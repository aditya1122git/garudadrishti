import os
os.environ['SEED_MOCK_DATA'] = 'true'
os.environ['DEMO_IN_MEMORY'] = 'true'
os.environ['SCHEDULER_ENABLED'] = 'false'
import json
from datetime import timedelta
import pytest
import httpx
import app.data365 as data365_module
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient
from app.config import Config
from app.models import now
from app.services import bounds, today, create_alert, statuses, encrypt, decrypt, notify_negative_posts, within_automation_window, _telegram_link_label, _social_posts_with_fallback
from app.sentiment import Classifier
from app.connectors import NEWS_CHANNELS, NEWS_SEARCH_QUERIES, matches, apify_posts, google_news_posts, _actor_input, _apify_item, _approved_news_source, ProviderError, request
from app.data365 import data365_posts, _data365_request_spec


def test_timezone_boundary():
    start, end = bounds('2026-09-28')
    assert start.isoformat() == '2026-09-27T18:30:00+00:00'
    assert end - start == timedelta(days=1)


def test_telegram_link_labels_are_platform_specific():
    assert _telegram_link_label('x') == 'View on X'
    assert _telegram_link_label('youtube') == 'View on YouTube'
    assert _telegram_link_label('instagram') == 'View on Instagram'
    assert _telegram_link_label('reddit') == 'View on Reddit'


def test_bootstrap_credentials_are_optional_for_existing_database():
    settings = Config(_env_file=None, seed_mock_data=False, demo_in_memory=False,
                      jwt_secret='x' * 32, encryption_key=Fernet.generate_key().decode(),
                      bootstrap_email='', bootstrap_password='')
    assert settings.bootstrap_email == '' and settings.bootstrap_password == ''


def test_encryption():
    secret = {'api_key': 'private-key-value'}
    ciphertext = encrypt(secret)
    assert 'private-key' not in ciphertext
    assert decrypt(ciphertext) == secret


def test_keyword_matching_hindi_and_name_variants():
    assert matches('बिहार सरकार पर चर्चा', ['बिहार सरकार'])
    assert matches('Samrat Choudhary ki meeting', ['Samrat Choudhary'])
    assert not matches('Unrelated Bihar bulletin', ['Bihar BJP'])


def test_token_only_apify_inputs_are_platform_specific():
    since = now() - timedelta(hours=2)
    keywords = ['Samrat Choudhary', 'Bihar BJP']
    instagram = _actor_input('instagram', keywords, since, 20)
    assert instagram['resultsType'] == 'posts'
    assert instagram['directUrls'] == [
        'https://www.instagram.com/explore/tags/SamratChoudhary/',
        'https://www.instagram.com/explore/tags/BiharBJP/',
    ]
    assert instagram['onlyPostsNewerThan'].endswith('Z')
    x_input = _actor_input('x', keywords, since, 20)
    assert x_input['sort'] == 'Latest + Top'
    assert x_input['searchTerms'] == [
        f'("Samrat Choudhary" OR "Samrat Chaudhary" OR "CM Samrat" OR '
        f'#SamratChoudhary OR #SamratChaudhary OR #CMSamrat) since:{since.date().isoformat()}',
        f'("Bihar BJP" OR "BJP Bihar" OR "बिहार भाजपा" OR "भाजपा बिहार" OR '
        f'#BiharBJP OR #BJP4Bihar OR @BJP4Bihar OR from:BJP4Bihar) since:{since.date().isoformat()}',
    ]
    assert len(x_input['searchTerms']) <= 5


def test_x_actor_combines_keyword_variants_into_broad_entity_queries():
    since = now() - timedelta(hours=2)
    x_input = _actor_input('x', [
        'Samrat Choudhary', 'Samrat Chaudhary', 'सम्राट चौधरी', '#SamratChoudhary',
        'Bihar BJP', 'BJP Bihar', 'बिहार भाजपा', '#BiharBJP',
        'Bihar Government', 'बिहार सरकार', '#BiharGovt',
        'NDA Bihar', '#NDABihar', '#एनडीए',
    ], since, 50)
    assert len(x_input['searchTerms']) == 5
    assert all(f'since:{since.date().isoformat()}' in term for term in x_input['searchTerms'])
    assert '"Samrat Choudhary" OR "Samrat Chaudhary"' in x_input['searchTerms'][0]
    assert any('#BiharBJP' in term for term in x_input['searchTerms'])


