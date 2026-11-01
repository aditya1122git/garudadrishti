import asyncio
import json
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from pymongo.errors import DuplicateKeyError
from .config import config, DEFAULT_AUTOMATION_START_HOUR, DEFAULT_AUTOMATION_END_HOUR
from .models import now
from .connectors import BIHAR_DISCOVERY_TERMS, apify_posts, google_news_posts, youtube_posts, request
from .sentiment import classifier

YOUTUBE_CONTENT_SCOPE = 'youtube-title-description-v3'
YOUTUBE_SEARCH_STRATEGY = 'keyword-title-description-v4'
YOUTUBE_CLASSIFICATION_DESCRIPTION_CHARS = 1200
POST_SCOPE = {'$or': [{'platform': {'$ne': 'youtube'}}, {'demo': True}, {'content_scope': YOUTUBE_CONTENT_SCOPE}]}

PLATFORMS = ['facebook', 'instagram', 'x', 'youtube', 'news', 'reddit']
TRACKING_SCOPE_VERSION = 'samrat-bihar-bjp-government-v3'
DEFAULT_KEYWORD_VARIANTS = [
    'Samrat Chaudhary', 'BJP Bihar', 'Bihar Bharatiya Janata Party',
    'Government of Bihar', '#SamratChoudhary', '#BJP4Bihar', '#BiharGovernment',
]
DEFAULT_X_USERNAMES = [
    'ANI', 'Live_Cities', 'aajtak', 'News18Bihar', 'PoliceBhagalpur',
    'ANI_HindiNews', 'ians_india', 'IndianExpress', 'BIHARSS1', 'ZeeBiharNews',
    'dmbhagalpur', 'moliticsindia', 'ChapraZila', 'Hinduspirit0', 'TV9Bharatvarsh',
    'IANSKhabar', 'amitvikram', 'BiharInfraTales', 'INCBihar', 'SadanJee',
    'PurneaTimes', 'BhagalpurIndex', 'Bharat24Liv', 'naugachiapolice', 'The_Banka_Index',
]
MONITORING_PROJECTS = {
    'bhagalpur-division': {
        'label': 'BHAGALPUR DIVISION (Headquarters: Bhagalpur)',
        'keywords': [
            'Bhagalpur Division', 'Bhagalpur', 'भागलपुर', 'भागलपुर प्रमंडल',
            'Bhagalpur Commissioner', 'Bhagalpur DM', 'Bhagalpur Administration',
            'Bhagalpur News', 'Bhagalpur Development', 'Bhagalpur Police',
            'Banka', 'बांका', 'भागलपुर मंडल', 'Bhagalpur District',
            'Bhagalpur Smart City', 'Bhagalpur Municipal Corporation',
            'Bhagalpur Nagar Nigam', 'Bhagalpur Traffic', 'Bhagalpur Airport',
            'Bhagalpur University', 'Tilka Manjhi Bhagalpur University',
            'Bhagalpur Flood', 'Bhagalpur Crime', 'Bhagalpur Infrastructure',
            'Banka District', 'Banka News', 'Banka Administration', 'Banka Police',
            'भागलपुर जिला', 'भागलपुर प्रशासन', 'भागलपुर पुलिस', 'भागलपुर विकास',
            'भागलपुर समाचार', 'बांका जिला', 'बांका प्रशासन', 'बांका पुलिस',
            '#Bhagalpur', '#BhagalpurNews', '#Banka', '#भागलपुर',
        ],
    },
    'bihar-cm-qrt': {
        'label': 'Bihar CM QRT',
        'keywords': [
            'Bihar CM QRT', 'CM QRT Bihar', 'Bihar Chief Minister', 'Bihar CM Office',
            'मुख्यमंत्री बिहार', 'मुख्यमंत्री कार्यालय', 'CM Helpline Bihar',
            'Bihar CM Action', 'Bihar Government Action', 'CM Public Grievance',
            'जन शिकायत बिहार', 'जनता दरबार', 'मुख्यमंत्री जनता दरबार',
            'Bihar Emergency Response', 'CMO Bihar', 'Bihar CMO',
            'Chief Minister Office Bihar', 'Bihar CM Helpline 181',
            'Bihar CM Complaint', 'Bihar CM Grievance', 'Bihar CM Review Meeting',
            'Bihar Cabinet Decision', 'Bihar Government Decision',
            'Bihar Government Scheme', 'Bihar Public Grievance',
            'मुख्यमंत्री सचिवालय बिहार', 'मुख्यमंत्री हेल्पलाइन बिहार',
            'मुख्यमंत्री शिकायत बिहार', 'लोक शिकायत बिहार', 'बिहार कैबिनेट फैसला',
            'बिहार सरकार कार्रवाई', '#BiharCM', '#CMOBihar', '#JantaDarbar',
        ],
    },
    'district-munger': {
        'label': 'District Munger',
        'keywords': [
            'Munger', 'मुंगेर', 'Munger News', 'Munger District',
            'Munger Administration', 'Munger DM', 'Munger Police', 'Munger Development',
            'Munger Crime', 'Munger Infrastructure', 'Munger Railway', 'Munger University',
            'मुंगेर जिला', 'मुंगेर प्रशासन', 'मुंगेर पुलिस', 'Munger Division',
            'Munger Commissioner', 'Munger Municipal Corporation',
            'Munger Nagar Nigam', 'Munger Traffic', 'Munger Hospital',
            'Munger Flood', 'Munger Education', 'Jamalpur Bihar',
            'Jamalpur Railway', 'Haveli Kharagpur', 'Tarapur Munger',
            'मुंगेर प्रमंडल', 'मुंगेर विकास', 'मुंगेर समाचार', 'मुंगेर अपराध',
            'जमालपुर बिहार', 'हवेली खड़गपुर', 'तारापुर मुंगेर',
            '#Munger', '#MungerNews', '#मुंगेर',
        ],
    },
    'magadh-division': {
        'label': 'MAGADH DIVISION (Headquarters: Gaya)',
        'keywords': [
            'Magadh Division', 'मगध प्रमंडल', 'Gaya', 'गया', 'Nawada', 'नवादा',
            'Aurangabad Bihar', 'औरंगाबाद बिहार', 'Jehanabad', 'जहानाबाद',
            'Arwal', 'अरवल', 'Magadh Commissioner', 'Gaya DM',
            'Magadh Development', 'Magadh News', 'मगध विकास', 'Magadh Administration',
            'Magadh Police', 'Magadh Infrastructure', 'Gaya District',
            'Gaya Administration', 'Gaya Police', 'Gaya Development', 'Gaya News',
            'Bodh Gaya', 'Nawada District', 'Nawada Administration', 'Nawada Police',
            'Aurangabad Bihar District', 'Aurangabad Bihar Police',
            'Jehanabad District', 'Jehanabad Police', 'Arwal District', 'Arwal Police',
            'मगध प्रशासन', 'मगध समाचार', 'गया जिला', 'गया प्रशासन', 'गया पुलिस',
            'बोधगया', 'नवादा प्रशासन', 'औरंगाबाद प्रशासन', 'जहानाबाद प्रशासन',
            'अरवल प्रशासन', '#Magadh', '#Gaya', '#BodhGaya', '#मगध',
        ],
    },
    'patna-division': {
        'label': 'Patna Division (Headquarters: Patna)',
        'keywords': [
            'Patna Division', 'पटना प्रमंडल', 'Patna', 'पटना', 'Nalanda', 'नालंदा',
            'Bhojpur', 'भोजपुर', 'Buxar', 'बक्सर', 'Rohtas', 'रोहतास',
            'Kaimur', 'कैमूर', 'Patna Commissioner', 'Patna Administration',
            'Patna DM', 'Patna Development', 'पटना प्रशासन', 'पटना विकास',
            'Patna District', 'Patna Police', 'Patna Traffic Police',
            'Patna Municipal Corporation', 'Patna Nagar Nigam', 'Patna Smart City',
            'Patna Infrastructure', 'Patna Metro', 'Patna Airport', 'Patna News',
            'Nalanda District', 'Nalanda Administration', 'Nalanda Police',
            'Bhojpur District', 'Bhojpur Administration', 'Bhojpur Police',
            'Buxar District', 'Buxar Administration', 'Buxar Police',
            'Rohtas District', 'Rohtas Administration', 'Rohtas Police',
            'Kaimur District', 'Kaimur Administration', 'Kaimur Police',
            'पटना जिला', 'पटना पुलिस', 'पटना नगर निगम', 'पटना मेट्रो',
            '#Patna', '#PatnaNews', '#PatnaPolice', '#पटना',
        ],
    },
    'samrat-choudhary': {
        'label': 'Samrat Choudhary Ji',
        'keywords': [
            'Samrat Choudhary', 'सम्राट चौधरी', 'Samrat Chaudhary',
            'Samrat Choudhary Ji', 'सम्राट चौधरी जी', 'Samrat Choudhary News',
            'Samrat Choudhary Speech', 'Samrat Choudhary Announcement',
            'Samrat Choudhary Statement', 'Samrat Choudhary Rally',
            'Samrat Choudhary Meeting', 'Samrat Choudhary Bihar',
            'सम्राट चौधरी बयान', 'सम्राट चौधरी घोषणा', 'सम्राट चौधरी प्रेस कॉन्फ्रेंस',
            'Samrat Choudhary Interview', 'Samrat Choudhary Press Conference',
            'Samrat Choudhary Latest News', 'Samrat Choudhary BJP',
            'Samrat Choudhary Deputy CM', 'Samrat Choudhary Bihar BJP',
            'Samrat Chaudhary Bihar', 'Samrat Chaudhary News',
            'Bihar Deputy CM Samrat Choudhary', 'Deputy CM Bihar Samrat Choudhary',
            'Bihar Dy CM Samrat Choudhary', 'Deputy Chief Minister Samrat Choudhary',
            'सम्राट चौधरी भाषण', 'सम्राट चौधरी रैली', 'सम्राट चौधरी बैठक',
            'सम्राट चौधरी इंटरव्यू', 'उपमुख्यमंत्री सम्राट चौधरी',
            'बिहार के उपमुख्यमंत्री सम्राट चौधरी', '@samratchoudhary',
            '#SamratChoudhary', '#SamratChaudhary', '#सम्राटचौधरी',
        ],
    },
    'tirhut-division': {
        'label': 'TIRHUT DIVISION (Headquarters: Muzaffarpur)',
        'keywords': [
            'Tirhut Division', 'तिरहुत प्रमंडल', 'Muzaffarpur', 'मुजफ्फरपुर',
            'Vaishali', 'वैशाली', 'Sitamarhi', 'सीतामढ़ी', 'Sheohar', 'शिवहर',
            'East Champaran', 'पूर्वी चंपारण', 'Motihari', 'मोतिहारी',
            'West Champaran', 'पश्चिमी चंपारण', 'Bettiah', 'बेतिया',
            'Tirhut Commissioner', 'Tirhut Development', 'Tirhut News', 'तिरहुत विकास',
            'Tirhut Administration', 'Tirhut Police', 'Tirhut Infrastructure',
            'Muzaffarpur District', 'Muzaffarpur Administration',
            'Muzaffarpur DM', 'Muzaffarpur Police', 'Muzaffarpur Development',
            'Muzaffarpur News', 'Vaishali District', 'Vaishali Police',
            'Hajipur Bihar', 'Sitamarhi District', 'Sitamarhi Police',
            'Sheohar District', 'Sheohar Police', 'East Champaran District',
            'Motihari Administration', 'Motihari Police', 'West Champaran District',
            'Bettiah Administration', 'Bettiah Police', 'तिरहुत प्रशासन',
            'तिरहुत समाचार', 'मुजफ्फरपुर जिला', 'मुजफ्फरपुर प्रशासन',
            'मुजफ्फरपुर पुलिस', 'वैशाली प्रशासन', 'हाजीपुर बिहार',
            'सीतामढ़ी प्रशासन', 'मोतिहारी प्रशासन', 'बेतिया प्रशासन',
            '#Tirhut', '#Muzaffarpur', '#Motihari', '#Bettiah', '#तिरहुत',
        ],
    },
}
MONITORING_PROJECTS = {
    'all': {
        'label': 'All projects',
        'keywords': list(dict.fromkeys(
            keyword
            for project in MONITORING_PROJECTS.values()
            for keyword in project['keywords']
        )),
    },
    **MONITORING_PROJECTS,
}
DEFAULT_MONITORING_PROJECT = 'bhagalpur-division'
KEYWORDS = [
    *BIHAR_DISCOVERY_TERMS,
    'Samrat Choudhary', 'Bihar BJP', 'Bharatiya Janata Party Bihar',
    'Bihar Government', 'Bihar Govt', 'सम्राट चौधरी', 'बिहार भाजपा', 'भाजपा बिहार',
    'बिहार सरकार', '#BiharBJP', '#SamratChaudhary', '#BiharGovt',
    'NDA', 'NDA Bihar', 'BJP NDA', 'एनडीए',
    '#NDA', '#NDAAlliance', '#NDABihar', '#BJPNDA', '#भाजपाएनडीए', '#एनडीए',
]


