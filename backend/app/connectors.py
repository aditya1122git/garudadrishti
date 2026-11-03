"""Rate-aware connectors for YouTube, RSS and social monitoring providers."""
import asyncio
import ast
import hashlib
import html
import json
import random
import re
import time
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from xml.etree import ElementTree
import httpx
from .config import (
    APIFY_FACEBOOK_DISCOVERY_ACTOR,
    APIFY_FACEBOOK_DISCOVERY_LIMIT,
    APIFY_MAX_ITEMS,
    APIFY_RUN_TIMEOUT_SECONDS,
    DEFAULT_APIFY_ACTORS,
    REDDIT_MAX_ITEMS,
)

NEWS_CHANNELS = (
    'News18', 'Zee Bihar', 'ABP Bihar', 'News State', 'Sahara Samay',
    'Bihar Tak', 'First Bihar', 'Live Cities', 'News4Nation',
    'Hindustani Media', 'Dainik Jagran Bihar', 'TV9 Bihar/Jharkhand',
    'Dainik Bhaskar Bihar', 'Prabhat Khabar', 'Live Hindustan Bihar',
    'ETV Bharat Bihar', 'Navbharat Times Bihar',
    'Aaj Tak', 'India Today', 'NDTV India', 'Republic Bharat',
    'CNN-News18', 'News24', 'Bharat24', 'DD News', 'ANI', 'PTI',
    'Amar Ujala', 'Jansatta', 'Oneindia Hindi', 'Punjab Kesari',
    'Times of India', 'Hindustan Times', 'Indian Express', 'The Hindu',
    'Economic Times', 'Kashish News',
)

NEWS_LOCALES = (
    {'hl': 'hi', 'gl': 'IN', 'ceid': 'IN:hi'},
    {'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'},
)

BIHAR_DISCOVERY_TERMS = (
    'Bihar', 'बिहार', '#Bihar', '#BiharNews',
    'Bihar News', 'बिहार न्यूज़', 'Bihar Politics', 'बिहार राजनीति',
    'Patna', 'पटना',
)
BIHAR_WIDE_NEWS_QUERY = '"Bihar" OR "बिहार"'

NEWS_SEARCH_QUERIES = (
    BIHAR_WIDE_NEWS_QUERY,
    '"Samrat Choudhary" OR "Samrat Chaudhary"',
    '"Bihar BJP" OR "BJP Bihar"',
    '"Bihar Government" OR "Bihar Govt"',
    '"सम्राट चौधरी" OR "बिहार भाजपा" OR "बिहार सरकार"',
)

YOUTUBE_SEARCH_TERMS = (
    'Bihar',
    'बिहार',
    'Bihar News',
    'Samrat Choudhary',
    'Bihar BJP',
    'Bihar Government',
    'NDA Bihar',
)

X_SEARCH_GROUPS = (
    (('Bihar', 'बिहार', '#Bihar', '#BiharNews', 'Bihar News'),
     ('Bihar', 'बिहार', '#Bihar', '#BiharNews', 'Bihar News', 'Bihar Politics', 'Patna', 'पटना')),
    (('Samrat Choudhary', 'Samrat Chaudhary', '#SamratChoudhary'),
     ('Samrat Choudhary', 'Samrat Chaudhary', 'CM Samrat',
      '#SamratChoudhary', '#SamratChaudhary', '#CMSamrat')),
    (('सम्राट चौधरी',),
     ('सम्राट चौधरी', 'सम्राट', '@samrat4bjp', 'from:samrat4bjp')),
    (('Bihar BJP', 'BJP Bihar', 'Bharatiya Janata Party Bihar',
      'बिहार भाजपा', 'भाजपा बिहार', '#BiharBJP', '#BJP4Bihar'),
     ('Bihar BJP', 'BJP Bihar', 'बिहार भाजपा', 'भाजपा बिहार',
      '#BiharBJP', '#BJP4Bihar', '@BJP4Bihar', 'from:BJP4Bihar')),
    (('Bihar Government', 'Bihar Govt', 'Government of Bihar', 'बिहार सरकार',
      '#BiharGovt', '#BiharGovernment'),
     ('Bihar Government', 'Bihar Govt', 'Government of Bihar', 'बिहार सरकार',
      '#BiharGovt', '#BiharGovernment')),
    (('NDA Bihar', '#NDA', '#NDAAlliance', '#NDABihar', '#BJPNDA',
      '#भाजपाएनडीए', '#एनडीए'),
     ('NDA Bihar', '#NDAAlliance', '#NDABihar', '#BJPNDA', '#भाजपाएनडीए', '#एनडीए')),
)
X_MATCH_ALIASES = ('CM Samrat', '#CMSamrat', '@samrat4bjp', '@BJP4Bihar', 'सम्राट')
X_OFFICIAL_HANDLES = {'samrat4bjp', 'bjp4bihar'}

