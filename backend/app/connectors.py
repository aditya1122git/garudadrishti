"""Official APIs only. Provider adapters accept a documented normalized HTTPS contract."""
import asyncio
import random
import re
import time
import socket
import ipaddress
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from .config import config


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


async def x_posts(client, secret, keywords, since):
    # Rotation is for token replacement/failover; never evade provider/account quotas.
    tokens = secret.get('tokens') or [secret['api_key']]
    query = '(' + ' OR '.join('"' + k.replace('"', '') + '"' for k in keywords) + ') -is:retweet'
    if len(query) > 512:
        raise ProviderError('X query exceeds 512 characters; reduce keywords')
    params = {'query': query, 'max_results': 100, 'tweet.fields': 'created_at,public_metrics,author_id',
              'start_time': since.isoformat().replace('+00:00', 'Z')}
    rows = []
    for _ in range(10):
        data = None
        for token in tokens:
            try:
                data = await request(client, 'GET', 'https://api.x.com/2/tweets/search/recent', params=params,
                                     headers={'Authorization': f'Bearer {token}'})
            except ProviderError as exc:
                if '(401)' in str(exc):
                    continue
                raise
            break
        if data is None:
            raise ProviderError('No valid X token')
        for p in data.get('data', []):
            m = p.get('public_metrics', {})
            rows.append(post('x', p['id'], p['author_id'], p['text'], f'https://x.com/i/status/{p["id"]}', p['created_at'],
                             dict(likes=m.get('like_count', 0), comments=m.get('reply_count', 0), shares=m.get('retweet_count', 0), views=m.get('impression_count', 0))))
        token = data.get('meta', {}).get('next_token')
        if not token:
            return rows
        params['next_token'] = token
    raise ProviderError('X pagination cap reached; shorten sync window before advancing checkpoint')


async def youtube_posts(client, secret, keywords, since):
    base = 'https://www.googleapis.com/youtube/v3/'
    # One combined query per run, at most 3 search pages; hourly scheduling below.
    params = dict(key=secret['api_key'], part='snippet', type='video', order='date', maxResults=50,
                  q='|'.join(keywords), publishedAfter=since.isoformat().replace('+00:00', 'Z'))
    rows = []
    videos = []
    for _ in range(3):
        data = await request(client, 'GET', base + 'search', params=params)
        videos.extend(data.get('items', []))
        if not data.get('nextPageToken'):
            break
        params['pageToken'] = data['nextPageToken']
    else:
        raise ProviderError('YouTube search pagination cap reached; checkpoint retained')
    # Revisit a bounded set of previously discovered videos to catch newer comments.
    seen = set()
    for v in videos + secret.get('watched_videos', []):
        vid = v['id']['videoId']
        if vid in seen:
            continue
        seen.add(vid)
        s = v['snippet']
        rows.append(post('youtube', vid, s['channelTitle'], s['title'] + '\n' + s.get('description', ''),
                         f'https://www.youtube.com/watch?v={vid}', s['publishedAt']))
        cp = dict(key=secret['api_key'], part='snippet', videoId=vid, maxResults=100, order='time', textFormat='plainText')
        for _ in range(5):
            comments = await request(client, 'GET', base + 'commentThreads', params=cp, comments_optional=True)
            reached_old = False
            for t in comments.get('items', []):
                c = t['snippet']['topLevelComment']; cs = c['snippet']
                if datetime.fromisoformat(cs['publishedAt'].replace('Z', '+00:00')) < since:
                    reached_old = True
                    continue
                if matches(cs['textDisplay'], keywords):
                    rows.append(post('youtube', c['id'], cs['authorDisplayName'], cs['textDisplay'],
                                     f'https://www.youtube.com/watch?v={vid}&lc={c["id"]}', cs['publishedAt'], {'likes': cs['likeCount']}))
            if reached_old or not comments.get('nextPageToken'):
                break
            cp['pageToken'] = comments['nextPageToken']
        else:
            raise ProviderError('YouTube comment pagination cap reached; checkpoint retained')
    secret['watched_videos'] = (videos + secret.get('watched_videos', []))[:30]
    return rows


async def meta_posts(client, platform, secret, keywords, since):
    account = secret['account_id']
    if not account.isdigit():
        raise ProviderError('Meta account ID must be numeric')
    ig = platform == 'instagram'
    edge = 'media' if ig else 'posts'
    fields = 'id,caption,timestamp,permalink,like_count,comments_count' if ig else 'id,message,created_time,permalink_url,shares'
    url = f'https://graph.facebook.com/{config().meta_graph_version}/{account}/{edge}'
    params = dict(fields=fields, limit=100, since=int(since.timestamp()))
    rows = []
    for _ in range(10):
        data = await request(client, 'GET', url, params=params, headers={'Authorization': f'Bearer {secret["api_key"]}'})
        for p in data.get('data', []):
            content = p.get('caption' if ig else 'message', '')
            timestamp = p['timestamp' if ig else 'created_time']
            if matches(content, keywords) and datetime.fromisoformat(timestamp.replace('Z', '+00:00')) >= since:
                rows.append(post(platform, p['id'], account, content, p.get('permalink' if ig else 'permalink_url', ''), timestamp,
                                 dict(likes=p.get('like_count', 0), comments=p.get('comments_count', 0), shares=p.get('shares', {}).get('count', 0))))
        paging = data.get('paging', {})
        if not paging.get('next'):
            return rows
        params['after'] = paging['cursors']['after']
    raise ProviderError('Meta pagination cap reached; checkpoint retained')


async def aggregator_posts(client, platform, secret, keywords, since):
    # Vendor-specific payload/auth mapping lives in the organization's trusted adapter.
    endpoint = secret['endpoint']
    await validate_destination(endpoint)
    rows = []
    cursor = None
    for _ in range(10):
        data = await request(client, 'POST', endpoint, headers={'Authorization': f'Bearer {secret["api_key"]}'},
                             json=dict(platform=platform, keywords=keywords, since=since.isoformat(), cursor=cursor))
        for p in data['posts']:
            rows.append(post(platform, p['id'], p['author'], p['content'], p['url'], p['published_at'], p.get('engagement')))
        cursor = data.get('next_cursor')
        if not cursor:
            return rows
    raise ProviderError('Aggregator pagination cap reached; checkpoint retained')
