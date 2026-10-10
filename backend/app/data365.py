"""Data365 asynchronous fallback for public social post searches."""
import asyncio
import hashlib
import math
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from .config import (
    DATA365_MAX_ITEMS,
    DATA365_POLL_INTERVAL_SECONDS,
    DATA365_TASK_TIMEOUT_SECONDS,
    REDDIT_MAX_ITEMS,
)
from .connectors import (
    ProviderError,
    REDDIT_SEARCH_GROUPS,
    X_MATCH_ALIASES,
    X_OFFICIAL_HANDLES,
    _author_name,
    _first,
    _number,
    _timestamp,
    matches,
    post,
    request,
)


DATA365_BASE_URL = 'https://api.data365.co/v1.1'


def _data365_queries(platform, keywords):
    """Keep fallback searches focused while limiting paid Data365 tasks."""
    active = {str(keyword).strip().casefold() for keyword in keywords if str(keyword).strip()}
    queries = [query for triggers, query in REDDIT_SEARCH_GROUPS
               if any(trigger.casefold() in active for trigger in triggers)]
    if not queries:
        raise ProviderError('No supported Data365 search terms are active')
    if platform == 'instagram':
        # Data365's documented Instagram discovery flow is hashtag based.
        return [re.sub(r'[^\w]+', '', query, flags=re.UNICODE) for query in queries]
    if platform in {'x', 'reddit'}:
        return [' OR '.join(f'"{query}"' for query in queries)]
    return queries


def _data365_request_spec(platform, query, since, max_posts):
    """Return create/status/items URLs and parameters from Data365 v1.1."""
    from_date = since.date().isoformat()
    to_date = datetime.now(timezone.utc).date().isoformat()
    if platform == 'x':
        root = f'{DATA365_BASE_URL}/twitter/search/post'
        identity = {'keywords': query, 'search_type': 'latest',
                    'from_date': from_date, 'to_date': to_date}
        return (
            root + '/update', {**identity, 'max_posts': max_posts, 'load_replies': 'false'},
            root + '/update', identity,
            root + '/posts', {**identity, 'max_page_size': max_posts, 'order_by': 'date_desc'},
        )
    if platform == 'instagram':
        root = f'{DATA365_BASE_URL}/instagram/tag/{quote(query, safe="")}'
        return (
            root + '/update', {'from_date': from_date, 'sort_type': 'recent',
                               'load_posts': 'true', 'load_posts_data': 'false',
                               'max_posts': max_posts, 'load_comments': 'false'},
            root + '/update', {},
            root + '/posts', {'sort_type': 'recent', 'from_date': from_date,
                              'to_date': to_date, 'max_page_size': max_posts,
                              'order_by': 'date_desc'},
        )
    if platform == 'facebook':
        root = f'{DATA365_BASE_URL}/facebook/search/{quote(query, safe="")}/posts/latest'
        identity = {'from_date': from_date, 'to_date': to_date}
        return (
            root + '/update', {**identity, 'max_posts': max_posts, 'load_comments': 'false',
                               'load_reactors': 'false', 'load_shares': 'false'},
            root + '/update', identity,
            root + '/posts', {**identity, 'max_page_size': max_posts, 'order_by': 'date_desc'},
        )
    if platform == 'reddit':
        root = f'{DATA365_BASE_URL}/reddit/search/post'
        identity = {'keywords': query, 'sort_type': 'new', 'include_over_18': 'false'}
        return (
            root + '/update', {**identity, 'from_date': from_date, 'max_posts': max_posts},
            root + '/update', identity,
            root + '/items', {**identity, 'from_date': from_date, 'to_date': to_date,
                              'max_page_size': max_posts, 'order_by': 'date_desc'},
        )
    raise ProviderError(f'Data365 does not support platform {platform}')


def _data365_task_status(payload):
    if not isinstance(payload, dict):
        return ''
    data = payload.get('data')
    if isinstance(data, dict):
        return str(data.get('status') or data.get('task_status') or '').strip().casefold()
    return str(payload.get('status') or '').strip().casefold()


