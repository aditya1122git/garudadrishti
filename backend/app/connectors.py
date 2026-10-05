"""Rate-aware source connectors for YouTube and Apify-backed monitoring."""
import asyncio
import ast
import hashlib
import json
import random
import re
import time
import socket
import ipaddress
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
import httpx
from .config import config

NEWS_CHANNELS = (
    'News18', 'Zee Bihar', 'ABP Bihar', 'News State', 'Sahara Samay',
    'Bihar Tak', 'First Bihar', 'Live Cities', 'News4Nation',
    'Hindustani Media',
)

NEWS_SOURCE_ALIASES = {
    'News18': ('news18',),
    'Zee Bihar': ('zeebihar', 'zeebiharjharkhand'),
    'ABP Bihar': ('abpbihar', 'abplive', 'abpnews'),
    'News State': ('newsstate', 'newsstate24'),
    'Sahara Samay': ('saharasamay', 'samaylive'),
    'Bihar Tak': ('bihartak',),
    'First Bihar': ('firstbihar',),
    'Live Cities': ('livecities',),
    'News4Nation': ('news4nation',),
    'Hindustani Media': ('hindustanimedia',),
}


def _approved_news_source(value):
    normalized = re.sub(r'[^a-z0-9]+', '', str(value or '').lower())
    return any(alias in normalized for aliases in NEWS_SOURCE_ALIASES.values() for alias in aliases)


class ProviderError(RuntimeError):
    pass


async def request(client, method, url, **kwargs):
    comments_optional = kwargs.pop('comments_optional', False)
    response_json = kwargs.pop('response_json', True)
    for attempt in range(4):
        try:
            response = await client.request(method, url, **kwargs)
            if comments_optional and response.status_code == 403 and any(e.get('reason') == 'commentsDisabled' for e in response.json().get('error', {}).get('errors', [])):
                return {'items': []}
            if response.status_code == 429 or response.status_code >= 500:
                delay = max(float(response.headers.get('retry-after', 0) or 0),
                            float(response.headers.get('x-rate-limit-reset', 0) or 0) - time.time(),
                            2 ** attempt + random.random())
                if delay > 30 or attempt == 3:
                    raise ProviderError('Provider rate limited or unavailable; retry next scheduled run')
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response.json() if response_json else {}
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise ProviderError(f'Provider rejected request ({exc.response.status_code})') from None
            if attempt == 3:
                raise ProviderError('Provider unavailable') from None
            await asyncio.sleep(2 ** attempt)
    raise ProviderError('Provider unavailable')


async def validate_destination(url):
    parsed = urlparse(url)
    allowed = {h.strip().lower() for h in config().outbound_allowed_hosts.split(',') if h.strip()}
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in [None, 443] or parsed.hostname.lower() not in allowed:
        raise ProviderError('Endpoint must use HTTPS and an OUTBOUND_ALLOWED_HOSTS hostname')
    answers = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443)
    if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
        raise ProviderError('Endpoint must resolve to public addresses')


def matches(text, keywords):
    return any(re.search(r'(?<!\w)' + re.escape(k) + r'(?!\w)', text, re.I) for k in keywords)


def post(platform, external_id, author, content, url, timestamp, engagement=None):
    metrics = {k: int((engagement or {}).get(k, 0)) for k in ('likes', 'comments', 'shares', 'views')}
    return dict(schema_version=1, platform=platform, external_id=str(external_id), author=author,
                content=content, url=url, published_at=datetime.fromisoformat(timestamp.replace('Z', '+00:00')),
                engagement=metrics, engagement_score=sum(metrics[k] for k in ('likes', 'comments', 'shares')),
                ingested_at=datetime.now(timezone.utc), sentiment=None, demo=False)


