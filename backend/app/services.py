import asyncio
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
import aiosmtplib
from cryptography.fernet import Fernet
from pymongo.errors import DuplicateKeyError
from .config import config
from .models import now
from .connectors import x_posts, youtube_posts, meta_posts, aggregator_posts, request, validate_destination
from .sentiment import classifier

PLATFORMS = ['facebook', 'instagram', 'x', 'youtube']
KEYWORDS = ['Jan Suraaj Party', 'Prashant Kishore', 'PK', 'जन सुराज', 'प्रशांत किशोर', '#JanSuraaj', '#PrashantKishore']

def today():
    return now().astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat()

def bounds(day):
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(config().reporting_timezone))
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)

def encrypt(value):
    return Fernet(config().encryption_key.encode()).encrypt(json.dumps(value).encode()).decode()

def decrypt(value):
    return json.loads(Fernet(config().encryption_key.encode()).decrypt(value.encode()))

async def settings(db):
    return await db.settings.find_one({'_id': 'main'}) or {'threshold': 500, 'email': '', 'webhook_enabled': False, 'email_enabled': False}

async def audit(db, user, action, meta=None):
    await db.audit_logs.insert_one(dict(user_id=str(user['_id']), action=action, timestamp=now(), meta=meta or {}))

async def statuses(db):
    credentials = {c['platform']: c async for c in db.platform_credentials.find({}, {'encrypted_api_key': 0})}
    result = []
    for p in PLATFORMS:
        c = credentials.get(p)
        if config().seed_mock_data and p in ['x', 'youtube']:
            result.append(dict(platform=p, source='Demo', status='demo', last_synced_at=now()))
        elif c:
            result.append(dict(platform=p, source='Third-party aggregator' if c['mode'] == 'aggregator' else 'Live API',
                               status=c.get('status', 'pending'), last_synced_at=c.get('last_synced_at'), error=c.get('error')))
        else:
            result.append(dict(platform=p, source='Not connected', status='disconnected', last_synced_at=None))
    return result

async def rollup(db):
    connected = [s['platform'] for s in await statuses(db) if s['status'] != 'disconnected']
    start = now() - timedelta(days=35)
    match = {'published_at': {'$gte': start}, 'platform': {'$in': connected}, 'sentiment': {'$ne': None}, 'demo': config().seed_mock_data}
    if config().demo_in_memory:
        # mongomock has no $dateTrunc. Only the explicit disposable demo uses this branch.
        grouped = defaultdict(lambda: dict(positive_count=0, negative_count=0, neutral_count=0, total_count=0))
        async for p in db.posts.find(match):
            day = p['published_at'].astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat()
            g = grouped[(day, p['platform'])]
            g[p['sentiment']['label'] + '_count'] += 1; g['total_count'] += 1
        rows = [dict(date=k[0], platform=k[1], **v) for k, v in grouped.items()]
    else:
        pipeline = [{'$match': match}, {'$group': {
            '_id': {'date': {'$dateTrunc': {'date': '$published_at', 'unit': 'day', 'timezone': config().reporting_timezone}}, 'platform': '$platform'},
            **{label + '_count': {'$sum': {'$cond': [{'$eq': ['$sentiment.label', label]}, 1, 0]}} for label in ['positive', 'negative', 'neutral']},
            'total_count': {'$sum': 1}}}]
        raw = await db.posts.aggregate(pipeline).to_list(None)
        rows = [dict(date=r['_id']['date'].astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat(),
                     platform=r['_id']['platform'], **{k: v for k, v in r.items() if k != '_id'}) for r in raw]
    overall = defaultdict(lambda: dict(positive_count=0, negative_count=0, neutral_count=0, total_count=0))
    for row in rows:
        for k in overall[row['date']]:
            overall[row['date']][k] += row[k]
    rows += [dict(date=d, platform='overall', **v) for d, v in overall.items()]
    for row in rows:
        row['negativity_index'] = round(row['negative_count'] / row['total_count'] * 100, 1) if row['total_count'] else 0
        await db.daily_aggregates.update_one({'date': row['date'], 'platform': row['platform']}, {'$set': {**row, 'schema_version': 1}}, upsert=True)