def _text_for_classification(post_row):
    """Use source text only; ignore any legacy enrichment appended to content."""
    if post_row.get('platform') in {'facebook', 'instagram', 'x', 'reddit'} and 'caption' in post_row:
        return str(post_row.get('caption') or '')
    if post_row.get('platform') == 'youtube':
        title = ' '.join(str(post_row.get('title') or '').split())
        description = ' '.join(str(post_row.get('description') or '').split())
        if title or description:
            if len(description) > YOUTUBE_CLASSIFICATION_DESCRIPTION_CHARS:
                description = description[:YOUTUBE_CLASSIFICATION_DESCRIPTION_CHARS].rsplit(' ', 1)[0].rstrip()
                description += '…'
            return f'{title}\n{description}'.strip()
    return str(post_row.get('content') or '')


def analytics_platforms():
    """Platforms whose stored posts belong in historical analytics."""
    enabled = {value.strip() for value in config().enabled_platforms.split(',')}
    return [platform for platform in PLATFORMS if platform in enabled]


def today():
    return now().astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat()

def bounds(day):
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(config().reporting_timezone))
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def within_automation_window(value=None, start_hour=None, end_hour=None):
    """Return true during the inclusive operating hours."""
    local = (value or now()).astimezone(ZoneInfo(config().reporting_timezone))
    start = DEFAULT_AUTOMATION_START_HOUR if start_hour is None else start_hour
    end = DEFAULT_AUTOMATION_END_HOUR if end_hour is None else end_hour
    return start <= local.hour <= end

