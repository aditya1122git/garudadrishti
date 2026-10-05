import json
from datetime import timedelta
from types import SimpleNamespace
import httpx
import pytest
from app.sentiment import Classifier, Result, apply_target_context, detect_targets
from app.groq_fallback import GroqFallback
from app.connectors import youtube_posts
from app.models import now


@pytest.mark.asyncio
async def test_exact_threshold_routes_only_below_60(monkeypatch):
    settings = SimpleNamespace(hf_confidence_threshold=.60, hf_model='hf', hf_revision='rev', groq_model='groq')
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='neutral', confidence=c, reason='HF') for c in [.60, .599, .9]])
    class Fallback:
        async def classify(self, texts):
            assert texts == ['low']
            return [Result(sentiment='negative', confidence=.88, reason='Target criticism')]
    engine._groq = Fallback()
    results = await engine.classify(['boundary', 'low', 'high'])
    assert [r.model_used for r in results] == ['hf@rev', 'groq/groq', 'hf@rev']
    assert results[1].hf_confidence == .599
    assert results[1].sentiment == 'negative'


def test_sarcastic_opponent_attack_becomes_local_positive_target_stance():
    title = ('BJP \u0915\u094b \u0935\u094b\u091f \u0915\u0940\u091c\u093f\u090f \u091b\u0924 \u0938\u0947 \u092a\u093e\u0928\u0940 '
             '\u0906\u090f\u0917\u093e #youth #prashantkishor #jansuraj #bjp #modi')
    result = apply_target_context(
        title, Result(sentiment='negative', confidence=.85, reason='Overall negative tone'),
        sarcasm_probability=.90, sarcasm_threshold=.65,
    )
    assert result.sentiment == 'positive'
    assert result.confidence == pytest.approx(.95)
    assert result.sarcasm_detected
    assert result.language == 'hinglish'
    assert result.targets == ['jan_suraaj', 'prashant_kishore']


def test_political_sarcasm_cue_compensates_for_model_false_negative():
    title = ('BJP \u0915\u094b \u0935\u094b\u091f \u0915\u0940\u091c\u093f\u090f \u091b\u0924 \u0938\u0947 \u092a\u093e\u0928\u0940 '
             '\u0906\u090f\u0917\u093e #prashantkishor #jansuraj #bjp')
    result = apply_target_context(
        title, Result(sentiment='neutral', confidence=.354, reason='Overall ambiguous tone'),
        sarcasm_probability=.002, sarcasm_threshold=.65,
    )
    assert result.sentiment == 'positive'
    assert result.confidence == pytest.approx(.95)
    assert result.sarcasm_model_confidence == .002
    assert result.sarcasm_confidence == .90


def test_devanagari_target_detection():
    text = ('\u091c\u0928 \u0938\u0941\u0930\u093e\u091c \u0914\u0930 '
            '\u092a\u094d\u0930\u0936\u093e\u0902\u0924 \u0915\u093f\u0936\u094b\u0930')
    assert detect_targets(text) == ['jan_suraaj', 'prashant_kishore']


def test_ambiguous_sarcasm_routes_to_groq_by_reducing_combined_confidence():
    result = apply_target_context(
        'Great work Prashant Kishore, another promise!',
        Result(sentiment='negative', confidence=.84, reason='Overall negative tone'),
        sarcasm_probability=.88, sarcasm_threshold=.65,
    )
    assert result.sentiment == 'negative'
    assert result.confidence == .59
    assert 'ambiguous' in result.reason


@pytest.mark.asyncio
async def test_unavailable_fallback_keeps_high_results_and_flags_low(monkeypatch):
    settings = SimpleNamespace(hf_confidence_threshold=.60, hf_model='hf', hf_revision='rev',
                               groq_model='groq', groq_api_key='', groq_concurrency=2)
    engine = Classifier(settings)
    monkeypatch.setattr(engine, '_run', lambda texts: [
        Result(sentiment='neutral', confidence=c, reason='HF') for c in [.59, .9]])
    results = await engine.classify(['low', 'high'])
    assert results[0].pending and not results[1].pending
    assert engine.status == 'partial'


@pytest.mark.asyncio
async def test_mismatched_groq_batch_retries_individually(monkeypatch):
    settings = SimpleNamespace(groq_api_key='test', groq_concurrency=2, groq_model='test')
    engine = GroqFallback(settings)
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
async def test_groq_rejects_wrong_ids():
    engine = GroqFallback(SimpleNamespace(groq_api_key='test', groq_concurrency=1, groq_model='test'))
    payload = {'results': [{'id': 9, 'sentiment': 'neutral', 'confidence': .8, 'reason': 'Fact'}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        json={'choices': [{'message': {'content': json.dumps(payload)}}]}))) as client:
        with pytest.raises(ValueError):
            await engine._request(client, ['text'])


@pytest.mark.asyncio
async def test_groq_accepts_mixed_label():
    engine = GroqFallback(SimpleNamespace(groq_api_key='test', groq_concurrency=1, groq_model='test'))
    payload = {'results': [{'id': 0, 'sentiment': 'mixed', 'confidence': .9,
                            'reason': 'Praise and criticism both target the entity.'}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        json={'choices': [{'message': {'content': json.dumps(payload)}}]}))) as client:
        result = await engine._request(client, ['Good ideas, poor execution'])
    assert result[0].sentiment == 'mixed' and result[0].confidence == .9


@pytest.mark.asyncio
async def test_youtube_classifies_title_only_never_description_or_comments():
    paths = []
    def handler(req):
        paths.append(req.url.path)
        if req.url.path.endswith('/search'):
            return httpx.Response(200, json={'items': [
                {'id': {'videoId': 'abc'}}, {'id': {'videoId': 'description-only'}}]})
        assert req.url.path.endswith('/videos')
        assert req.url.params['part'] == 'snippet,statistics,contentDetails'
        return httpx.Response(200, json={'items': [
            {'id': 'abc', 'snippet': {
                'title': 'Prashant Kishore meeting', 'description': 'Full description, not a search excerpt.',
                'channelTitle': 'News', 'publishedAt': '2026-10-01T00:00:00Z'},
                'statistics': {'likeCount': '4', 'viewCount': '90', 'commentCount': '99'}},
            {'id': 'description-only', 'snippet': {
                'title': 'Unrelated daily bulletin', 'description': 'Prashant Kishore appears only here.',
                'channelTitle': 'News', 'publishedAt': '2026-10-01T00:00:00Z'},
                'statistics': {}}
        ]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await youtube_posts(client, {'api_key': 'test'}, ['Prashant Kishore'], now()-timedelta(days=1))
    assert paths.count('/youtube/v3/search') == 2 and len(rows) == 1
    assert rows[0]['content'] == 'Prashant Kishore meeting'
    assert 'description' not in rows[0]
    assert rows[0]['engagement']['comments'] == 0
    assert rows[0]['engagement']['views'] == 90
    assert rows[0]['content_scope'] == 'youtube-title-only-v2'
    assert rows[0]['content_type'] == 'short'