async def create_alert(db, day):
    prefs = await settings(db)
    row = await db.daily_aggregates.find_one({'date': day, 'platform': 'overall'})
    if not row or row['negative_count'] <= prefs['threshold']:
        return
    start, end = bounds(day)
    connected = [s['platform'] for s in await statuses(db) if s['status'] != 'disconnected']
    top = await db.posts.find({'published_at': {'$gte': start, '$lt': end}, 'sentiment.label': 'negative',
                              'platform': {'$in': connected}, 'demo': config().seed_mock_data}).sort('engagement_score', -1).limit(5).to_list(5)
    for p in top:
        p['_id'] = str(p['_id'])
    breakdown = {r['platform']: r['negative_count'] async for r in db.daily_aggregates.find({'date': day, 'platform': {'$in': connected}})}
    try:
        await db.alerts.update_one({'date': day}, {'$setOnInsert': dict(schema_version=1, date=day, threshold=prefs['threshold'],
                                  triggered_at=now(), notified_channels=[], resolved=False),
                                  '$set': dict(negative_count=row['negative_count'], top_negative_posts=top, platform_breakdown=breakdown)}, upsert=True)
    except DuplicateKeyError:
        pass

async def notify_alerts(db, client):
    if config().seed_mock_data:
        return  # Synthetic records must never send external notifications.
    prefs = await settings(db)
    async for alert in db.alerts.find({'resolved': False}):
        payload = dict(date=alert['date'], negative_count=alert['negative_count'], threshold=alert['threshold'],
                       platform_breakdown=alert['platform_breakdown'], top_negative_posts=alert['top_negative_posts'])
        body = json.dumps(payload, default=str, ensure_ascii=False)
        for channel in ['email', 'webhook']:
            if not prefs.get(channel + '_enabled') or channel in alert.get('notified_channels', []):
                continue
            # Single-process scheduler plus an atomic lease protects manual and scheduled retries.
            claim = await db.alerts.update_one({'_id': alert['_id'], 'notified_channels': {'$ne': channel},
                '$or': [{f'leases.{channel}': {'$exists': False}}, {f'leases.{channel}': {'$lt': now()}}]},
                {'$set': {f'leases.{channel}': now() + timedelta(minutes=5)}})
            if not claim.modified_count:
                continue
            try:
                if channel == 'webhook':
                    url = decrypt(prefs['webhook_secret'])['url']
                    await validate_destination(url)
                    await request(client, 'POST', url, json=json.loads(body), response_json=False,
                                  headers={'Idempotency-Key': f'jannetra:{alert["date"]}'})
                elif config().sendgrid_api_key:
                    response = await client.post('https://api.sendgrid.com/v3/mail/send', headers={'Authorization': f'Bearer {config().sendgrid_api_key}'},
                        json={'personalizations': [{'to': [{'email': prefs['email']}]}], 'from': {'email': config().smtp_from},
                              'subject': f'JanNetra alert • {alert["date"]}', 'content': [{'type': 'text/plain', 'value': body}]})
                    response.raise_for_status()
                else:
                    message = EmailMessage(); message['From'] = config().smtp_from; message['To'] = prefs['email']
                    message['Subject'] = f'JanNetra alert • {alert["date"]}'
                    message['Message-ID'] = f'<jannetra-{alert["date"]}@{config().smtp_from.split("@")[-1]}>'
                    message.set_content(body)
                    await aiosmtplib.send(message, hostname=config().smtp_host, port=config().smtp_port,
                                          username=config().smtp_username or None, password=config().smtp_password or None, start_tls=True)
                await db.alerts.update_one({'_id': alert['_id']}, {'$addToSet': {'notified_channels': channel}, '$unset': {f'notification_errors.{channel}': ''}})
            except Exception:
                await db.alerts.update_one({'_id': alert['_id']}, {'$set': {f'notification_errors.{channel}': 'Delivery failed; retry scheduled'}})

_sync_lock = asyncio.Lock()