REDDIT_SEARCH_GROUPS = (
    (('Bihar', 'बिहार', 'Bihar News', '#Bihar', '#BiharNews'), 'Bihar'),
    (('Samrat Choudhary', 'Samrat Chaudhary', 'सम्राट चौधरी'),
     'Samrat Choudhary'),
    (('Bihar BJP', 'BJP Bihar', 'Bharatiya Janata Party Bihar', 'बिहार भाजपा', 'भाजपा बिहार'),
     'Bihar BJP'),
    (('Bihar Government', 'Bihar Govt', 'Government of Bihar', 'बिहार सरकार'),
     'Bihar Government'),
    (('NDA', 'NDA Bihar', 'BJP NDA', 'एनडीए'),
     'NDA Bihar'),
)

# Provider discovery only needs the monitored entities/locations. The full
# keyword list (including every location AND issue combination) is still used
# below when normalizing/filtering returned posts. Sending all combinations to
# paid Actors creates thousands of equivalent searches without adding coverage.
SOCIAL_PROVIDER_DISCOVERY_TERMS = (
    'Bihar', 'बिहार', 'Bihar News', 'बिहार न्यूज़',
    'Bihar Government', 'बिहार सरकार', 'Bihar BJP', 'बिहार भाजपा',
    'NDA Bihar', 'Samrat Choudhary', 'सम्राट चौधरी', 'Bihar CM',
    'Bhagalpur', 'भागलपुर', 'Banka', 'बांका',
    'Munger', 'मुंगेर', 'Gaya Bihar', 'गया', 'Nawada', 'नवादा',
    'Aurangabad Bihar', 'औरंगाबाद', 'Jehanabad', 'जहानाबाद', 'Arwal', 'अरवल',
    'Patna', 'पटना', 'Nalanda', 'नालंदा', 'Bhojpur', 'भोजपुर',
    'Buxar', 'बक्सर', 'Rohtas', 'रोहतास', 'Kaimur', 'कैमूर',
    'Muzaffarpur', 'मुजफ्फरपुर', 'Vaishali', 'वैशाली',
    'Sitamarhi', 'सीतामढ़ी', 'Sheohar', 'शिवहर',
    'East Champaran', 'पूर्वी चंपारण', 'Motihari', 'मोतिहारी',
    'West Champaran', 'पश्चिमी चंपारण', 'Bettiah', 'बेतिया',
)


def _compact_provider_terms(keywords, project_keywords):
    """Keep all manual terms while collapsing generated project combinations."""
    project_scope = {
        str(value).strip().casefold()
        for value in project_keywords if str(value).strip()
    }
    manual_terms = [
        str(value).strip() for value in keywords
        if str(value).strip() and str(value).strip().casefold() not in project_scope
    ]
    unique = {}
    for value in (*SOCIAL_PROVIDER_DISCOVERY_TERMS, *manual_terms):
        clean = ' '.join(str(value).split())
        if clean:
            unique.setdefault(clean.casefold(), clean)
    return list(unique.values())