async def youtube_posts(client, secret, keywords, since):
    base = 'https://www.googleapis.com/youtube/v3/'
    # Search results are relevance-ranked rather than exhaustive. Split terms into
    # small OR groups and run an additional official short-duration query per group.
    rows = []
    videos = {}
    group_size = config().youtube_terms_per_query
    for offset in range(0, len(keywords), group_size):
        query = '|'.join(keywords[offset:offset + group_size])
        for duration in (None, 'short'):
            params = dict(key=secret['api_key'], part='snippet', type='video', order='date', maxResults=50,
                          q=query, publishedAfter=since.isoformat().replace('+00:00', 'Z'))
            if duration:
                # The API defines videoDuration=short as under four minutes. It is
                # the supported search filter that improves Shorts coverage.
                params['videoDuration'] = duration
            data = await request(client, 'GET', base + 'search', params=params)
            for item in data.get('items', []):
                video_id = item.get('id', {}).get('videoId')
                if video_id:
                    videos.setdefault(video_id, set()).add('short-search' if duration else 'general-search')
    # Fetch stable video metadata in batches. Sentiment uses the title only.
    ids = list(videos)
    for offset in range(0, len(ids), 50):
        details = await request(client, 'GET', base + 'videos', params=dict(
            key=secret['api_key'], part='snippet,statistics,contentDetails', id=','.join(ids[offset:offset + 50])))
        for video in details.get('items', []):
            vid, snippet = video['id'], video['snippet']
            title = snippet['title']
            if not matches(title, keywords):
                continue
            stats = video.get('statistics', {})
            row = post('youtube', vid, snippet['channelTitle'], title,
                       f'https://www.youtube.com/watch?v={vid}', snippet['publishedAt'],
                       dict(likes=stats.get('likeCount', 0), views=stats.get('viewCount', 0)))
            short_candidate = 'short-search' in videos[vid]
            row.update(content_type='short' if short_candidate else 'video', title=title,
                       discovery=sorted(videos[vid]),
                       content_scope='youtube-title-only-v2')
            rows.append(row)
    secret.pop('watched_videos', None)
    return rows