def encrypt(value):
    return Fernet(config().encryption_key.encode()).encrypt(json.dumps(value).encode()).decode()

def decrypt(value):
    return json.loads(Fernet(config().encryption_key.encode()).decrypt(value.encode()))

async def settings(db):
    return await db.settings.find_one({'_id': 'main'}) or {
        'threshold': 500,
        'x_usernames': [],
        'active_project': DEFAULT_MONITORING_PROJECT,
        'automation_start_hour': DEFAULT_AUTOMATION_START_HOUR,
        'automation_end_hour': DEFAULT_AUTOMATION_END_HOUR,
    }

async def audit(db, user, action, meta=None):
    await db.audit_logs.insert_one(dict(user_id=str(user['_id']), action=action, timestamp=now(), meta=meta or {}))

async def statuses(db):
    credentials = {c['platform']: c async for c in db.platform_credentials.find({}, {'encrypted_api_key': 0})}
    result = []
    for p in PLATFORMS:
        c = credentials.get(p) if p in config().enabled_platforms.split(',') else None
        if config().seed_mock_data and p in ['x', 'youtube']:
            result.append(dict(platform=p, source='Demo', status='demo', last_synced_at=now()))
        elif c:
            source = {
                'news': 'Google News RSS',
                'apify': 'Apify Actor',
            }.get(p if p == 'news' else c.get('mode'), 'Live API')
            result.append(dict(platform=p, source=source,
                               status=c.get('status', 'pending'), last_synced_at=c.get('last_synced_at'),
                               error=c.get('error')))
        else:
            result.append(dict(platform=p, source='Not connected', status='disconnected', last_synced_at=None))
    return result