NEWS_SOURCE_ALIASES = {
    'News18': ('news18',),
    'Zee Bihar': ('zeebihar', 'zeebiharjharkhand', 'zeenews', 'zeehindustan'),
    'ABP Bihar': ('abpbihar', 'abplive', 'abpnews'),
    'News State': ('newsstate', 'newsstate24'),
    'Sahara Samay': ('saharasamay', 'samaylive'),
    'Bihar Tak': ('bihartak',),
    'First Bihar': ('firstbihar',),
    'Live Cities': ('livecities',),
    'News4Nation': ('news4nation',),
    'Hindustani Media': ('hindustanimedia',),
    'Dainik Jagran Bihar': ('jagran', 'jagrancom'),
    'TV9 Bihar/Jharkhand': ('tv9hindi', 'tv9bharatvarsh'),
    'Dainik Bhaskar Bihar': ('dainikbhaskar', 'bhaskarhindi'),
    'Prabhat Khabar': ('prabhatkhabar',),
    'Live Hindustan Bihar': ('livehindustan',),
    'ETV Bharat Bihar': ('etvbharat',),
    'Navbharat Times Bihar': ('navbharattimes',),
    'Aaj Tak': ('aajtak',),
    'India Today': ('indiatoday',),
    'NDTV India': ('ndtvindia', 'ndtv'),
    'Republic Bharat': ('republicbharat',),
    'CNN-News18': ('cnnnews18',),
    'News24': ('news24',),
    'Bharat24': ('bharat24',),
    'DD News': ('ddnews',),
    'ANI': ('aninews',),
    'Amar Ujala': ('amarujala',),
    'Jansatta': ('jansatta',),
    'Oneindia Hindi': ('oneindiahindi',),
    'Punjab Kesari': ('punjabkesari',),
    'Times of India': ('timesofindia',),
    'Hindustan Times': ('hindustantimes',),
    'Indian Express': ('indianexpress',),
    'The Hindu': ('thehindu',),
    'Economic Times': ('economictimes',),
    'Kashish News': ('kashishnews',),
}

NEWS_SOURCE_EXACT_ALIASES = {'hindustan', 'ani', 'pti', 'presstrustofindia'}
NEWS_SOURCE_EXACT_CHANNELS = {
    'hindustan': 'Live Hindustan Bihar',
    'ani': 'ANI',
    'pti': 'PTI',
    'presstrustofindia': 'PTI',
}


def canonical_news_source(value):
    """Map Google News publisher variants to a configured display channel."""
    normalized = re.sub(r'[^a-z0-9]+', '', str(value or '').lower())
    if normalized in NEWS_SOURCE_EXACT_CHANNELS:
        return NEWS_SOURCE_EXACT_CHANNELS[normalized]
    matches = [
        (len(alias), channel)
        for channel, aliases in NEWS_SOURCE_ALIASES.items()
        for alias in aliases
        if alias in normalized
    ]
    return max(matches)[1] if matches else None


def _approved_news_source(value):
    return canonical_news_source(value) is not None


class ProviderError(RuntimeError):
    pass


class DailyQuotaExhausted(ProviderError):
    pass


async def request(client, method, url, **kwargs):
    comments_optional = kwargs.pop('comments_optional', False)
    response_json = kwargs.pop('response_json', True)
    response_text = kwargs.pop('response_text', False)
    for attempt in range(4):
        try:
            response = await client.request(method, url, **kwargs)
            if comments_optional and response.status_code == 403 and any(e.get('reason') == 'commentsDisabled' for e in response.json().get('error', {}).get('errors', [])):
                return {'items': []}
            if response.status_code in (403, 429):
                try:
                    error = response.json().get('error', {})
                    message = error.get('message', '')
                    reasons = {row.get('reason', '') for row in error.get('errors', [])}
                except (TypeError, ValueError):
                    message, reasons = '', set()
                quota_reasons = {
                    'quotaExceeded', 'dailyLimitExceeded', 'dailyLimitExceededUnreg',
                    'rateLimitExceeded', 'userRateLimitExceeded',
                }
                if reasons & quota_reasons or 'quota' in message.lower():
                    raise DailyQuotaExhausted('YouTube daily search quota exhausted; retry after quota reset')
                if response.status_code == 403:
                    response.raise_for_status()
                delay = max(float(response.headers.get('retry-after', 0) or 0),
                            float(response.headers.get('x-rate-limit-reset', 0) or 0) - time.time(),
                            2 ** attempt + random.random())
                if delay > 30 or attempt == 3:
                    raise ProviderError('Provider rate limited or unavailable; retry next scheduled run')
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 500:
                delay = max(float(response.headers.get('retry-after', 0) or 0),
                            float(response.headers.get('x-rate-limit-reset', 0) or 0) - time.time(),
                            2 ** attempt + random.random())
                if delay > 30 or attempt == 3:
                    raise ProviderError('Provider rate limited or unavailable; retry next scheduled run')
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response.text if response_text else response.json() if response_json else {}
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise ProviderError(f'Provider rejected request ({exc.response.status_code})') from None
            if attempt == 3:
                raise ProviderError('Provider unavailable') from None
            await asyncio.sleep(2 ** attempt)
    raise ProviderError('Provider unavailable')


def matches(text, keywords):
    return any(re.search(r'(?<!\w)' + re.escape(k) + r'(?!\w)', text, re.I) for k in keywords)


