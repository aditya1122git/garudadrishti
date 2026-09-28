import asyncio
import csv
import io
import ipaddress
import socket
from contextlib import asynccontextmanager
from datetime import timedelta, date
from urllib.parse import urlparse
import bcrypt
import httpx
import jwt
from bson import ObjectId
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal
from reportlab.pdfgen import canvas
from .config import config
from .sentiment import classifier_status
from .models import DOCUMENTS, now, Platform, Label
from .services import KEYWORDS, PLATFORMS, today, bounds, settings, encrypt, audit, statuses, seed, sync


@asynccontextmanager
async def lifespan(app):
    c = config()
    if c.demo_in_memory:
        from mongomock_motor import AsyncMongoMockClient
        mongo = AsyncMongoMockClient(tz_aware=True)
    else:
        mongo = AsyncIOMotorClient(c.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=10000)
    # Separate demo database prevents fixture contamination of live collections.
    db = mongo[c.mongodb_database + ('_demo' if c.seed_mock_data else '')]
    if c.demo_in_memory:
        # Build disposable fixtures before mongomock indexes to avoid quadratic insert checks.
        await seed(db)
    await init_beanie(database=db, document_models=DOCUMENTS)
    app.state.db = db
    app.state.http = httpx.AsyncClient(timeout=30, follow_redirects=False)
    if not await db.users.find_one({'email': c.bootstrap_email}):
        hashed = await asyncio.to_thread(bcrypt.hashpw, c.bootstrap_password.encode(), bcrypt.gensalt())
        await db.users.insert_one(dict(email=c.bootstrap_email, hashed_password=hashed.decode(), role='admin'))
    for term in KEYWORDS:
        await db.tracked_keywords.update_one({'keyword': term}, {'$setOnInsert': {'keyword': term, 'is_active': True}}, upsert=True)
    await db.settings.update_one({'_id': 'main'}, {'$setOnInsert': {'threshold': 500, 'email': '', 'email_enabled': False, 'webhook_enabled': False}}, upsert=True)
    for p, key, account in [('x', c.x_bearer_token, ''), ('youtube', c.youtube_api_key, ''),
                             ('facebook', c.meta_access_token if c.meta_facebook_page_id else '', c.meta_facebook_page_id),
                             ('instagram', c.meta_access_token if c.meta_instagram_account_id else '', c.meta_instagram_account_id)]:
        if key and not c.seed_mock_data:
            await db.platform_credentials.update_one({'platform': p}, {'$setOnInsert': dict(platform=p, mode='official',
                encrypted_api_key=encrypt({'api_key': key, 'account_id': account}), status='pending', last_synced_at=None)}, upsert=True)
    if c.seed_mock_data:
        await seed(db)
        await sync(db, app.state.http)
    scheduler = AsyncIOScheduler(timezone=c.reporting_timezone)
    if c.scheduler_enabled:
        scheduler.add_job(sync, 'interval', minutes=c.sync_interval_minutes, args=[db, app.state.http], max_instances=1, coalesce=True,
                          next_run_time=now() + timedelta(seconds=10))
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await app.state.http.aclose()
    mongo.close()


app = FastAPI(title='JanNetra', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config().allowed_origins.split(','), allow_methods=['GET', 'POST', 'PUT'],
                   allow_headers=['Authorization', 'Content-Type'])
oauth = OAuth2PasswordBearer(tokenUrl='/api/auth/token')

@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

def db():
    return app.state.db

async def current_user(token: str = Depends(oauth)):
    try:
        claims = jwt.decode(token, config().jwt_secret, algorithms=['HS256'], audience='jannetra', issuer='jannetra')
        user = await db().users.find_one({'_id': ObjectId(claims['sub'])})
        if not user:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, 'Invalid or expired session', headers={'WWW-Authenticate': 'Bearer'})

