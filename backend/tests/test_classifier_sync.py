import pytest
from mongomock_motor import AsyncMongoMockClient
from app import services
from app.sentiment import Result


@pytest.mark.asyncio
@pytest.mark.parametrize('fails', [False, True])
async def test_local_classifier_only_processes_pending_live_posts(monkeypatch, fails):
    db = AsyncMongoMockClient().test
    await db.posts.insert_many([
        {'external_id': 'pending', 'sentiment': None, 'demo': False, 'content': 'A new post'},
        {'external_id': 'classified', 'sentiment': {'label': 'positive'}, 'demo': False, 'content': 'Old post'},
        {'external_id': 'demo', 'sentiment': None, 'demo': True, 'content': 'Synthetic post'},
    ])
    class Settings:
        seed_mock_data = False
        hf_batch_size = 16
    class Engine:
        provenance = 'public/model@pinned-commit'
        async def classify(self, texts):
            assert texts == ['A new post']
            if fails:
                raise RuntimeError('Model unavailable')
            return [Result(sentiment='negative', confidence=.8, reason='Test inference')]
    async def no_op(*args):
        pass
    monkeypatch.setattr(services, 'config', lambda: Settings())
    monkeypatch.setattr(services, 'classifier', Engine)
    monkeypatch.setattr(services, 'rollup', no_op)
    monkeypatch.setattr(services, 'notify_alerts', no_op)
    await services.sync(db, None)
    pending = await db.posts.find_one({'external_id': 'pending'})
    if fails:
        assert pending['sentiment'] is None
    else:
        assert pending['sentiment']['label'] == 'negative'
        assert pending['sentiment']['model_used'] == Engine.provenance
    assert (await db.posts.find_one({'external_id': 'classified'}))['sentiment'] == {'label': 'positive'}
    assert (await db.posts.find_one({'external_id': 'demo'}))['sentiment'] is None