def _data365_result_items(payload):
    if not isinstance(payload, dict):
        return []
    data = payload.get('data', payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('items', 'posts', 'data'):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _data365_item(platform, item, keywords, since):
    if not isinstance(item, dict):
        return None
    title = str(_first(item, 'title', default='')).strip()
    text = str(_first(item, 'text', 'description', 'caption', default='')).strip()
    content = f'{title}\n{text}'.strip() if platform == 'reddit' else text or title
    author_handle = str(_first(item, 'author_username', 'owner_username', default='')).strip().lstrip('@')
    official_x_post = platform == 'x' and author_handle.casefold() in X_OFFICIAL_HANDLES
    if not content or not (matches(content, [*keywords, *X_MATCH_ALIASES] if platform == 'x' else keywords)
                           or official_x_post):
        return None
    published = _timestamp(_first(item, 'created_time', 'timestamp', 'created_at'))
    if published < since:
        return None
    external_id = _first(item, 'id', 'post_id', 'shortcode')
    url = str(_first(item, 'post_url', 'url', 'permalink', default='')).strip()
    if not url:
        if platform == 'x' and external_id and author_handle:
            url = f'https://x.com/{author_handle}/status/{external_id}'
        elif platform == 'instagram' and _first(item, 'shortcode'):
            url = f'https://www.instagram.com/p/{_first(item, "shortcode")}/'
        elif platform == 'facebook' and external_id:
            url = f'https://www.facebook.com/{external_id}'
    if not external_id:
        external_id = hashlib.sha256(
            f'{platform}\0{url}\0{content}\0{published.isoformat()}'.encode()
        ).hexdigest()
    author = _author_name(_first(
        item, 'author_username', 'owner_full_name', 'owner_username', 'author_name', default='Unknown',
    ))
    engagement = dict(
        likes=_number(item, 'favorite_count', 'likes_count', 'reactions_total_count', 'score'),
        comments=_number(item, 'reply_count', 'comments_count'),
        shares=_number(item, 'retweet_count', 'share_count', 'shares_count'),
        views=_number(item, 'view_count', 'video_views_count', 'video_view_count'),
    )
    row = post(platform, external_id, author, content, url, published.isoformat(), engagement)
    row.update(source_provider='data365', content_scope='data365-public-post-v1')
    return row


async def _run_data365_search(client, platform, token, query, since, max_posts):
    create_url, create_params, status_url, status_params, items_url, items_params = (
        _data365_request_spec(platform, query, since, max_posts)
    )
    await request(client, 'POST', create_url,
                  params={**create_params, 'access_token': token}, timeout=30)
    deadline = time.monotonic() + DATA365_TASK_TIMEOUT_SECONDS
    while True:
        payload = await request(client, 'GET', status_url,
                                params={**status_params, 'access_token': token}, timeout=30)
        status = _data365_task_status(payload)
        if status == 'finished':
            break
        if status in {'fail', 'failed', 'canceled', 'cancelled', 'unknown'}:
            raise ProviderError(f'Data365 search task ended with status {status}')
        if time.monotonic() >= deadline:
            raise ProviderError('Data365 search task timed out; retry next scheduled run')
        await asyncio.sleep(DATA365_POLL_INTERVAL_SECONDS)
    payload = await request(client, 'GET', items_url,
                            params={**items_params, 'access_token': token}, timeout=30)
    return _data365_result_items(payload)


async def data365_posts(client, platform, secret, keywords, since):
    """Search Data365 and normalize public posts into the shared post schema."""
    token = str(secret.get('data365_api_token', '')).strip()
    if not token:
        raise ProviderError('Missing Data365 API token')
    queries = _data365_queries(platform, keywords)
    total_limit = REDDIT_MAX_ITEMS if platform == 'reddit' else DATA365_MAX_ITEMS
    per_query = max(1, math.ceil(total_limit / len(queries)))
    # Facebook and Instagram use several focused searches. One provider task
    # must not discard usable rows returned by the other tasks.
    results = await asyncio.gather(*(
        _run_data365_search(client, platform, token, query, since, per_query)
        for query in queries
    ), return_exceptions=True)
    unique = {}
    errors = []
    invalid = 0
    raw_count = 0
    for items in results:
        if isinstance(items, Exception):
            errors.append(items)
            continue
        raw_count += len(items)
        for item in items:
            try:
                row = _data365_item(platform, item, keywords, since)
            except ProviderError:
                invalid += 1
                continue
            if row:
                unique[row['external_id']] = row
    if raw_count and invalid == raw_count:
        raise ProviderError('Data365 output has no usable publication timestamps; check API mapping')
    if errors and not unique:
        first = errors[0]
        if isinstance(first, ProviderError):
            raise first
        raise ProviderError('Data365 search tasks failed') from None
    return list(unique.values())[:total_limit]
