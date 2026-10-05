import os
os.environ['SEED_MOCK_DATA'] = 'true'
os.environ['DEMO_IN_MEMORY'] = 'true'
os.environ['SCHEDULER_ENABLED'] = 'false'
import json
from datetime import timedelta
import pytest
import httpx
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient
from app.config import Config
from app.models import now
from app.services import bounds, today, create_alert, statuses, encrypt, decrypt, notify_negative_posts, within_automation_window
from app.sentiment import Classifier
from app.connectors import NEWS_CHANNELS, matches, apify_posts, _actor_input, ProviderError, request


def test_timezone_boundary():
    start, end = bounds('2026-09-28')
    assert start.isoformat() == '2026-09-27T18:30:00+00:00'
    assert end - start == timedelta(days=1)


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


def test_keyword_matching_hindi_and_pk():
    assert matches('जन सुराज पर चर्चा', ['जन सुराज'])
    assert matches('PK ki meeting', ['PK'])
    assert not matches('APK file download', ['PK'])


def test_token_only_apify_inputs_are_platform_specific():
    since = now() - timedelta(hours=2)
    keywords = ['Jan Suraaj', 'Prashant Kishore']
    assert _actor_input('facebook', '', keywords, since, 20)['searchType'] == 'posts'
    assert _actor_input('instagram', '', keywords, since, 20)['searchQueries'] == keywords
    assert _actor_input('x', '', keywords, since, 20)['searchTerms'] == keywords
    news = _actor_input('news', '', keywords, since, 20)
    assert all(term in news['query'] for term in keywords)
    assert all(channel in news['query'] for channel in NEWS_CHANNELS)
    assert news['maxItems'] == 100 and news['time_period'] == 'custom'


@pytest.mark.asyncio
async def test_webhook_accepts_empty_success_response():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(204))) as client:
        assert await request(client, 'POST', 'https://example.org/hook', response_json=False, json={'date': today()}) == {}


@pytest.mark.asyncio
async def test_negative_post_telegram_alert_is_idempotent(monkeypatch):
    db = AsyncMongoMockClient(tz_aware=True).test
    await db.posts.insert_one({
        'platform': 'facebook', 'external_id': 'negative-1', 'author': 'News Desk',
        'content': 'Jan Suraaj Party plan faces criticism',
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
    monkeypatch.setattr('app.services.within_automation_window', lambda value=None: True)
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
    monkeypatch.setattr('app.services.within_automation_window', lambda value=None: True)
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
    for p in ['facebook', 'instagram', 'news']:
        s = next(x for x in result if x['platform'] == p)
        assert s['source'] == 'Not connected' and s['status'] == 'disconnected'


@pytest.mark.asyncio
async def test_apify_actor_normalizes_and_filters_items():
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, json=[
            {'postId': '42', 'text': 'Jan Suraaj Party rally update', 'createdAt': now().isoformat(),
             'postUrl': 'https://example.org/post/42', 'authorName': 'Reporter', 'likesCount': '12'},
            {'postId': '43', 'text': 'Unrelated post', 'createdAt': now().isoformat()},
        ])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await apify_posts(client, 'facebook', {'api_key': 'apify-token-value', 'actor_id': 'owner~facebook-actor',
            'input_template': '{"queries": {{keywords_json}}, "since": "{{since_iso}}"}', 'max_items': 50},
            ['Jan Suraaj'], now() - timedelta(hours=1))
    assert len(rows) == 1 and rows[0]['external_id'] == '42'
    assert rows[0]['engagement']['likes'] == 12 and rows[0]['source_provider'] == 'apify'
    assert requests[0].headers['Authorization'] == 'Bearer apify-token-value'
    assert '/actors/owner~facebook-actor/run-sync-get-dataset-items' in str(requests[0].url)


@pytest.mark.asyncio
async def test_apify_normalizes_serialized_facebook_author():
    captured = []
    def handler(req):
        captured.append(req)
        return httpx.Response(200, json=[{
            'postId': 'fb-1', 'text': 'Jan Suraaj Party teachers update',
            'createdAt': now().isoformat(),
            'author': "{'id': '123', 'name': 'Jagarit Bihar', 'profilePic': 'https://example.org/long.jpg'}",
        }])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await apify_posts(client, 'facebook', {
            'api_key': 'token', 'actor_id': 'apify~facebook-search-scraper', 'max_items': 50,
        }, ['Jan Suraaj'], now() - timedelta(hours=1))
    assert rows[0]['author'] == 'Jagarit Bihar'


@pytest.mark.asyncio
async def test_easyapi_news_input_and_output_mapping():
    captured = []
    def handler(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200, json=[{
            'title': 'Prashant Kishore addresses Bihar rally',
            'snippet': 'Jan Suraaj leaders shared the campaign plan.',
            'link': 'https://news.example.org/story', 'source': 'News18 Bihar Jharkhand',
            'date_utc': now().isoformat(),
        }])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await apify_posts(client, 'news', {
            'api_key': 'token', 'actor_id': 'easyapi~google-news-scraper', 'max_items': 50,
        }, ['Jan Suraaj', 'Prashant Kishore'], now() - timedelta(days=1))
    assert captured[0]['maxItems'] == 100
    assert all(channel in captured[0]['query'] for channel in NEWS_CHANNELS)
    assert rows[0]['author'] == 'News18 Bihar Jharkhand'
    assert rows[0]['url'] == 'https://news.example.org/story'
    assert 'campaign plan' in rows[0]['content']


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
async def test_apify_rejects_unmapped_dataset():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=[{'text': 'Jan Suraaj update'}]))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderError):
            await apify_posts(client, 'news', {'api_key': 'apify-token-value', 'actor_id': 'news-actor'},
                              ['Jan Suraaj'], now() - timedelta(hours=1))
