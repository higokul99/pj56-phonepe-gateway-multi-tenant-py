from fastapi import Request
from app.config import get_settings
from app.core.exceptions import RateLimitExceededException
from app.redis import get_redis

settings = get_settings()


async def check_api_key_rate_limit(key_prefix: str, custom_limit: int = 0) -> None:
    """
    Checks if the caller with the given API key prefix has exceeded their rate limit.
    Raises RateLimitExceededException if limit exceeded.
    """
    redis_mgr = await get_redis()
    limit = custom_limit or settings.RATE_LIMIT_PER_MINUTE
    allowed, remaining, reset_time = await redis_mgr.check_rate_limit(
        key_identifier=key_prefix,
        limit=limit,
        window_seconds=60,
    )
    if not allowed:
        raise RateLimitExceededException(
            f"Rate limit exceeded ({limit} requests/min). Try again in {reset_time}s."
        )