async def sync(db, client):
    if _sync_lock.locked():
        return
    async with _sync_lock:
        if not config().seed_mock_data:
            keywords = [k['keyword'] async for k in db.tracked_keywords.find({'is_active': True})]
            if keywords:
                async for c in db.platform_credentials.find({'platform': {'$in': PLATFORMS}}):
                    p = c['platform']
                    # Search quota budget: YouTube once every 2 hours, other providers per scheduler interval.
                    if p == 'youtube' and c.get('last_attempt_at') and now() - c['last_attempt_at'] < timedelta(hours=2):
                        continue
                    started = now()
                    await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': {'last_attempt_at': started}})
                    try:
                        secret = decrypt(c['encrypted_api_key'])
                        since = c.get('last_synced_at') or now() - timedelta(hours=24)
                        since -= timedelta(minutes=5)  # deliberate overlap; compound unique index deduplicates
                        if c['mode'] == 'aggregator':
                            rows = await aggregator_posts(client, p, secret, keywords, since)
                        elif p == 'x':
                            rows = await x_posts(client, secret, keywords, since)
                        elif p == 'youtube':
                            rows = await youtube_posts(client, secret, keywords, since)
                        else:
                            rows = await meta_posts(client, p, secret, keywords, since)
                        for row in rows:
                            await db.posts.update_one({'platform': p, 'external_id': row['external_id']}, {'$setOnInsert': row}, upsert=True)
                        await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': {'last_synced_at': started,
                            'status': 'live', 'error': None, 'encrypted_api_key': encrypt(secret)}})
                    except Exception as exc:
                        await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': {'status': 'unavailable',
                            'error': str(exc) if isinstance(exc, RuntimeError) else 'Connection failed; check configuration'}})
            engine = classifier()
            try:
                posts = await db.posts.find({'sentiment': None, 'demo': False}).limit(200).to_list(200)
                size = config().hf_batch_size
                for offset in range(0, len(posts), size):
                    batch = posts[offset:offset + size]
                    results = await engine.classify([p['content'] for p in batch])
                    for p, r in zip(batch, results, strict=True):
                        await db.posts.update_one({'_id': p['_id'], 'sentiment': None}, {'$set': {'sentiment': dict(
                            label=r.sentiment, confidence=r.confidence, reason=r.reason,
                            model_used=engine.provenance, classified_at=now())}})
            except Exception:
                # Classifier exposes failure state; pending posts are retried next sync.
                pass
        await rollup(db)
        # Include late-arriving posts from previous reporting days.
        async for day in db.daily_aggregates.find({'platform': 'overall'}):
            await create_alert(db, day['date'])
        await notify_alerts(db, client)

async def seed(db):
    if await db.posts.count_documents({'demo': True}):
        return
    rng = random.Random(20260928)
    texts = {
        'positive': ['जन सुराज की शिक्षा पर चर्चा अच्छी लगी। अब काम होते देखना है।', 'Prashant Kishore is asking the right questions about jobs in Bihar.', 'Jan Suraaj Party ki local meeting mein achhi discussion hui.'],
        'negative': ['Jan Suraaj Party needs a clearer jobs plan. Promises alone are not enough.', 'प्रशांत किशोर की बातों में जमीन पर काम की स्पष्ट योजना कहाँ है?', 'PK ki rally mein sawaal zyada, jawaab kam. Bihar needs specifics.'],
        'neutral': ['Prashant Kishore addressed a public meeting today. Full discussion to follow.', 'जन सुराज की अगली बैठक रविवार को आयोजित होगी।', 'Jan Suraaj Party: a summary of today’s education policy discussion.']}
    docs = []
    day0 = datetime.fromisoformat(today()).date()
    for offset in range(30):
        day = (day0 - timedelta(days=offset)).isoformat(); start, end = bounds(day)
        for platform in ['x', 'youtube']:
            count = (1080 if platform == 'x' else 570) if offset == 0 else rng.randint(260, 560)
            for i in range(count):
                label = rng.choices(['positive', 'negative', 'neutral'], [34, 42 if offset == 0 else 24 + offset % 9, 24])[0]
                eng = dict(likes=rng.randint(0, 980), comments=rng.randint(0, 180), shares=rng.randint(0, 240), views=rng.randint(300, 18000))
                available_seconds = max(1, int((min(end, now()) - start).total_seconds()))
                docs.append(dict(schema_version=1, platform=platform, external_id=f'demo-{day}-{platform}-{i}',
                                 author=f'Sample analyst {i % 80 + 1:02d}', content=rng.choice(texts[label]), url='',
                                 published_at=start + timedelta(seconds=rng.randrange(available_seconds)), engagement=eng,
                                 engagement_score=eng['likes'] + eng['comments'] + eng['shares'], ingested_at=now(), demo=True,
                                 sentiment=dict(label=label, confidence=round(rng.uniform(.59, .98), 2), reason='Synthetic demonstration label', model_used='demo-fixture', classified_at=now())))
    await db.posts.insert_many(docs)
