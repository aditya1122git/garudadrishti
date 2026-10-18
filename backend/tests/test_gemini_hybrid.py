import json
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.connectors import YOUTUBE_SEARCH_TERMS, youtube_posts
from app.gemini_fallback import GeminiFallback
from app.models import now
from app.sentiment import Classifier, Result, apply_target_context, detect_targets


@pytest.mark.asyncio
async def test_exact_threshold_routes_only_below_80(monkeypatch):
    settings = SimpleNamespace(
        hf_confidence_threshold=.80, hf_model='hf', hf_revision='rev',
        gemini_model='gemini-test', gemini_api_key='test', gemini_concurrency=2,
    )
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='neutral', confidence=c, reason='HF') for c in [.80, .799, .9]])

    class Fallback:
        last_error = None

        async def classify(self, texts):
            assert texts == ['low']
            return [Result(sentiment='negative', confidence=.88, reason='Target criticism')]

    engine._gemini = Fallback()
    results = await engine.classify(['boundary', 'low', 'high'])
    assert [r.model_used for r in results] == [
        'hf@rev', 'gemini/gemini-test', 'hf@rev',
    ]
    assert results[1].hf_confidence == .799
    assert results[1].sentiment == 'negative'


@pytest.mark.asyncio
async def test_high_confidence_hf_negative_always_uses_gemini_final_label(monkeypatch):
    settings = SimpleNamespace(
        hf_confidence_threshold=.80, hf_model='hf', hf_revision='rev',
        gemini_model='gemini-test', gemini_api_key='test', gemini_concurrency=2,
    )
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='negative', confidence=.96, reason='HF negative',
               hf_label='negative', hf_confidence=.96),
    ])

    class Fallback:
        last_error = None

        async def classify(self, texts):
            assert texts == ['target-aware post']
            return [Result(sentiment='positive', confidence=.91, reason='Target praised')]

    engine._gemini = Fallback()
    result = (await engine.classify(['target-aware post']))[0]
    assert result.sentiment == 'positive'
    assert result.model_used == 'gemini/gemini-test'
    assert result.hf_label == 'negative'
    assert result.hf_confidence == .96


@pytest.mark.parametrize('title', [
    'अपराध पर दुख जताने के बजाय मजाक? विपक्ष के बयान पर भड़के सम्राट चौधरी! #BiharBJP',
    'जमुई कांड पर विपक्ष के बयान पर बरसे सम्राट चौधरी! #JamuiIncident',
    'राजधानी पटना में दिनदहाड़े गोलियां, डीजीपी तक नहीं! #BiharGovernment #PatnaFiring',
    'बिहार में 50 लाख बाढ़ पीड़ित #BiharBJP #BiharFlood',
])
def test_negative_event_with_campaign_hashtag_routes_to_target_verifier(title):
    result = apply_target_context(
        title, Result(sentiment='negative', confidence=.95, reason='Overall negative'), .80,
    )
    assert result.confidence == .79
    assert result.hf_confidence is None
    assert result.targets
    assert 'Gemini verification' in result.reason


def test_direct_target_criticism_can_stay_high_confidence_hf():
    result = apply_target_context(
        'बिहार सरकार ने जनता को निराश किया',
        Result(sentiment='negative', confidence=.94, reason='Overall negative'), .80,
    )
    assert result.confidence == .94


def test_target_condolence_is_positive_despite_negative_event_words():
    result = apply_target_context(
        'अभिनेता श्री नाना पाटेकर जी के निधन पर सीएम श्री सम्राट चौधरी जी ने जताया दुख। '
        '#samratchoudhary #nanapatekar',
        Result(sentiment='negative', confidence=.8569, reason='Overall negative'), .80,
    )
    assert result.sentiment == 'positive'
    assert result.confidence == .90
    assert result.targets == ['samrat_choudhary']
    assert result.hf_confidence is None