def test_x_actor_accepts_target_aliases_and_official_account_posts():
    since = now() - timedelta(hours=2)
    alias_item = {
        'id': 'alias', 'text': 'CM Samrat ने आज नई पहल शुरू की',
        'createdAt': now().isoformat(), 'url': 'https://x.com/example/status/alias',
        'author': {'userName': 'example'},
    }
    official_item = {
        'id': 'official', 'text': 'आज पटना में जनसंवाद किया।',
        'createdAt': now().isoformat(), 'url': 'https://x.com/samrat4bjp/status/official',
        'author': {'userName': 'samrat4bjp'},
    }
    assert _apify_item('x', alias_item, ['Samrat Choudhary'], since)['external_id'] == 'alias'
    assert _apify_item('x', official_item, ['Samrat Choudhary'], since)['external_id'] == 'official'


@pytest.mark.parametrize('source', [
    'Dainik Bhaskar', 'jagran.com', 'tv9hindi.com', 'prabhatkhabar.com',
    'Hindustan', 'ETV Bharat', 'Navbharat Times',
])
def test_expanded_bihar_news_sources_are_approved(source):
    assert _approved_news_source(source)


def test_similarly_named_unapproved_source_is_rejected():
    assert not _approved_news_source('Hindustan Times')


@pytest.mark.asyncio
async def test_webhook_accepts_empty_success_response():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(204))) as client:
        assert await request(client, 'POST', 'https://example.org/hook', response_json=False, json={'date': today()}) == {}


@pytest.mark.asyncio
async def test_negative_post_telegram_alert_is_idempotent(monkeypatch):
    db = AsyncMongoMockClient(tz_aware=True).test
    await db.posts.insert_one({
        'platform': 'facebook', 'external_id': 'negative-1', 'author': 'News Desk',
        'content': 'Bihar Government plan faces criticism',
        'url': 'https://example.org/post/negative-1', 'published_at': now(), 'demo': False,
        'sentiment': {'label': 'negative', 'confidence': .91},
        'telegram_notification': {'status': 'pending'},
    })
    class Settings:
        seed_mock_data = False
        telegram_bot_token = '123456:test_bot_token_value_long_enough'
        telegram_chat_id = '-1001234567890'
        reporting_timezone = 'Asia/Kolkata'
        automation_start_hour = 6
        automation_end_hour = 22
    monkeypatch.setattr('app.services.config', lambda: Settings())
    monkeypatch.setattr('app.services.within_automation_window', lambda *args, **kwargs: True)
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await notify_negative_posts(db, client)
        await notify_negative_posts(db, client)
    stored = await db.posts.find_one({'external_id': 'negative-1'})
    assert stored['telegram_notification']['status'] == 'sent'
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload['chat_id'] == '-1001234567890'
    assert payload['parse_mode'] == 'HTML'
    assert payload['disable_web_page_preview'] is True
    assert 'GarudaDrishti negative post' in payload['text']
    assert '>View on Facebook</a>' in payload['text']
    assert 'Open post:' not in payload['text']
    assert 'https://example.org/post/negative-1' in payload['text']


@pytest.mark.asyncio
async def test_old_negative_post_is_skipped_without_telegram_delivery(monkeypatch):
    db = AsyncMongoMockClient(tz_aware=True).test
    await db.posts.insert_one({
        'platform': 'youtube', 'external_id': 'old-negative', 'author': 'Channel',
        'content': 'Old negative title', 'url': 'https://youtu.be/old-negative',
        'published_at': now() - timedelta(days=1), 'demo': False,
        'sentiment': {'label': 'negative', 'confidence': .9},
        'telegram_notification': {'status': 'pending'},
    })
    class Settings:
        seed_mock_data = False
        telegram_bot_token = '123456:test_bot_token_value_long_enough'
        telegram_chat_id = '-1001234567890'
        reporting_timezone = 'Asia/Kolkata'
    monkeypatch.setattr('app.services.config', lambda: Settings())
    monkeypatch.setattr('app.services.within_automation_window', lambda *args, **kwargs: True)
    requests = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda req: requests.append(req) or httpx.Response(200, json={'ok': True}))) as client:
        await notify_negative_posts(db, client)
    stored = await db.posts.find_one({'external_id': 'old-negative'})
    assert stored['telegram_notification']['status'] == 'skipped'
    assert requests == []