def _prioritized_bihar_keywords(keywords):
    """Keep broad Bihar discovery terms inside provider query-count limits."""
    active = {str(keyword).strip().casefold() for keyword in keywords if str(keyword).strip()}
    priority = [term for term in BIHAR_DISCOVERY_TERMS if term.casefold() in active]
    priority_keys = {term.casefold() for term in priority}
    return priority + [
        str(keyword).strip() for keyword in keywords
        if str(keyword).strip() and str(keyword).strip().casefold() not in priority_keys
    ]


def post(platform, external_id, author, content, url, timestamp, engagement=None):
    metrics = {k: int((engagement or {}).get(k, 0)) for k in ('likes', 'comments', 'shares', 'views')}
    return dict(schema_version=1, platform=platform, external_id=str(external_id), author=author,
                content=content, url=url, published_at=datetime.fromisoformat(timestamp.replace('Z', '+00:00')),
                engagement=metrics, engagement_score=sum(metrics[k] for k in ('likes', 'comments', 'shares')),
                ingested_at=datetime.now(timezone.utc), sentiment=None, demo=False)


async def youtube_posts(client, secret, keywords, since, project_keywords=()):
    base = 'https://www.googleapis.com/youtube/v3/'
    keys = list(dict.fromkeys(filter(None, (
        str(secret.get('api_key', '')).strip(),
        str(secret.get('backup_api_key', '')).strip(),
    ))))
    if not keys:
        raise ProviderError('YouTube API key is not configured')
    active_key = 0

    async def youtube_get(endpoint, params):
        nonlocal active_key
        while active_key < len(keys):
            try:
                return await request(client, 'GET', base + endpoint,
                                     params={**params, 'key': keys[active_key]})
            except DailyQuotaExhausted:
                active_key += 1
        raise ProviderError('YouTube daily quota exhausted on all configured API keys; retry after quota reset')

    # One combined official search includes regular videos and Shorts. The old
    # per-group + short-filter approach spent about four times as many quota units.
    rows = []
    videos = {}
    # YouTube returns an empty result set for very large OR expressions even
    # though compact entity searches work. Use one stable discovery query;
    # the complete editable keyword set still filters returned video titles.
    # Keep the stable Bihar discovery query and add a bounded selection from
    # the active project. A very large YouTube OR expression returns no rows.
    query_terms = list(dict.fromkeys([*YOUTUBE_SEARCH_TERMS, *list(project_keywords)[:6]]))
    search_params = dict(
        part='snippet', type='video', order='date', maxResults=50,
        q='|'.join(query_terms), publishedAfter=since.isoformat().replace('+00:00', 'Z'),
    )
    # search.list returns at most 50 rows per response. Exhaust pageToken so a
    # busy 15-minute interval is not silently truncated to its first 50 videos.
    page_token = None
    seen_page_tokens = set()
    while True:
        data = await youtube_get('search', {
            **search_params, **({'pageToken': page_token} if page_token else {}),
        })
        for item in data.get('items', []):
            video_id = item.get('id', {}).get('videoId')
            if video_id:
                videos[video_id] = {'general-search'}
        next_page_token = str(data.get('nextPageToken') or '').strip()
        if not next_page_token or next_page_token in seen_page_tokens:
            break
        seen_page_tokens.add(next_page_token)
        page_token = next_page_token
    # Fetch stable video metadata in batches. Discovery, storage and sentiment
    # use the complete public title + description text.
    ids = list(videos)
    for offset in range(0, len(ids), 50):
        details = await youtube_get('videos', dict(
            part='snippet,statistics,contentDetails', id=','.join(ids[offset:offset + 50])))
        for video in details.get('items', []):
            vid, snippet = video['id'], video['snippet']
            title = snippet['title']
            description = str(snippet.get('description') or '').strip()
            content = f'{title}\n{description}'.strip()
            if not matches(content, keywords):
                continue
            stats = video.get('statistics', {})
            row = post('youtube', vid, snippet['channelTitle'], content,
                       f'https://www.youtube.com/watch?v={vid}', snippet['publishedAt'],
                       dict(likes=stats.get('likeCount', 0), views=stats.get('viewCount', 0)))
            duration = video.get('contentDetails', {}).get('duration', '')
            duration_match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
            duration_seconds = (int(duration_match.group(1) or 0) * 3600
                                + int(duration_match.group(2) or 0) * 60
                                + int(duration_match.group(3) or 0)) if duration_match else None
            short_candidate = duration_seconds is not None and duration_seconds < 240
            row.update(content_type='short' if short_candidate else 'video', title=title,
                       description=description,
                       media_type='video',
                       thumbnail_url=str(_first(
                           snippet, 'thumbnails.maxres.url', 'thumbnails.standard.url',
                           'thumbnails.high.url', 'thumbnails.medium.url',
                           'thumbnails.default.url', default='',
                       )),
                       discovery=sorted(videos[vid]),
                       content_scope='youtube-title-description-v3')
            rows.append(row)
    secret.pop('watched_videos', None)
    return rows


