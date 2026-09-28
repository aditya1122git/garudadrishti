"""Optional real-Mongo check: TEST_MONGODB_URI=mongodb://localhost:27017 pytest tests/test_mongo.py."""
import os
os.environ.setdefault('SEED_MOCK_DATA', 'true')
os.environ.setdefault('DEMO_IN_MEMORY', 'true')
import uuid
from datetime import timedelta
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models import DOCUMENTS
from app.config import config
from app.services import bounds, rollup, today


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('TEST_MONGODB_URI'), reason='Real MongoDB not configured')
async def test_real_date_trunc_and_dedup(monkeypatch):
    from pymongo.errors import DuplicateKeyError
    c = config()
    monkeypatch.setattr(c, 'demo_in_memory', False)
    monkeypatch.setattr(c, 'seed_mock_data', False)
    client = AsyncIOMotorClient(os.environ['TEST_MONGODB_URI'], tz_aware=True)
    name = 'test_jannetra_' + uuid.uuid4().hex
    db = client[name]
    try:
        await init_beanie(database=db, document_models=DOCUMENTS)
        await db.platform_credentials.insert_one({'platform': 'x', 'mode': 'official', 'status': 'live'})
        start, _ = bounds(today())
        for i, time in enumerate([start - timedelta(seconds=1), start, start + timedelta(hours=1)]):
            await db.posts.insert_one({'platform': 'x', 'external_id': str(i), 'published_at': time,
                                      'demo': False, 'sentiment': {'label': 'negative'}})
        with pytest.raises(DuplicateKeyError):
            await db.posts.insert_one({'platform': 'x', 'external_id': '0'})
        await rollup(db)
        assert (await db.daily_aggregates.find_one({'date': today(), 'platform': 'overall'}))['negative_count'] == 2
    finally:
        # The test owns this random, explicitly prefixed database only.
        await client.drop_database(name)
        client.close()