def test_mocked_target_condolence_is_not_force_positive():
    result = apply_target_context(
        'सम्राट चौधरी ने दुख जताया लेकिन लोगों ने इसे ढोंग बताया',
        Result(sentiment='negative', confidence=.91, reason='Overall negative'), .80,
    )
    assert result.sentiment == 'negative'


def test_devanagari_target_detection():
    text = 'सम्राट चौधरी, बिहार भाजपा और बिहार सरकार'
    assert detect_targets(text) == ['samrat_choudhary', 'bihar_bjp', 'bihar_government']
    assert detect_targets('#SamratChaudhary') == ['samrat_choudhary']
    assert detect_targets('Bihar Bharatiya Janata Party') == ['bihar_bjp']


@pytest.mark.asyncio
async def test_unavailable_fallback_keeps_high_results_and_flags_low(monkeypatch):
    settings = SimpleNamespace(
        hf_confidence_threshold=.80, hf_model='hf', hf_revision='rev',
        gemini_model='gemini-test', gemini_api_key='', gemini_concurrency=2,
    )
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='neutral', confidence=c, reason='HF') for c in [.79, .9]])
    results = await engine.classify(['low', 'high'])
    assert results[0].pending and not results[1].pending
    assert engine.status == 'partial'


@pytest.mark.asyncio
async def test_unavailable_gemini_keeps_high_hf_negative_pending(monkeypatch):
    settings = SimpleNamespace(
        hf_confidence_threshold=.80, hf_model='hf', hf_revision='rev',
        gemini_model='gemini-test', gemini_api_key='', gemini_concurrency=2,
    )
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='negative', confidence=.97, reason='HF negative',
               hf_label='negative', hf_confidence=.97),
    ])
    result = (await engine.classify(['negative event text']))[0]
    assert result.pending
    assert result.review_required