async def rollup(db):
    included = analytics_platforms()
    start = now() - timedelta(days=35)
    match = {**POST_SCOPE, 'published_at': {'$gte': start}, 'platform': {'$in': included}, 'sentiment': {'$ne': None}, 'demo': config().seed_mock_data}
    if config().demo_in_memory:
        # mongomock has no $dateTrunc. Only the explicit disposable demo uses this branch.
        grouped = defaultdict(lambda: dict(positive_count=0, negative_count=0, neutral_count=0, mixed_count=0, total_count=0))
        async for p in db.posts.find(match):
            day = p['published_at'].astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat()
            g = grouped[(day, p['platform'])]
            g[p['sentiment']['label'] + '_count'] += 1; g['total_count'] += 1
        rows = [dict(date=k[0], platform=k[1], **v) for k, v in grouped.items()]
    else:
        pipeline = [{'$match': match}, {'$group': {
            '_id': {'date': {'$dateTrunc': {'date': '$published_at', 'unit': 'day', 'timezone': config().reporting_timezone}}, 'platform': '$platform'},
            **{label + '_count': {'$sum': {'$cond': [{'$eq': ['$sentiment.label', label]}, 1, 0]}} for label in ['positive', 'negative', 'neutral', 'mixed']},
            'total_count': {'$sum': 1}}}]
        raw = await db.posts.aggregate(pipeline).to_list(None)
        rows = [dict(date=r['_id']['date'].astimezone(ZoneInfo(config().reporting_timezone)).date().isoformat(),
                     platform=r['_id']['platform'], **{k: v for k, v in r.items() if k != '_id'}) for r in raw]
    overall = defaultdict(lambda: dict(positive_count=0, negative_count=0, neutral_count=0, mixed_count=0, total_count=0))
    for row in rows:
        for k in overall[row['date']]:
            overall[row['date']][k] += row[k]
    rows += [dict(date=d, platform='overall', **v) for d, v in overall.items()]
    for row in rows:
        row['negativity_index'] = round(row['negative_count'] / row['total_count'] * 100, 1) if row['total_count'] else 0
        await db.daily_aggregates.update_one({'date': row['date'], 'platform': row['platform']}, {'$set': {**row, 'schema_version': 1, 'content_scope': YOUTUBE_CONTENT_SCOPE}}, upsert=True)

