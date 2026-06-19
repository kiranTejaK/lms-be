import json
import hashlib
import inspect
from functools import wraps
from typing import Optional

import redis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=int(settings.REDIS_NAME) if settings.REDIS_NAME else 0,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)

# 🔹 Base prefix (shared)
def _base_prefix(module: str) -> str:
    return f"{settings.APP_PREFIX}:{settings.CACHE_VERSION}:{module}"

# 🔹 Hash helper for query params
def _hash_payload(*args, **kwargs) -> str:
    payload = {
        "args": args,
        "kwargs": kwargs
    }
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(payload_str.encode()).hexdigest()

# 🔹 Query key (pagination / filters)
def query_key_generator(module: str, resource: str, *args, **kwargs) -> str:
    hash_str = _hash_payload(*args, **kwargs)
    return f"{_base_prefix(module)}:{resource}:query:{hash_str}"

# 🔹 Entity key (single item)
def entity_key_generator(module: str, resource: str, entity_id: str) -> str:
    return f"{_base_prefix(module)}:{resource}:entity:{entity_id}"

def cache_get(key: str) -> Optional[str]:
    try:
        return redis_client.get(key)
    except redis.RedisError as exc:
        logger.warning("redis_get_failed", key=key, error=str(exc))
        return None

def cache_set(key: str, value: str, expire_seconds: int = 3600) -> None:
    try:
        redis_client.setex(key, expire_seconds, value)
    except redis.RedisError as exc:
        logger.warning("redis_set_failed", key=key, error=str(exc))

def clear_cache(key_pattern: str) -> None:
    try:
        keys = redis_client.keys(key_pattern)
        if keys:
            redis_client.delete(*keys)
            logger.debug("cache_cleared", pattern=key_pattern, count=len(keys))
    except redis.RedisError as exc:
        logger.warning("redis_clear_failed", pattern=key_pattern, error=str(exc))

def extract_entity_id(func, args, kwargs):
    try:
        bound_args = inspect.signature(func).bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Prefer *_id
        for name, value in bound_args.arguments.items():
            if name.endswith("_id"):
                return value

        # Fallback to "id"
        if "id" in bound_args.arguments:
            return bound_args.arguments["id"]

    except Exception:
        pass

    return "all"

def build_cache_key(key_generator_func, func, args, kwargs, generator_kwargs):
    module = generator_kwargs.get("module", "default")
    resource = generator_kwargs.get("resource", "default")

    if key_generator_func == query_key_generator:
        return query_key_generator(module, resource, *args, **kwargs)
    entity_id = extract_entity_id(func, args, kwargs)
    return entity_key_generator(module, resource, str(entity_id))

def serialize_result(result):
    def normalize(obj):
        # SQLAlchemy models — dump columns only (no relationships)
        if hasattr(obj, "__table__"):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

        # Dicts (e.g. get_users returns {"users": [...], "total": int})
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()}

        # Lists
        if isinstance(obj, list):
            return [normalize(item) for item in obj]

        return obj

    return json.dumps(normalize(result), default=str)

def redis_cache(key_generator_func, expire_seconds: int = 3600, **generator_kwargs):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = build_cache_key(key_generator_func, func, args, kwargs, generator_kwargs)

            cached = cache_get(key)
            if cached is not None:
                return json.loads(cached)

            result = func(*args, **kwargs)

            serialized = serialize_result(result)
            cache_set(key, serialized, expire_seconds)

            return result

        return wrapper
    return decorator