def _first(item, *paths, default=None):
    """Return the first non-empty value from common Actor output shapes."""
    for path in paths:
        value = item
        for part in path.split('.'):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
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
        # RFC 2822 is common in RSS/news Actor output.
        from email.utils import parsedate_to_datetime
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            raise ProviderError('Apify item has an invalid publication timestamp') from None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _actor_input(platform, template, keywords, since, max_items):
    if not template:
        per_query = max(1, min(50, max_items // max(len(keywords), 1)))
        news_keywords = ' OR '.join(f'"{term}"' for term in keywords)
        news_sources = ' OR '.join(f'"{channel}"' for channel in NEWS_CHANNELS)
        defaults = {
            'facebook': {'categories': keywords, 'searchType': 'posts', 'resultsLimit': max_items},
            'instagram': {'searchQueries': keywords[:10], 'maxResultsPerQuery': per_query},
            'x': {'searchTerms': keywords, 'maxItems': max_items, 'sort': 'Latest'},
            # easyapi/google-news-scraper accepts one query and requires at
            # least 100 requested results. The response is still capped by
            # `limit=max_items` in our Apify API call.
            'news': {'query': f'({news_keywords}) ({news_sources})',
                     'maxItems': max(100, max_items), 'time_period': 'custom',
                     'time_period_min': since.strftime('%m/%d/%Y'),
                     'time_period_max': datetime.now(timezone.utc).strftime('%m/%d/%Y'),
                     'nfpr': 1, 'filter': 1},
        }
        return defaults[platform]
    values = {
        '{{keywords_json}}': json.dumps(keywords, ensure_ascii=False),
        '{{query}}': ' OR '.join(f'"{term}"' for term in keywords),
        '{{since_iso}}': since.isoformat().replace('+00:00', 'Z'),
        '{{max_items}}': str(max_items),
    }
    raw = template
    for marker, value in values.items():
        # JSON string values must be encoded when substituted inside quotes.
        replacement = value if marker in ('{{keywords_json}}', '{{max_items}}') else json.dumps(value, ensure_ascii=False)[1:-1]
        raw = raw.replace(marker, replacement)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(f'Invalid Apify input template: {exc.msg}') from None
    if not isinstance(result, dict):
        raise ProviderError('Apify input template must be a JSON object')
    return result


def _apify_item(platform, item, keywords, since):
    if not isinstance(item, dict):
        return None
    title = str(_first(item, 'title', 'headline', 'article.title', default='')).strip()
    text = str(_first(item, 'text', 'full_text', 'tweetText', 'postText', 'message', 'caption',
                      'description', 'snippet', 'article.description', default='')).strip()
    # News benefits from its headline plus summary. Social Actors usually expose
    # the post body in `text`/`caption`; do not ingest replies or comments.
    content = ' — '.join(dict.fromkeys(x for x in (title, text) if x)) if platform == 'news' else (text or title)
    if not content or not matches(content, keywords):
        return None
    published = _timestamp(_first(item, 'publishedAt', 'published_at', 'createdAt', 'created_at', 'takenAt',
                                  'date_utc', 'timestamp', 'date', 'time', 'article.publishedAt'))
    if published < since:
        return None
    url = str(_first(item, 'url', 'postUrl', 'tweetUrl', 'permalink', 'link', 'article.url', default=''))
    external_id = _first(item, 'id', 'postId', 'tweetId', 'shortCode', 'shortcode', 'article.id')
    if not external_id:
        external_id = hashlib.sha256(f'{platform}\0{url}\0{content}\0{published.isoformat()}'.encode()).hexdigest()
    author = _author_name(_first(item, 'authorName', 'pageName', 'author.name', 'author.userName', 'author.username',
                                'author', 'ownerUsername', 'username', 'fullName', 'user.name', 'user',
                                'channelName', 'source', 'publisher', default='Unknown'))
    if platform == 'news' and not _approved_news_source(author):
        return None
    engagement = dict(
        likes=_number(item, 'likesCount', 'likeCount', 'likes', 'favoriteCount', 'stats.likes', 'reactions_count', 'public_metrics.like_count'),
        comments=_number(item, 'commentsCount', 'commentCount', 'comments', 'replyCount', 'stats.comments', 'comments_count', 'public_metrics.reply_count'),
        shares=_number(item, 'sharesCount', 'shareCount', 'shares', 'retweetCount', 'stats.shares', 'reshare_count', 'public_metrics.retweet_count'),
        views=_number(item, 'viewsCount', 'viewCount', 'views', 'impressionCount', 'public_metrics.impression_count'),
    )
    row = post(platform, external_id, author, content, url, published.isoformat(), engagement)
    row.update(source_provider='apify', content_scope='apify-public-post-v1')
    if platform == 'news':
        row['title'] = title
    return row


async def apify_posts(client, platform, secret, keywords, since):
    """Run a configured Apify Actor and normalize its default dataset items.

    Actor output formats vary, so this adapter accepts the common field names
    used by social/news Actors. A custom Actor can use the canonical names
    documented in the README for deterministic mapping.
    """
    actor_id = str(secret.get('actor_id', '')).strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:[~/][A-Za-z0-9_.-]+)?', actor_id):
        raise ProviderError('Invalid or missing Apify Actor ID')
    max_items = min(max(int(secret.get('max_items', config().apify_max_items)), 1), 1000)
    payload = _actor_input(platform, secret.get('input_template', ''), keywords, since, max_items)
    actor_path = quote(actor_id.replace('/', '~'), safe='~')
    url = f'https://api.apify.com/v2/actors/{actor_path}/run-sync-get-dataset-items'
    data = await request(client, 'POST', url,
                         params={'format': 'json', 'clean': '1', 'limit': max_items, 'maxItems': max_items,
                                 'timeout': config().apify_run_timeout_seconds},
                         headers={'Authorization': f'Bearer {secret["api_key"]}', 'Content-Type': 'application/json'},
                         timeout=config().apify_run_timeout_seconds + 15,
                         json=payload)
    if not isinstance(data, list):
        raise ProviderError('Apify Actor did not return a dataset item array')
    rows = []
    invalid = 0
    for item in data:
        try:
            row = _apify_item(platform, item, keywords, since)
        except ProviderError:
            invalid += 1
            continue
        if row:
            rows.append(row)
    if data and invalid == len(data):
        raise ProviderError('Apify output has no usable publication timestamps; check Actor mapping')
    return rows