async def create_alert(db, day):
    prefs = await settings(db)
    row = await db.daily_aggregates.find_one({'date': day, 'platform': 'overall'})
    if not row or row['negative_count'] <= prefs['threshold']:
        return
    start, end = bounds(day)
    included = analytics_platforms()
    top = await db.posts.find({**POST_SCOPE, 'published_at': {'$gte': start, '$lt': end}, 'sentiment.label': 'negative',
                              'platform': {'$in': included}, 'demo': config().seed_mock_data}).sort('engagement_score', -1).limit(5).to_list(5)
    for p in top:
        p['_id'] = str(p['_id'])
    breakdown = {r['platform']: r['negative_count'] async for r in db.daily_aggregates.find({'date': day, 'platform': {'$in': included}})}
    try:
        await db.alerts.update_one({'date': day}, {'$setOnInsert': dict(schema_version=1, date=day, threshold=prefs['threshold'],
                                  triggered_at=now(), notified_channels=[], resolved=False),
                                  '$set': dict(negative_count=row['negative_count'], top_negative_posts=top, platform_breakdown=breakdown,
                                               content_scope=YOUTUBE_CONTENT_SCOPE)}, upsert=True)
    except DuplicateKeyError:
        pass


def _telegram_link_label(platform: object) -> str:
    key = str(platform or '').strip().lower()
    return {
        'facebook': 'View on Facebook',
        'instagram': 'View on Instagram',
        'x': 'View on X',
        'youtube': 'View on YouTube',
        'news': 'View on News',
        'reddit': 'View on Reddit',
    }.get(key, 'View original post')


def _telegram_recipients(settings_obj) -> list[str]:
    """Return unique Telegram targets from a comma/space-separated env value."""
    values = (str(getattr(settings_obj, 'telegram_chat_id', '') or ''),)
    recipients = []
    for value in values:
        for chat_id in re.split(r'[,;\s]+', value.strip()):
            if chat_id and chat_id not in recipients:
                recipients.append(chat_id)
    return recipients


