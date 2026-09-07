"""Best-effort Redis cache for dashboard aggregates.

The versioned key avoids a stale request repopulating the cache after an
invalidation. Redis is deliberately optional: reporting remains available from
PostgreSQL if it is down or not configured.
"""

import json
import logging
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_VERSION_KEY = "dashboard:summary:version:v2"


@lru_cache(maxsize=1)
def _client() -> Redis | None:
    url = get_settings().REDIS_URL
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.25, socket_timeout=0.5) if url else None


def _safe(operation: str, callback, default: Any = None) -> Any:
    client = _client()
    if client is None:
        return default
    try:
        return callback(client)
    except RedisError:
        logger.warning("Dashboard cache %s failed; falling back to PostgreSQL", operation, exc_info=True)
        return default


def dashboard_cache_version() -> str:
    return str(_safe("version lookup", lambda client: client.get(_VERSION_KEY), "0") or "0")


def get_dashboard_summary(version: str) -> dict[str, Any] | None:
    value = _safe("read", lambda client: client.get(f"dashboard:summary:v2:{version}"))
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def set_dashboard_summary(version: str, payload: dict[str, Any]) -> None:
    ttl = get_settings().DASHBOARD_CACHE_TTL_SECONDS
    _safe("write", lambda client: client.setex(f"dashboard:summary:v2:{version}", ttl, json.dumps(payload)))


def invalidate_dashboard_summary() -> None:
    """Make the next read use a fresh cache key after a committed mutation."""
    _safe("invalidation", lambda client: client.incr(_VERSION_KEY))
