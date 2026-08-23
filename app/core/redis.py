from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    redis: Redis = Redis.from_url(str(get_settings().redis_url), decode_responses=True)
    return redis


async def check_rate_limit(
    redis: Redis, *, key: str, max_requests: int, window_seconds: int
) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds).

    A fixed window (vs. sliding/token-bucket) is the simplest thing that's
    still correct for auth-endpoint abuse — bursts at window boundaries are
    an acceptable trade-off for a portfolio-scale service.
    """
    redis_key = f"rate_limit:{key}"
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, window_seconds)

    if count > max_requests:
        ttl = await redis.ttl(redis_key)
        return False, max(ttl, 1)

    return True, 0