async def notify_negative_posts(db, client):
    """Send one idempotent Telegram message for every newly classified negative post."""
    c = config()
    prefs = await settings(db)
    recipients = _telegram_recipients(c)
    if (c.seed_mock_data or not c.telegram_bot_token or not recipients
            or not within_automation_window(
                start_hour=prefs.get('automation_start_hour', DEFAULT_AUTOMATION_START_HOUR),
                end_hour=prefs.get('automation_end_hour', DEFAULT_AUTOMATION_END_HOUR))):
        return
    start, end = bounds(today())
    await db.posts.update_many({
        'telegram_notification.status': {'$in': ['pending', 'failed']},
        '$or': [{'published_at': {'$lt': start}}, {'published_at': {'$gte': end}}],
    }, {'$set': {'telegram_notification.status': 'skipped',
                 'telegram_notification.error': 'Only posts published today are alerted'}})
    query = {'sentiment.label': 'negative', 'demo': False,
             'published_at': {'$gte': start, '$lt': end},
             'telegram_notification.status': {'$in': ['pending', 'failed']}}
    async for post_row in db.posts.find(query).sort('published_at', 1).limit(100):
        claim = await db.posts.update_one({
            '_id': post_row['_id'],
            'telegram_notification.status': {'$in': ['pending', 'failed']},
            '$or': [{'telegram_notification.lease_until': {'$exists': False}},
                    {'telegram_notification.lease_until': {'$lt': now()}}],
        }, {'$set': {'telegram_notification.status': 'sending',
                     'telegram_notification.lease_until': now() + timedelta(minutes=5)}})
        if not claim.modified_count:
            continue
        url = str(post_row.get('url') or '').strip()
        if not url.startswith(('https://', 'http://')):
            await db.posts.update_one({'_id': post_row['_id']}, {'$set': {
                'telegram_notification.status': 'skipped',
                'telegram_notification.error': 'Source post link unavailable'}})
            continue
        sentiment = post_row.get('sentiment') or {}
        confidence = round(float(sentiment.get('confidence', 0)) * 100)
        content = ' '.join(str(post_row.get('content') or '').split())[:800]
        platform = str(post_row.get('platform') or 'unknown')
        link_label = _telegram_link_label(platform)
        message = (f'<b>🚨 SamratChoudhary Ji negative post</b>\n\n'
                   f'<b>Platform:</b> {html_escape(platform.title())}\n'
                   f'<b>Author:</b> {html_escape(str(post_row.get("author") or "Unknown"))}\n'
                   f'<b>Confidence:</b> {confidence}%\n\n'
                   f'{html_escape(content)}\n\n'
                   f'<a href="{html_escape(url, quote=True)}">{link_label}</a>')
        already_sent = set((post_row.get('telegram_notification') or {}).get('sent_chat_ids') or [])
        failed = False
        for chat_id in recipients:
            if chat_id in already_sent:
                continue
            try:
                response = await request(client, 'POST',
                    f'https://api.telegram.org/bot{c.telegram_bot_token}/sendMessage',
                    json={'chat_id': chat_id, 'text': message,
                          'parse_mode': 'HTML', 'disable_web_page_preview': True})
                if not isinstance(response, dict) or not response.get('ok'):
                    raise RuntimeError('Telegram rejected the message')
                already_sent.add(chat_id)
                await db.posts.update_one({'_id': post_row['_id']}, {
                    '$addToSet': {'telegram_notification.sent_chat_ids': chat_id}})
            except Exception:
                failed = True
        if not failed and all(chat_id in already_sent for chat_id in recipients):
            await db.posts.update_one({'_id': post_row['_id']}, {
                '$set': {'telegram_notification.status': 'sent',
                         'telegram_notification.sent_at': now()},
                '$unset': {'telegram_notification.error': '',
                           'telegram_notification.lease_until': ''}})
        else:
            await db.posts.update_one({'_id': post_row['_id']}, {
                '$set': {'telegram_notification.status': 'failed',
                         'telegram_notification.error': 'Delivery to one or more chats failed; retry scheduled'},
                '$unset': {'telegram_notification.lease_until': ''}})

_sync_lock = asyncio.Lock()


def sync_running():
    """Report whether an ingestion/classification cycle currently owns the lock."""
    return _sync_lock.locked()


async def _social_posts(client, platform, secret, keywords, since, x_usernames=(), project_keywords=()):
    """Fetch public social posts through the configured Apify Actor."""
    apify_token = str(secret.get('api_key', '')).strip()
    if not apify_token:
        raise RuntimeError('Apify API token is not configured')
    return await apify_posts(client, platform, secret, keywords, since, x_usernames, project_keywords)

async def scheduled_sync(db, client, platforms):
    """Run without any logged-in user, but only inside the operating window."""
    prefs = await settings(db)
    if not within_automation_window(
            start_hour=prefs.get('automation_start_hour', DEFAULT_AUTOMATION_START_HOUR),
            end_hour=prefs.get('automation_end_hour', DEFAULT_AUTOMATION_END_HOUR)):
        return
    await sync(db, client, platforms=platforms)