@pytest.mark.asyncio
async def test_mismatched_gemini_batch_retries_individually(monkeypatch):
    settings = SimpleNamespace(
        gemini_api_key='test', gemini_concurrency=2, gemini_model='gemini-test',
    )
    engine = GeminiFallback(settings)
    calls = []

    async def fake(client, texts):
        calls.append(texts)
        if len(texts) > 1:
            raise ValueError('Mismatch')
        return [Result(sentiment='neutral', confidence=.85, reason=texts[0])]

    monkeypatch.setattr(engine, '_request', fake)
    results = await engine.classify(['one', 'two'])
    assert [r.reason for r in results] == ['one', 'two']
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_gemini_rejects_wrong_ids():
    engine = GeminiFallback(SimpleNamespace(
        gemini_api_key='test', gemini_concurrency=1, gemini_model='gemini-test',
    ))
    payload = {'results': [
        {'id': 9, 'sentiment': 'neutral', 'confidence': .8, 'reason': 'Fact'},
    ]}

    def handler(request):
        return httpx.Response(200, json={'candidates': [{
            'finishReason': 'STOP',
            'content': {'parts': [{'text': json.dumps(payload)}]},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await engine._request(client, ['text'])


@pytest.mark.asyncio
async def test_gemini_accepts_mixed_label_and_uses_structured_output():
    engine = GeminiFallback(SimpleNamespace(
        gemini_api_key='test', gemini_concurrency=1, gemini_model='gemini-test',
    ))
    payload = {'results': [{
        'id': 0, 'sentiment': 'mixed', 'confidence': .9,
        'reason': 'Praise and criticism both target the entity.',
    }]}

    def handler(request):
        body = json.loads(request.content)
        assert request.headers['x-goog-api-key'] == 'test'
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert body['generationConfig']['responseSchema']['required'] == ['results']
        return httpx.Response(200, json={'candidates': [{
            'finishReason': 'STOP',
            'content': {'parts': [{'text': json.dumps(payload)}]},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await engine._request(client, ['Good ideas, poor execution'])
    assert result[0].sentiment == 'mixed' and result[0].confidence == .9


@pytest.mark.asyncio
async def test_youtube_classifies_title_only_never_description_or_comments():
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if req.url.path.endswith('/search'):
            assert req.url.params['q'] == '|'.join(YOUTUBE_SEARCH_TERMS)
            return httpx.Response(200, json={'items': [
                {'id': {'videoId': 'abc'}}, {'id': {'videoId': 'description-only'}},
            ]})
        assert req.url.path.endswith('/videos')
        assert req.url.params['part'] == 'snippet,statistics,contentDetails'
        return httpx.Response(200, json={'items': [
            {'id': 'abc', 'snippet': {
                'title': 'Samrat Choudhary meeting',
                'description': 'Full description, not a search excerpt.',
                'channelTitle': 'News', 'publishedAt': '2026-10-01T00:00:00Z'},
             'contentDetails': {'duration': 'PT45S'},
             'statistics': {'likeCount': '4', 'viewCount': '90', 'commentCount': '99'}},
            {'id': 'description-only', 'snippet': {
                'title': 'Unrelated daily bulletin',
                'description': 'Samrat Choudhary appears only here.',
                'channelTitle': 'News', 'publishedAt': '2026-10-01T00:00:00Z'},
             'statistics': {}},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await youtube_posts(
            client, {'api_key': 'test'}, ['Samrat Choudhary'], now() - timedelta(days=1),
        )
    assert paths.count('/youtube/v3/search') == 1 and len(rows) == 1
    assert rows[0]['content'] == 'Samrat Choudhary meeting'
    assert 'description' not in rows[0]
    assert rows[0]['engagement']['comments'] == 0
    assert rows[0]['engagement']['views'] == 90
    assert rows[0]['content_scope'] == 'youtube-title-only-v2'
    assert rows[0]['content_type'] == 'short'


@pytest.mark.asyncio
async def test_youtube_search_exhausts_all_result_pages():
    search_tokens = []

    def handler(req):
        if req.url.path.endswith('/search'):
            token = req.url.params.get('pageToken')
            search_tokens.append(token)
            video_id = 'first' if token is None else 'second'
            payload = {'items': [{'id': {'videoId': video_id}}]}
            if token is None:
                payload['nextPageToken'] = 'page-2'
            return httpx.Response(200, json=payload)
        ids = req.url.params['id'].split(',')
        return httpx.Response(200, json={'items': [{
            'id': video_id,
            'snippet': {'title': f'Samrat Choudhary {video_id}', 'channelTitle': 'News',
                        'publishedAt': '2026-10-01T00:00:00Z'},
            'statistics': {}, 'contentDetails': {'duration': 'PT5M'},
        } for video_id in ids]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await youtube_posts(
            client, {'api_key': 'test'}, ['Samrat Choudhary'], now() - timedelta(days=1),
        )

    assert search_tokens == [None, 'page-2']
    assert {row['external_id'] for row in rows} == {'first', 'second'}


@pytest.mark.asyncio
async def test_youtube_rotates_to_backup_key_only_after_quota_exhaustion():
    keys = []

    def handler(req):
        key = req.url.params['key']
        keys.append(key)
        if key == 'primary':
            return httpx.Response(403, json={'error': {
                'message': 'The request cannot be completed because you have exceeded your quota.',
                'errors': [{'reason': 'quotaExceeded'}],
            }})
        if req.url.path.endswith('/search'):
            return httpx.Response(200, json={'items': [{'id': {'videoId': 'backup-video'}}]})
        return httpx.Response(200, json={'items': [{
            'id': 'backup-video',
            'snippet': {'title': 'Bihar BJP update', 'channelTitle': 'News',
                        'publishedAt': '2026-10-06T06:00:00Z'},
            'statistics': {}, 'contentDetails': {'duration': 'PT5M'},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await youtube_posts(client, {
            'api_key': 'primary', 'backup_api_key': 'backup',
        }, ['Bihar BJP'], now() - timedelta(days=1))

    assert keys == ['primary', 'backup', 'backup']
    assert len(rows) == 1 and rows[0]['external_id'] == 'backup-video'