def _rss_text(value):
    clean = re.sub(r'<[^>]+>', ' ', html.unescape(value or ''))
    return ' '.join(clean.split())


async def google_news_posts(client, keywords, since, project_keywords=()):
    """Fetch approved Bihar publishers from Google News public RSS search feeds."""
    lookback_days = min(7, max(1, math.ceil((datetime.now(timezone.utc) - since).total_seconds() / 86400)))

    async def fetch(entity_query, locale):
        # Google News does not treat a quoted publisher name as a reliable
        # source filter. Query each tracked entity and validate the RSS
        # <source> metadata against the approved publisher allow-list instead.
        query = f'({entity_query}) when:{lookback_days}d'
        xml = await request(client, 'GET', 'https://news.google.com/rss/search', params={
            'q': query, **locale,
        }, headers={'Accept': 'application/rss+xml, application/xml;q=0.9'}, response_text=True)
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError:
            raise ProviderError('Google News returned invalid RSS') from None
        found = []
        for item in root.findall('./channel/item'):
            source = _rss_text(item.findtext('source'))
            channel = canonical_news_source(source)
            if not channel:
                continue
            title = _rss_text(item.findtext('title'))
            suffix = f' - {source}'
            headline = title[:-len(suffix)].strip() if source and title.endswith(suffix) else title
            if not headline or not (matches(headline, keywords) or entity_query == BIHAR_WIDE_NEWS_QUERY):
                continue
            try:
                published = parsedate_to_datetime(item.findtext('pubDate') or '').astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            if published < since:
                continue
            url = (item.findtext('link') or '').strip()
            guid = (item.findtext('guid') or '').strip()
            external_id = guid or hashlib.sha256(f'{url}\0{headline}\0{published.isoformat()}'.encode()).hexdigest()
            row = post('news', external_id, channel, headline, url, published.isoformat())
            row.update(source_provider='google-news-rss', content_scope='google-news-rss-v1', title=headline)
            found.append(row)
        return found

    project_terms = list(dict.fromkeys(
        str(value).strip() for value in project_keywords if str(value).strip()
    ))[:12]
    project_query = ' OR '.join(f'"{term}"' for term in project_terms)
    search_queries = [*NEWS_SEARCH_QUERIES, *([project_query] if project_query else [])]
    results = await asyncio.gather(*(
        fetch(query, locale) for query in search_queries for locale in NEWS_LOCALES
    ))
    unique = {}
    for rows in results:
        for row in rows:
            unique[row['external_id']] = row
    return list(unique.values())


def _first(item, *paths, default=None):
    """Return the first non-empty value from common Actor output shapes."""
    for path in paths:
        value = item
        for part in path.split('.'):
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                value = value[int(part)]
            else:
                value = None
                break
        if value not in (None, ''):
            return value
    return default


def _number(item, *paths):
    value = _first(item, *paths, default=0)
    try:
        return max(0, int(float(str(value).replace(',', ''))))
    except (TypeError, ValueError):
        return 0


def _author_name(value):
    """Normalize Actor author objects, including Python-repr strings."""
    if isinstance(value, dict):
        nested = _first(value, 'name', 'fullName', 'displayName', 'userName', 'username', default='')
        return str(nested).strip() or 'Unknown'
    if isinstance(value, (list, tuple)):
        return _author_name(value[0]) if value else 'Unknown'
    text = str(value or '').strip()
    if text.startswith('{') and text.endswith('}'):
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                pass
        if isinstance(parsed, dict):
            return _author_name(parsed)
        # Never expose a provider's serialized metadata blob as an author name.
        return 'Unknown'
    return text[:160] or 'Unknown'