async def admin(user=Depends(current_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required')
    return user

def serialize(value):
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    return str(value) if isinstance(value, ObjectId) else value

@app.get('/api/health')
async def health():
    await db().command('ping')
    return {'status': 'ok', 'demo': config().seed_mock_data}

@app.get('/api/auth/mode')
async def mode():
    return {'demo': config().seed_mock_data}

@app.post('/api/auth/token')
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    # Shared DB buckets survive restarts. Bound both account and client attempts.
    minute = now().strftime('%Y%m%d%H%M')
    for identity in [f'ip:{request.client.host}', f'account:{form.username.lower()}']:
        key = identity + ':' + minute
        from pymongo import ReturnDocument
        bucket = await db().login_limits.find_one_and_update({'_id': key}, {'$inc': {'count': 1}, '$set': {'expires_at': now() + timedelta(minutes=2)}},
            upsert=True, return_document=ReturnDocument.AFTER)
        if bucket['count'] > 10:
            raise HTTPException(429, 'Too many login attempts. Try again in a minute.')
    await db().login_limits.create_index('expires_at', expireAfterSeconds=0)
    user = await db().users.find_one({'email': form.username.lower()})
    valid = user and len(form.password.encode()) <= 72 and await asyncio.to_thread(bcrypt.checkpw, form.password.encode(), user['hashed_password'].encode())
    if not valid:
        raise HTTPException(401, 'Invalid email or password')
    token = jwt.encode({'sub': str(user['_id']), 'exp': now() + timedelta(minutes=60), 'iat': now(), 'aud': 'jannetra', 'iss': 'jannetra'},
                       config().jwt_secret, algorithm='HS256')
    await audit(db(), user, 'login')
    return {'access_token': token, 'token_type': 'bearer', 'role': user['role'], 'email': user['email']}

@app.get('/api/overview')
async def overview(platform: Platform | None = None, user=Depends(current_user)):
    sources = await statuses(db())
    usable = [s['platform'] for s in sources if s['status'] != 'disconnected']
    selected = [platform] if platform in usable else usable if platform is None else []
    rows = await db().daily_aggregates.find({'date': {'$gte': (date.fromisoformat(today()) - timedelta(days=29)).isoformat()},
                                          'platform': {'$in': selected}}, {'_id': 0}).to_list(None)
    grouped = {}
    for r in rows:
        out = grouped.setdefault(r['date'], dict(date=r['date'], positive_count=0, negative_count=0, neutral_count=0, total_count=0))
        for k in ['positive_count', 'negative_count', 'neutral_count', 'total_count']:
            out[k] += r[k]
    for v in grouped.values():
        v['negativity_index'] = round(v['negative_count'] / v['total_count'] * 100, 1) if v['total_count'] else 0
    prefs = await settings(db())
    pending = await db().posts.count_documents({'sentiment': None, 'platform': {'$in': selected}, 'demo': config().seed_mock_data})
    await audit(db(), user, 'view.overview', {'platform': platform})
    return serialize(dict(demo=config().seed_mock_data, date=today(), timezone=config().reporting_timezone,
        sources=sources, today=grouped.get(today()), trend=sorted(grouped.values(), key=lambda x: x['date']),
        platform_totals=[r for r in rows if r['date'] == today()], pending=pending, threshold=prefs['threshold'],
        classifier=classifier_status(),
        partial=any(s['status'] in ['unavailable', 'pending'] for s in sources if s['platform'] in selected),
        alerts=await db().alerts.find({'resolved': False}).sort('date', -1).limit(30).to_list(30)))

@app.get('/api/posts')
async def posts(q: str = Query('', max_length=200), platform: Platform | None = None, sentiment: Label | None = None,
                day: date | None = None, sort: Literal['recency', 'engagement'] = 'recency', page: int = Query(1, ge=1, le=10000), user=Depends(current_user)):
    import re
    connected = [s['platform'] for s in await statuses(db()) if s['status'] != 'disconnected']
    query = {'platform': platform if platform in connected else {'$in': connected if platform is None else []}, 'demo': config().seed_mock_data}
    if q:
        # Escaped substring supports Hindi and PK consistently; text index available for analytical queries.
        query['content'] = {'$regex': re.escape(q), '$options': 'i'}
    if sentiment:
        query['sentiment.label'] = sentiment
    if day:
        start, end = bounds(day.isoformat()); query['published_at'] = {'$gte': start, '$lt': end}
    rows = await db().posts.find(query).sort([('engagement_score' if sort == 'engagement' else 'published_at', -1), ('_id', -1)]).skip((page - 1) * 20).limit(20).to_list(20)
    await audit(db(), user, 'view.posts', {'platform': platform, 'sentiment': sentiment, 'page': page})
    return serialize({'items': rows, 'total': await db().posts.count_documents(query), 'page': page})

@app.get('/api/settings')
async def read_settings(user=Depends(current_user)):
    prefs = await settings(db())
    prefs.pop('webhook_secret', None)
    return serialize({**prefs, 'keywords': await db().tracked_keywords.find({}, {'_id': 0}).to_list(None),
                      'credentials': await db().platform_credentials.find({'platform': {'$in': PLATFORMS}}, {'encrypted_api_key': 0}).to_list(None),
                      'sources': await statuses(db()), 'model': config().hf_model, 'classifier': classifier_status()})

class Preferences(BaseModel):
    threshold: int = Field(ge=1, le=10000000)
    keywords: list[str] = Field(min_length=1, max_length=30)
    email: str = Field(default='', max_length=254)
    email_enabled: bool = False
    webhook_enabled: bool = False
    webhook_url: str = Field(default='', max_length=2048)

async def public_https(url):
    from .connectors import validate_destination, ProviderError
    try:
        await validate_destination(url)
    except (OSError, ValueError, ProviderError) as exc:
        raise HTTPException(422, str(exc))

@app.put('/api/settings')
async def update_settings(value: Preferences, user=Depends(admin)):
    if any(not k.strip() or len(k) > 100 for k in value.keywords):
        raise HTTPException(422, 'Keywords must contain 1–100 characters')
    if value.email_enabled and ('@' not in value.email or '\n' in value.email or '\r' in value.email):
        raise HTTPException(422, 'A valid email destination is required')
    old = await settings(db())
    if value.webhook_enabled and not value.webhook_url and not old.get('webhook_secret'):
        raise HTTPException(422, 'A webhook URL is required')
    data = value.model_dump(exclude={'keywords', 'webhook_url'})
    if value.webhook_url:
        await public_https(value.webhook_url)
        data['webhook_secret'] = encrypt({'url': value.webhook_url})
    await db().settings.update_one({'_id': 'main'}, {'$set': data})
    terms = list(dict.fromkeys(k.strip() for k in value.keywords))
    for term in terms:
        await db().tracked_keywords.update_one({'keyword': term}, {'$set': {'is_active': True}}, upsert=True)
    await db().tracked_keywords.update_many({'keyword': {'$nin': terms}}, {'$set': {'is_active': False}})
    await audit(db(), user, 'settings.update')
    return {'saved': True}

class CredentialInput(BaseModel):
    platform: Literal['facebook', 'instagram', 'x', 'youtube']
    mode: Literal['official', 'aggregator'] = 'official'
    api_key: str = Field(min_length=10, max_length=10000)
    account_id: str = ''
    endpoint: str = ''
    replacement_tokens: list[str] = Field(default_factory=list, max_length=5)

@app.put('/api/credentials')
async def credentials(value: CredentialInput, user=Depends(admin)):
    if config().seed_mock_data:
        raise HTTPException(409, 'Turn off demo mode before storing real credentials')
    if value.mode == 'aggregator':
        if value.platform not in ['facebook', 'instagram']:
            raise HTTPException(422, 'Aggregator mode is supported only for Meta platforms')
        await public_https(value.endpoint)
    elif value.platform in ['facebook', 'instagram'] and not value.account_id.isdigit():
        raise HTTPException(422, 'Owned/managed numeric account ID required')
    secret = {'api_key': value.api_key, 'account_id': value.account_id, 'endpoint': value.endpoint,
              'tokens': [value.api_key] + value.replacement_tokens}
    await db().platform_credentials.update_one({'platform': value.platform}, {'$set': dict(platform=value.platform, mode=value.mode,
        encrypted_api_key=encrypt(secret), status='pending', error=None)}, upsert=True)
    await audit(db(), user, 'credentials.rotate', {'platform': value.platform})
    return {'saved': True}

@app.post('/api/sync')
async def run_sync(user=Depends(admin)):
    await audit(db(), user, 'ingestion.request')
    await sync(db(), app.state.http)
    return {'complete': True}

@app.post('/api/alerts/{day}/resolve')
async def resolve(day: date, user=Depends(admin)):
    result = await db().alerts.update_one({'date': day.isoformat()}, {'$set': {'resolved': True}})
    if not result.matched_count:
        raise HTTPException(404, 'Alert not found')
    await audit(db(), user, 'alert.resolve', {'date': day.isoformat()})
    return {'resolved': True}

class NewUser(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=14, max_length=72)
    role: Literal['admin', 'viewer'] = 'viewer'

@app.post('/api/users', status_code=201)
async def add_user(value: NewUser, user=Depends(admin)):
    from pymongo.errors import DuplicateKeyError
    if '@' not in value.email or len(value.password.encode()) > 72:
        raise HTTPException(422, 'Valid email and password at most 72 bytes required')
    hashed = await asyncio.to_thread(bcrypt.hashpw, value.password.encode(), bcrypt.gensalt())
    try:
        await db().users.insert_one(dict(email=value.email.lower(), hashed_password=hashed.decode(), role=value.role))
    except DuplicateKeyError:
        raise HTTPException(409, 'User already exists')
    await audit(db(), user, 'user.create', {'email': value.email, 'role': value.role})
    return {'created': True}

@app.get('/api/export')
async def export(period: Literal['daily', 'weekly', 'monthly'] = 'daily', format: Literal['csv', 'pdf'] = 'csv', user=Depends(current_user)):
    count = {'daily': 1, 'weekly': 7, 'monthly': 30}[period]
    start = (date.fromisoformat(today()) - timedelta(days=count - 1)).isoformat()
    connected = [s['platform'] for s in await statuses(db()) if s['status'] != 'disconnected']
    rows = await db().daily_aggregates.find({'date': {'$gte': start, '$lte': today()}, 'platform': {'$in': connected}}, {'_id': 0}).sort([('date', 1), ('platform', 1)]).to_list(None)
    fields = ['date', 'platform', 'positive_count', 'negative_count', 'neutral_count', 'total_count', 'negativity_index']
    source_status = '; '.join(f'{s["platform"]}: {s["source"]}/{s["status"]}' for s in await statuses(db()))
    if format == 'csv':
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=fields + ['mode', 'source_status'], extrasaction='ignore'); writer.writeheader()
        writer.writerows([{**r, 'mode': 'DEMO' if config().seed_mock_data else 'LIVE', 'source_status': source_status} for r in rows])
        content = stream.getvalue().encode('utf-8-sig'); mime = 'text/csv'
    else:
        stream = io.BytesIO(); pdf = canvas.Canvas(stream, pagesize=(842, 595))
        def heading():
            pdf.setFont('Helvetica-Bold', 20); pdf.drawString(40, 550, 'JanNetra | Sentiment report' + (' | DEMO' if config().seed_mock_data else ''))
            pdf.setFont('Helvetica', 10); pdf.drawString(40, 525, f'{start} to {today()} | {config().reporting_timezone} | Negative / classified x 100')
            pdf.drawString(40, 507, source_status[:145]); pdf.drawString(40, 483, 'Date           Platform          Positive       Negative       Neutral        Total        Negativity %')
        heading(); y = 462
        for r in rows:
            if y < 50:
                pdf.showPage(); heading(); y = 462
            pdf.setFont('Courier', 10)
            pdf.drawString(40, y, f'{r["date"]}   {r["platform"]:12} {r["positive_count"]:8} {r["negative_count"]:12} {r["neutral_count"]:12} {r["total_count"]:10} {r["negativity_index"]:12.1f}')
            y -= 18
        pdf.save(); content = stream.getvalue(); mime = 'application/pdf'
    await audit(db(), user, 'export.' + format, {'period': period})
    return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="jannetra-{period}-{today()}.{format}"'})