def test_hf_label_mapping_and_low_confidence():
    from app.sentiment import result_from_scores, preprocess
    result = result_from_scores(['Positive', 'Negative', 'Neutral'], [.15, .6, .25], True)
    assert result.sentiment == 'negative' and result.confidence == .6
    assert 'Low model confidence' in result.reason and 'truncated' in result.reason
    assert preprocess('@analyst text https://example.org/a') == '@user text http'


@pytest.mark.parametrize('labels,scores', [
    (['LABEL_0', 'LABEL_1', 'LABEL_2'], [.2, .3, .5]),
    (['negative', 'neutral', 'positive'], [.2, .3, float('nan')]),
    (['negative', 'neutral', 'positive'], [.2, .3, 1.4]),
    (['negative', 'neutral', 'positive'], [.2, .3, .1]),
])
def test_hf_rejects_invalid_model_output(labels, scores):
    from app.sentiment import result_from_scores
    with pytest.raises(ValueError):
        result_from_scores(labels, scores)


@pytest.mark.asyncio
async def test_hf_batch_validation_and_failure_status(monkeypatch):
    engine = Classifier()
    monkeypatch.setattr(engine, '_run', lambda texts: [])
    with pytest.raises(ValueError):
        await engine.classify(['a', 'b'])
    assert engine.status == 'unavailable' and 'pending' in engine.error


@pytest.mark.asyncio
async def test_hf_inference_off_event_loop(monkeypatch):
    import threading
    from app.sentiment import Result
    engine = Classifier()
    main_thread = threading.get_ident()
    def run(texts):
        assert threading.get_ident() != main_thread
        return [Result(sentiment='neutral', confidence=.8, reason='Test classification') for _ in texts]
    monkeypatch.setattr(engine, '_run', run)
    assert len(await engine.classify(['English text', 'Hindi text'])) == 2
    assert engine.status == 'live'
    assert '@' in engine.provenance
    assert await engine.classify([]) == []


@pytest.mark.asyncio
async def test_alert_strict_threshold_and_idempotence():
    db = AsyncMongoMockClient(tz_aware=True).test
    await db.alerts.create_index('date', unique=True)
    await db.settings.insert_one({'_id': 'main', 'threshold': 500})
    await db.daily_aggregates.insert_one({'date': today(), 'platform': 'overall', 'negative_count': 500})
    await create_alert(db, today())
    assert await db.alerts.count_documents({}) == 0
    await db.daily_aggregates.update_one({}, {'$set': {'negative_count': 501}})
    await create_alert(db, today()); await create_alert(db, today())
    assert await db.alerts.count_documents({}) == 1
    await db.alerts.update_one({}, {'$set': {'resolved': True}})
    await create_alert(db, today())
    assert (await db.alerts.find_one({}))['resolved'] is True


@pytest.mark.asyncio
async def test_apify_sources_unconfigured_are_disconnected():
    result = await statuses(AsyncMongoMockClient().test)
    for p in ['facebook', 'instagram']:
        s = next(x for x in result if x['platform'] == p)
        assert s['source'] == 'Not connected' and s['status'] == 'disconnected'


@pytest.mark.asyncio
async def test_apify_actor_normalizes_and_filters_items():
    requests = []
    def handler(req):
        requests.append(req)
        if 'facebook-search-scraper' in str(req.url):
            return httpx.Response(200, json=[
                {'pageName': 'Bihar BJP', 'facebookUrl': 'https://www.facebook.com/BJP4Bihar'},
            ])
        return httpx.Response(200, json=[
            {'postId': '42', 'text': 'Bihar BJP rally update', 'time': now().isoformat(),
             'postUrl': 'https://example.org/post/42', 'pageName': 'Reporter', 'reactionCount': '12'},
            {'postId': '43', 'text': 'Unrelated post', 'createdAt': now().isoformat()},
        ])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await apify_posts(client, 'facebook', {'api_key': 'apify-token-value'},
            ['Bihar BJP'], now() - timedelta(hours=1))
    assert len(rows) == 1 and rows[0]['external_id'] == '42'
    assert rows[0]['engagement']['likes'] == 12 and rows[0]['source_provider'] == 'apify'
    assert requests[0].headers['Authorization'] == 'Bearer apify-token-value'
    assert '/acts/apify~facebook-search-scraper/run-sync-get-dataset-items' in str(requests[0].url)
    assert '/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items' in str(requests[1].url)
    assert json.loads(requests[1].content)['startUrls'] == [{'url': 'https://www.facebook.com/BJP4Bihar'}]