def _timestamp(value):
    if isinstance(value, (int, float)):
        # Accept Unix seconds and milliseconds returned by different Actors.
        value = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(value, timezone.utc)
    if not value:
        raise ProviderError('Apify item has no publication timestamp')
    text = str(value).strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            # X/Twitter Actors commonly return: Sun Nov 01 04:31:37 +0000 2026
            parsed = datetime.strptime(text, '%a %b %d %H:%M:%S %z %Y')
        except ValueError:
            parsed = None
    if parsed is None:
        # RFC 2822 is common in RSS/news Actor output.
        from email.utils import parsedate_to_datetime
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            raise ProviderError('Apify item has an invalid publication timestamp') from None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _actor_input(platform, keywords, since, max_items, x_usernames=(), project_keywords=()):
    """Build inputs for the fixed, tested Apify Actors."""
    since_iso = since.isoformat().replace('+00:00', 'Z')
    provider_terms = _compact_provider_terms(keywords, project_keywords)
    if platform == 'instagram':
        # Direct hashtag URLs make the Instagram Scraper return post objects.
        # Its generic `search` input returns hashtag summary objects instead.
        searches = []
        discovery_keywords = provider_terms
        for keyword in discovery_keywords:
            # Boolean X/Reddit discovery expressions are not valid Instagram
            # hashtags. Broad location/topic tags already cover both sides.
            if re.search(r'\s+AND\s+', keyword, flags=re.I):
                continue
            tag = re.sub(r'[^\w]+', '', keyword.lstrip('#'), flags=re.UNICODE)
            if tag and tag.casefold() not in {value.casefold() for value in searches}:
                searches.append(tag)
        if not searches:
            raise ProviderError('No Instagram hashtag search terms are active')
        return {
            'directUrls': [
                f'https://www.instagram.com/explore/tags/{quote(tag, safe="")}/'
                for tag in searches
            ],
            'resultsType': 'posts',
            # Instagram applies resultsLimit per hashtag URL. Divide the
            # run-wide allowance so ten tags cannot silently cost 10x more.
            'resultsLimit': max(1, max_items // len(searches)),
            'onlyPostsNewerThan': since_iso,
        }
    if platform == 'x':
        active = {keyword.casefold() for keyword in keywords}
        search_terms = []
        for triggers, terms in X_SEARCH_GROUPS:
            if not any(term.casefold() in active for term in triggers):
                continue
            query = ' OR '.join(
                term if term.startswith('#') else f'"{term}"'
                for term in terms
                if not term.startswith(('from:', '@'))
            )
            operators = ' OR '.join(
                term for term in terms if term.startswith(('from:', '@'))
            )
            query = f'{query} OR {operators}' if operators else query
            search_terms.append(f'({query}) since:{since.date().isoformat()}')
        for username in x_usernames:
            handle = re.sub(r'[^A-Za-z0-9_]', '', str(username).lstrip('@'))
            if handle:
                search_terms.append(f'from:{handle} since:{since.date().isoformat()}')
        for offset in range(0, len(provider_terms), 8):
            group = provider_terms[offset:offset + 8]
            expressions = []
            for term in group:
                parts = [part.strip() for part in re.split(r'\s+AND\s+', term, flags=re.I) if part.strip()]
                expressions.append(' AND '.join(f'"{part}"' for part in parts))
            query = ' OR '.join(f'({expression})' for expression in expressions)
            search_terms.append(f'({query}) since:{since.date().isoformat()}')
        search_terms = list(dict.fromkeys(search_terms))
        if not search_terms:
            raise ProviderError('No supported X search terms are active')
        return {'searchTerms': search_terms, 'maxItems': max_items, 'sort': 'Latest + Top'}
    if platform == 'reddit':
        active = {keyword.strip().casefold() for keyword in keywords if keyword.strip()}
        active_queries = [query for triggers, query in REDDIT_SEARCH_GROUPS
                          if any(trigger.casefold() in active for trigger in triggers)]
        for offset in range(0, len(provider_terms), 6):
            group = provider_terms[offset:offset + 6]
            active_queries.append(' OR '.join(
                f'"{term}"' if ' ' in term else term for term in group
            ))
        active_queries = list(dict.fromkeys(active_queries))
        if not active_queries:
            raise ProviderError('No Reddit search terms are active')
        lookback_seconds = max(0, (datetime.now(timezone.utc) - since).total_seconds())
        period = 'day' if lookback_seconds <= 86400 else 'week'
        return {
            'queries': active_queries,
            'sort': 'new',
            'timeframe': period,
            'scrapeComments': False,
            'includeNsfw': False,
            'strictSearch': True,
            'strictTokenFilter': False,
            'dateFrom': since.date().isoformat(),
            'forceSortNewForTimeFilteredRuns': True,
            'maxPosts': max(1, math.ceil(max_items / len(active_queries))),
            'maximize_coverage': False,
            'sentiment_analysis': False,
            'content_analysis': False,
        }
    raise ProviderError(f'Unsupported direct Apify input for {platform}')


def _apify_item(platform, item, keywords, since, x_usernames=()):
    if not isinstance(item, dict):
        return None
    if platform == 'reddit' and str(item.get('dataType', 'post')).casefold() != 'post':
        return None
    title = str(_first(item, 'title', 'headline', 'article.title', default='')).strip()
    text = str(_first(item, 'text', 'full_text', 'tweetText', 'postText', 'message', 'caption',
                      'description', 'snippet', 'body', 'selftext', 'article.description', default='')).strip()
    # Social Actors expose the post body in `text`/`caption`; replies and
    # comments are intentionally excluded.
    content = f'{title}\n{text}'.strip() if platform == 'reddit' else text or title
    author_handle = str(_first(
        item, 'author.userName', 'author.username', 'user.userName', 'user.username',
        'ownerUsername', 'username', default='',
    )).strip().lstrip('@').casefold()
    content_matches = matches(
        content, [*keywords, *X_MATCH_ALIASES] if platform == 'x' else keywords,
    ) if content else False
    official_x_post = platform == 'x' and author_handle in X_OFFICIAL_HANDLES
    tracked_x_post = platform == 'x' and author_handle in {
        str(username).strip().lstrip('@').casefold() for username in x_usernames
    }
    if not content:
        return None
    if not (content_matches or official_x_post or tracked_x_post):
        return None
    published = _timestamp(_first(item, 'publishedAt', 'published_at', 'createdAt', 'created_at', 'created_utc',
                                  'takenAt', 'date_utc', 'timestamp', 'date', 'time', 'timeCreated',
                                  'article.publishedAt'))
    if published < since:
        return None
    url = str(_first(item, 'url', 'postUrl', 'tweetUrl', 'permalink', 'link', 'article.url', default=''))
    external_id = _first(item, 'id', 'postId', 'tweetId', 'shortCode', 'shortcode', 'article.id')
    if not external_id:
        external_id = hashlib.sha256(f'{platform}\0{url}\0{content}\0{published.isoformat()}'.encode()).hexdigest()
    author = _author_name(_first(item, 'authorName', 'pageName', 'author.name', 'author.userName', 'author.username',
                                'author', 'ownerUsername', 'username', 'fullName', 'user.pageName', 'user.name', 'user',
                                'channelName', 'source', 'publisher', default='Unknown'))
    author_avatar_url = str(_first(
        item, 'author.profilePicture', 'author.profileImageUrl', 'author.avatar',
        'user.profile_image_url_https', 'user.profileImageUrl', 'user.avatar',
        'profilePicUrl', 'profilePicture', 'avatar', default='',
    )).strip()
    if not author_avatar_url.startswith(('https://', 'http://')):
        author_avatar_url = ''
    video_url = html.unescape(str(_first(
        item, 'videoUrl', 'video.url', 'video.0.url', 'videos.0.url', 'videos.0',
        'media.0.videoUrl',
        'extendedEntities.media.0.video_info.variants.0.url', default='',
    ))).strip()
    image_url = html.unescape(str(_first(
        item, 'displayUrl', 'imageUrl', 'thumbnailUrl', 'thumbnail.url', 'thumbnail',
        'images.0.url', 'images.0', 'childPosts.0.displayUrl',
        'media.0.thumbnail', 'media.1.thumbnail', 'media.2.thumbnail',
        'media.0.mediaUrl', 'media.0.url', 'media.0',
        'media.0.photo_image.uri', 'extendedEntities.media.0.media_url_https',
        'card.binding_values.thumbnail_image.image_value.url',
        'preview.images.0.source.url', 'gallery_images.0.url',
        'attachments.0.url', default='',
    ))).strip()
    if not video_url.startswith(('https://', 'http://')):
        video_url = ''
    if not image_url.startswith(('https://', 'http://')):
        image_url = ''
    if not image_url and re.search(r'\.(?:jpe?g|png|webp|gif)(?:\?|$)', url, re.I):
        image_url = url
    engagement = dict(
        likes=_number(item, 'likesCount', 'likeCount', 'reactionCount', 'likes', 'upVotes', 'score', 'favoriteCount', 'stats.likes', 'reactions_count', 'public_metrics.like_count'),
        comments=_number(item, 'commentsCount', 'commentCount', 'comments', 'numberOfComments', 'numComments', 'num_comments', 'replyCount', 'stats.comments', 'comments_count', 'public_metrics.reply_count'),
        shares=_number(item, 'sharesCount', 'shareCount', 'shares', 'retweetCount', 'stats.shares', 'reshare_count', 'public_metrics.retweet_count'),
        views=_number(item, 'viewsCount', 'viewCount', 'videoPostViewCount', 'views', 'impressionCount', 'public_metrics.impression_count'),
    )
    row = post(platform, external_id, author, content, url, published.isoformat(), engagement)
    row.update(source_provider='apify', content_scope=(
        'reddit-public-post-v1' if platform == 'reddit' else 'apify-public-post-v1'
    ), caption=content, author_handle=author_handle, author_avatar_url=author_avatar_url,
        media_url=video_url or image_url, thumbnail_url=image_url,
        media_type='video' if video_url else ('image' if image_url else ''),
        _caption_keyword_match=content_matches,
        _official_x_post=official_x_post or tracked_x_post)
    return row


async def _run_apify_actor(client, actor_id, api_key, payload, limit):
    actor_path = quote(actor_id.replace('/', '~'), safe='~')
    url = f'https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items'
    data = await request(client, 'POST', url,
                         params={'format': 'json', 'clean': '1', 'limit': limit,
                                 'timeout': APIFY_RUN_TIMEOUT_SECONDS},
                         headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                         timeout=APIFY_RUN_TIMEOUT_SECONDS + 15,
                         json=payload)
    if not isinstance(data, list):
        raise ProviderError('Apify Actor did not return a dataset item array')
    return data


async def apify_posts(client, platform, secret, keywords, since, x_usernames=(), project_keywords=()):
    """Run the configured Apify Actors and normalize public social posts."""
    api_key = str(secret.get('api_key', '')).strip()
    if not api_key:
        raise ProviderError('Missing Apify API token')
    max_items = REDDIT_MAX_ITEMS if platform == 'reddit' else APIFY_MAX_ITEMS
    if platform == 'facebook':
        # The official Posts Actor accepts page/profile URLs, not keywords.
        # Discover matching public pages first, then fetch their latest posts.
        discovery = await _run_apify_actor(client, APIFY_FACEBOOK_DISCOVERY_ACTOR, api_key, {
            'categories': _compact_provider_terms(keywords, project_keywords),
            # Discover relevant public pages across India. Post bodies are
            # still filtered against the tracked Bihar-focused keywords.
            'locations': ['India'],
            'resultsLimit': APIFY_FACEBOOK_DISCOVERY_LIMIT,
        }, APIFY_FACEBOOK_DISCOVERY_LIMIT)
        page_urls = []
        for item in discovery:
            candidate = str(_first(item, 'facebookUrl', 'pageUrl', 'url', default='')).strip()
            if candidate.startswith(('https://www.facebook.com/', 'https://facebook.com/')) and candidate not in page_urls:
                page_urls.append(candidate)
        if not page_urls:
            return []
        per_page = max(1, max_items // len(page_urls))
        payload = {
            'startUrls': [{'url': url} for url in page_urls],
            'resultsLimit': per_page,
            'onlyPostsNewerThan': since.isoformat().replace('+00:00', 'Z'),
        }
    else:
        payload = _actor_input(
            platform, keywords, since, max_items, x_usernames, project_keywords,
        )
    data = await _run_apify_actor(
        client, DEFAULT_APIFY_ACTORS[platform], api_key, payload, max_items,
    )
    candidates = []
    invalid = 0
    for item in data:
        try:
            row = _apify_item(platform, item, keywords, since, x_usernames)
        except ProviderError:
            invalid += 1
            continue
        if row:
            candidates.append(row)
    if data and invalid == len(data):
        raise ProviderError('Apify output has no usable publication timestamps; check Actor mapping')
    rows = []
    for row in candidates:
        if not (row.pop('_caption_keyword_match', False)
                or row.pop('_official_x_post', False)):
            continue
        rows.append(row)
    return rows