async def sync(db, client, platforms=None):
    if _sync_lock.locked():
        return
    async with _sync_lock:
        if not config().seed_mock_data:
            enabled = getattr(config(), 'enabled_platforms', ','.join(PLATFORMS)).split(',')
            selected = [p for p in (platforms or enabled) if p in enabled]
            preferences = await settings(db)
            base_keywords = [k['keyword'] async for k in db.tracked_keywords.find({'is_active': True})]
            active_project = preferences.get('active_project', DEFAULT_MONITORING_PROJECT)
            project_keywords = MONITORING_PROJECTS.get(active_project, {}).get('keywords', [])
            keywords = list(dict.fromkeys([*base_keywords, *project_keywords]))
            x_usernames = preferences.get('x_usernames', [])
            if keywords:
                async for c in db.platform_credentials.find({'platform': {'$in': selected}}):
                    p = c['platform']
                    started = now()
                    await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': {'last_attempt_at': started}})
                    try:
                        secret = decrypt(c['encrypted_api_key'])
                        scope_changed = (c.get('tracking_scope_version') != TRACKING_SCOPE_VERSION
                                         or c.get('monitoring_project') != active_project)
                        if scope_changed:
                            # A campaign retarget must not reuse the previous campaign's
                            # ingestion cursor. Backfill all sources for the new scope.
                            since = now() - timedelta(days=(
                                config().youtube_initial_lookback_days if p == 'youtube' else 7
                            ))
                        elif p == 'youtube' and c.get('search_strategy') != YOUTUBE_SEARCH_STRATEGY:
                            since = now() - timedelta(days=config().youtube_initial_lookback_days)
                        elif p == 'news' and c.get('search_strategy') != 'entity-rss-v3':
                            since = now() - timedelta(days=7)
                        else:
                            since = c.get('last_synced_at') or now() - timedelta(hours=24)
                        since -= timedelta(minutes=5)  # deliberate overlap; compound unique index deduplicates
                        if p == 'youtube':
                            rows = await youtube_posts(client, secret, keywords, since, project_keywords)
                        elif p == 'news':
                            rows = await google_news_posts(client, keywords, since, project_keywords)
                        else:
                            rows = await _social_posts(
                                client, p, secret, keywords, since, x_usernames, project_keywords,
                            )
                        for row in rows:
                            if p == 'youtube':
                                # Upgrade legacy title-only rows to title + description
                                # and send them through classification once.
                                await db.posts.update_one({'platform': p, 'external_id': row['external_id'],
                                    'content_scope': {'$ne': YOUTUBE_CONTENT_SCOPE}},
                                    {'$set': row, '$unset': {
                                        'classification_error': '', 'hf_candidate': '',
                                        'telegram_notification': '',
                                    }})
                            refresh_fields = {
                                key: row[key] for key in (
                                    'author_avatar_url', 'media_url', 'media_type', 'thumbnail_url',
                                ) if row.get(key)
                            }
                            insert_fields = {
                                key: value for key, value in row.items()
                                if key not in refresh_fields
                            }
                            update = {'$setOnInsert': insert_fields}
                            if refresh_fields:
                                update['$set'] = refresh_fields
                            await db.posts.update_one(
                                {'platform': p, 'external_id': row['external_id']}, update, upsert=True,
                            )
                        credential_update = {'last_synced_at': started, 'status': 'live', 'error': None,
                                             'tracking_scope_version': TRACKING_SCOPE_VERSION,
                                             'monitoring_project': active_project,
                                             'encrypted_api_key': encrypt(secret)}
                        if p == 'youtube':
                            credential_update['search_strategy'] = YOUTUBE_SEARCH_STRATEGY
                        elif p == 'news':
                            credential_update['search_strategy'] = 'entity-rss-v3'
                        await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': credential_update})
                    except Exception as exc:
                        await db.platform_credentials.update_one({'_id': c['_id']}, {'$set': {'status': 'unavailable',
                            'error': str(exc) if isinstance(exc, RuntimeError) else 'Connection failed; check configuration'}})
            engine = classifier()
            try:
                posts = await db.posts.find({
                    '$and': [
                        POST_SCOPE,
                        {'$or': [
                            {'sentiment': None},
                            {'sentiment.label': 'negative', 'sentiment_schema_version': {'$lt': 7}},
                        ]},
                    ],
                    'platform': {'$in': enabled},
                    'demo': False,
                    'classification_status': {'$ne': 'excluded_no_text'},
                }).limit(200).to_list(200)
                size = config().hf_batch_size
                for offset in range(0, len(posts), size):
                    batch = posts[offset:offset + size]
                    inputs = [(p, _text_for_classification(p)) for p in batch]
                    blank_posts = [p for p, text in inputs if not text.strip()]
                    for p in blank_posts:
                        await db.posts.update_one({'_id': p['_id']}, {
                            '$set': {
                                'classification_status': 'excluded_no_text',
                                'classification_error': (
                                    'No source caption/text is available for classification'
                                ),
                            },
                            '$unset': {'sentiment': '', 'hf_candidate': '',
                                       'telegram_notification': ''},
                        })
                    valid = [(p, text) for p, text in inputs if text.strip()]
                    if not valid:
                        continue
                    results = await engine.classify([text for _, text in valid])
                    for (p, _), r in zip(valid, results, strict=True):
                        if r.pending:
                            await db.posts.update_one({'_id': p['_id']}, {
                                '$set': {
                                    'classification_status': 'awaiting_gemini',
                                    'hf_candidate': r.model_dump(),
                                    'classification_error': (
                                        'Gemini unavailable; unverified result excluded from totals'
                                    ),
                                },
                                '$unset': {'sentiment': '', 'telegram_notification': ''},
                            })
                            continue
                        start, end = bounds(today())
                        published_today = start <= p['published_at'] < end
                        notification = ({'status': 'pending', 'created_at': now()}
                                        if r.sentiment == 'negative' and published_today
                                        and not p.get('telegram_notification') else None)
                        update_fields = {'sentiment': dict(
                            label=r.sentiment, confidence=r.confidence, reason=r.reason,
                            model_used=r.model_used or engine.provenance, hf_label=r.hf_label,
                            hf_confidence=r.hf_confidence,
                            language=r.language, targets=r.targets,
                            review_required=r.review_required, classified_at=now()), 'classification_status': 'classified',
                            'sentiment_schema_version': 7}
                        if notification:
                            update_fields['telegram_notification'] = notification
                        unset_fields = {'classification_error': '', 'hf_candidate': ''}
                        if r.sentiment != 'negative':
                            unset_fields['telegram_notification'] = ''
                        await db.posts.update_one({'_id': p['_id']}, {
                            '$set': update_fields, '$unset': unset_fields,
                        })
                    # Deliver newly classified negatives immediately after each batch.
                    await notify_negative_posts(db, client)
            except Exception:
                # Classifier exposes failure state; pending posts are retried next sync.
                pass
        await rollup(db)
        await notify_negative_posts(db, client)
        # Include late-arriving posts from previous reporting days.
        async for day in db.daily_aggregates.find({'platform': 'overall', 'content_scope': YOUTUBE_CONTENT_SCOPE}):
            await create_alert(db, day['date'])