@pytest.mark.asyncio
async def test_apify_normalizes_serialized_facebook_author():
    def handler(req):
        if 'facebook-search-scraper' in str(req.url):
            return httpx.Response(200, json=[{'facebookUrl': 'https://facebook.com/jagaritbihar'}])
        return httpx.Response(200, json=[{
            'postId': 'fb-1', 'text': 'Bihar Government teachers update',
            'createdAt': now().isoformat(),
            'author': "{'id': '123', 'name': 'Jagarit Bihar', 'profilePic': 'https://example.org/long.jpg'}",
        }])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await apify_posts(client, 'facebook', {'api_key': 'token'},
                                 ['Bihar Government'], now() - timedelta(hours=1))
    assert rows[0]['author'] == 'Jagarit Bihar'


@pytest.mark.asyncio
async def test_data365_async_search_normalizes_x_posts():
    requests = []

    def handler(req):
        requests.append(req)
        assert req.url.params['access_token'] == 'data365-token-value'
        if req.method == 'POST':
            return httpx.Response(202, json={'status': 'accepted', 'data': {'task_id': 'task-1'}})
        if str(req.url.path).endswith('/update'):
            return httpx.Response(200, json={'status': 'ok', 'data': {'status': 'finished'}})
        return httpx.Response(200, json={'status': 'ok', 'data': {'items': [{
            'id': '19001', 'text': 'Samrat Choudhary reviews Bihar development work',
            'created_time': now().isoformat(), 'author_username': 'reporter_bihar',
            'favorite_count': 18, 'reply_count': 3, 'retweet_count': 5,
        }]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await data365_posts(client, 'x', {'data365_api_token': 'data365-token-value'},
                                   ['Samrat Choudhary'], now() - timedelta(hours=1))
    assert [req.method for req in requests] == ['POST', 'GET', 'GET']
    assert rows[0]['external_id'] == '19001'
    assert rows[0]['url'] == 'https://x.com/reporter_bihar/status/19001'
    assert rows[0]['engagement'] == {'likes': 18, 'comments': 3, 'shares': 5, 'views': 0}
    assert rows[0]['source_provider'] == 'data365'


@pytest.mark.parametrize('platform', ['instagram', 'reddit'])
def test_data365_search_status_uses_update_endpoint(platform):
    create_url, _, status_url, _, _, _ = _data365_request_spec(
        platform, 'Samrat Choudhary', now() - timedelta(hours=1), 10,
    )
    assert create_url.endswith('/update')
    assert status_url == create_url
    if platform == 'instagram':
        assert '/instagram/tag/Samrat%20Choudhary/' in create_url


@pytest.mark.asyncio
async def test_social_provider_falls_back_to_data365_only_for_empty_apify(monkeypatch):
    calls = []

    async def empty_apify(*args):
        calls.append('apify')
        return []

    async def working_data365(*args):
        calls.append('data365')
        return [{'external_id': 'fallback-1'}]

    monkeypatch.setattr('app.services.apify_posts', empty_apify)
    monkeypatch.setattr('app.services.data365_posts', working_data365)
    rows, provider, reason = await _social_posts_with_fallback(
        None, 'x', {'api_key': 'a', 'data365_api_token': 'd'},
        ['Samrat Choudhary'], now() - timedelta(hours=1),
    )
    assert calls == ['apify', 'data365']
    assert rows == [{'external_id': 'fallback-1'}]
    assert provider == 'data365' and reason == 'Apify returned no usable posts'


@pytest.mark.asyncio
async def test_data365_keeps_partial_results_when_one_search_fails(monkeypatch):
    async def partial_search(client, platform, token, query, since, max_posts):
        if query == 'Bihar BJP':
            raise ProviderError('One Data365 task failed')
        return [{
            'id': 'partial-1', 'text': 'Samrat Choudhary reviews Bihar projects',
            'created_time': now().isoformat(), 'owner_username': 'bihar_updates',
        }]

    monkeypatch.setattr(data365_module, '_run_data365_search', partial_search)
    rows = await data365_posts(
        None, 'instagram', {'data365_api_token': 'token'},
        ['Samrat Choudhary', 'Bihar BJP'], now() - timedelta(hours=1),
    )
    assert len(rows) == 1
    assert rows[0]['external_id'] == 'partial-1'
    assert rows[0]['source_provider'] == 'data365'


@pytest.mark.asyncio
async def test_google_news_rss_input_and_output_mapping():
    from email.utils import format_datetime
    captured = []
    published = format_datetime(now())
    def handler(req):
        captured.append(req)
        return httpx.Response(200, text=f'''<?xml version="1.0" encoding="UTF-8"?>
          <rss version="2.0"><channel><item>
          <title>Samrat Choudhary addresses Bihar rally - News18 Bihar Jharkhand</title>
          <link>https://news.google.com/rss/articles/story</link>
          <guid>rss-story-1</guid><pubDate>{published}</pubDate>
          <source url="https://news18.com">News18 Bihar Jharkhand</source>
          </item></channel></rss>''')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await google_news_posts(client, ['Samrat Choudhary', 'Bihar BJP'], now() - timedelta(days=1))
    assert len(captured) == len(NEWS_SEARCH_QUERIES)
    assert all(req.url.host == 'news.google.com' for req in captured)
    assert all(req.url.params['ceid'] == 'IN:hi' for req in captured)
    assert all(not any(channel in req.url.params['q'] for channel in NEWS_CHANNELS)
               for req in captured)
    assert rows[0]['author'] == 'News18 Bihar Jharkhand'
    assert rows[0]['url'] == 'https://news.google.com/rss/articles/story'
    assert rows[0]['content'] == 'Samrat Choudhary addresses Bihar rally'
    assert rows[0]['source_provider'] == 'google-news-rss'


def test_reddit_actor_input_and_post_mapping():
    since = now() - timedelta(hours=6)
    payload = _actor_input('reddit', ['Samrat Choudhary', 'Bihar BJP'], since, 10)
    assert payload['queries'] == ['Samrat Choudhary', 'Bihar BJP']
    assert payload['scrapeComments'] is False and payload['includeNsfw'] is False
    assert payload['strictSearch'] is True and payload['strictTokenFilter'] is False
    assert payload['sort'] == 'new' and payload['timeframe'] == 'day'
    assert payload['maxPosts'] == 5

    row = _apify_item('reddit', {
        'id': 't3_reddit1', 'dataType': 'post',
        'title': 'Samrat Choudhary announces a Bihar development programme',
        'body': 'The Bihar BJP discussed the programme today.',
        'author': 'bihar_observer', 'score': 42, 'num_comments': 7,
        'created_utc': now().timestamp(),
        'url': 'https://www.reddit.com/r/bihar/comments/reddit1/example/',
    }, ['Samrat Choudhary', 'Bihar BJP'], since)
    assert row['platform'] == 'reddit' and row['external_id'] == 't3_reddit1'
    assert row['author'] == 'bihar_observer'
    assert row['engagement']['likes'] == 42 and row['engagement']['comments'] == 7
    assert row['content_scope'] == 'reddit-public-post-v1'
    assert _apify_item('reddit', {
        'id': 't1_comment', 'dataType': 'comment', 'body': 'Bihar BJP',
    }, ['Bihar BJP'], since) is None


def test_automation_window_uses_ist(monkeypatch):
    from datetime import datetime, timezone
    class Settings:
        reporting_timezone = 'Asia/Kolkata'
        automation_start_hour = 6
        automation_end_hour = 22
    monkeypatch.setattr('app.services.config', lambda: Settings())
    assert not within_automation_window(datetime(2026, 10, 4, 0, 29, tzinfo=timezone.utc))  # 05:59 IST
    assert within_automation_window(datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc))
    assert within_automation_window(datetime(2026, 10, 4, 16, 30, tzinfo=timezone.utc))
    assert not within_automation_window(datetime(2026, 10, 4, 17, 30, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_youtube_daily_quota_error_is_reported_without_retries():
    calls = 0

    def handler(req):
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={'error': {
            'message': "Quota exceeded for quota metric 'Search Queries' and limit 'Search Queries per day'",
            'errors': [{'reason': 'rateLimitExceeded'}],
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match='daily search quota exhausted'):
            await request(client, 'GET', 'https://www.googleapis.com/youtube/v3/search')

    assert calls == 1
