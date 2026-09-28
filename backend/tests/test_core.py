import os
os.environ['SEED_MOCK_DATA'] = 'true'
os.environ['DEMO_IN_MEMORY'] = 'true'
os.environ['SCHEDULER_ENABLED'] = 'false'
import json
from datetime import timedelta
import pytest
import httpx
from mongomock_motor import AsyncMongoMockClient
from app.models import now
from app.services import bounds, today, create_alert, statuses, encrypt, decrypt
from app.sentiment import Classifier
from app.connectors import matches, x_posts, ProviderError, request


def test_timezone_boundary():
    start, end = bounds('2026-09-28')
    assert start.isoformat() == '2026-09-27T18:30:00+00:00'
    assert end - start == timedelta(days=1)


def test_encryption():
    secret = {'api_key': 'private-key-value'}
    ciphertext = encrypt(secret)
    assert 'private-key' not in ciphertext
    assert decrypt(ciphertext) == secret


def test_keyword_matching_hindi_and_pk():
    assert matches('जन सुराज पर चर्चा', ['जन सुराज'])
    assert matches('PK ki meeting', ['PK'])
    assert not matches('APK file download', ['PK'])


@pytest.mark.asyncio
async def test_webhook_accepts_empty_success_response():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(204))) as client:
        assert await request(client, 'POST', 'https://example.org/hook', response_json=False, json={'date': today()}) == {}


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
async def test_meta_unconfigured_is_disconnected():
    result = await statuses(AsyncMongoMockClient().test)
    for p in ['facebook', 'instagram']:
        s = next(x for x in result if x['platform'] == p)
        assert s['source'] == 'Not connected' and s['status'] == 'disconnected'


@pytest.mark.asyncio
async def test_x_does_not_rotate_to_evade_rate_limit():
    tokens = []
    def handler(req):
        tokens.append(req.headers['Authorization'])
        return httpx.Response(429, headers={'retry-after': '900'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError):
            await x_posts(client, {'tokens': ['one', 'two']}, ['Jan Suraaj'], now() - timedelta(hours=1))
    assert tokens == ['Bearer one']


@pytest.mark.asyncio
async def test_x_rotates_expired_token():
    def handler(req):
        if req.headers['Authorization'] == 'Bearer one':
            return httpx.Response(401)
        return httpx.Response(200, json={'data': [], 'meta': {}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await x_posts(client, {'tokens': ['one', 'two']}, ['Jan Suraaj'], now() - timedelta(hours=1)) == []