async def seed(db):
    if await db.posts.count_documents({'demo': True}):
        return
    rng = random.Random(20260928)
    texts = {
        'positive': ['बिहार सरकार की शिक्षा पहल पर अच्छी चर्चा हुई।', 'Samrat Choudhary is asking the right questions about jobs in Bihar.', 'Bihar BJP ki local meeting mein achhi discussion hui.'],
        'negative': ['Bihar Government needs a clearer jobs plan. Promises alone are not enough.', 'सम्राट चौधरी की बातों में जमीन पर काम की स्पष्ट योजना कहाँ है?', 'Bihar BJP ki rally mein sawaal zyada, jawaab kam.'],
        'neutral': ['Samrat Choudhary addressed a public meeting today. Full discussion to follow.', 'बिहार भाजपा की अगली बैठक रविवार को होगी।', 'Bihar Government: a summary of today’s education policy discussion.']}
    texts['mixed'] = [
        'Samrat Choudhary raised strong education points, but his jobs plan remains weak.',
        'Bihar Government praised for outreach but criticised for slow execution.',
    ]
    docs = []
    day0 = datetime.fromisoformat(today()).date()
    for offset in range(30):
        day = (day0 - timedelta(days=offset)).isoformat(); start, end = bounds(day)
        for platform in ['x', 'youtube']:
            count = (1080 if platform == 'x' else 570) if offset == 0 else rng.randint(260, 560)
            for i in range(count):
                label = rng.choices(['positive', 'negative', 'neutral', 'mixed'], [32, 40 if offset == 0 else 24 + offset % 9, 23, 5])[0]
                eng = dict(likes=rng.randint(0, 980), comments=rng.randint(0, 180), shares=rng.randint(0, 240), views=rng.randint(300, 18000))
                available_seconds = max(1, int((min(end, now()) - start).total_seconds()))
                docs.append(dict(schema_version=1, platform=platform, external_id=f'demo-{day}-{platform}-{i}',
                                 author=f'Sample analyst {i % 80 + 1:02d}', content=rng.choice(texts[label]), url='',
                                 published_at=start + timedelta(seconds=rng.randrange(available_seconds)), engagement=eng,
                                 engagement_score=eng['likes'] + eng['comments'] + eng['shares'], ingested_at=now(), demo=True,
                                 sentiment=dict(label=label, confidence=round(rng.uniform(.59, .98), 2), reason='Synthetic demonstration label', model_used='demo-fixture', classified_at=now())))
    await db.posts.insert_many(docs)
