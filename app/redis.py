import json
import time
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import get_settings
from app.core.logging import logger

settings = get_settings()

class RedisManager:
    """Manages Redis connection pool and provides caching/rate limiting methods."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._memory_cache: dict[str, tuple[Any, float]] = {}  # fallback in-memory cache (key -> (val, expire_time))

    async def connect(self):
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2.0,
            )
            await self._redis.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"Could not connect to Redis ({e}). Operating with in-memory fallback.")
            self._redis = None

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            logger.info("Closed Redis connection")

    async def get(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return await self._redis.get(key)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        # In-memory fallback
        if key in self._memory_cache:
            val, expires_at = self._memory_cache[key]
            if expires_at == 0 or expires_at > time.time():
                return val
            else:
                del self._memory_cache[key]
        return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if self._redis:
            try:
                await self._redis.set(key, value, ex=ex)
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        # In-memory fallback
        expires_at = time.time() + ex if ex else 0
        self._memory_cache[key] = (value, expires_at)
        return True

    async def delete(self, key: str) -> bool:
        if self._redis:
            try:
                await self._redis.delete(key)
                return True
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        self._memory_cache.pop(key, None)
        return True

    async def get_json(self, key: str) -> Optional[dict]:
        raw = await self.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def set_json(self, key: str, value: dict, ex: Optional[int] = None) -> bool:
        return await self.set(key, json.dumps(value), ex=ex)

    async def check_rate_limit(self, key_identifier: str, limit: int, window_seconds: int = 60) -> tuple[bool, int, int]:
        """
        Sliding window / counter rate limiter.
        Returns (is_allowed, remaining_requests, reset_seconds).
        """
        redis_key = f"{settings.REDIS_RATE_LIMIT_PREFIX}:{key_identifier}"
        now = int(time.time())
        window_bucket = now // window_seconds
        bucket_key = f"{redis_key}:{window_bucket}"

        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(bucket_key)
                pipe.expire(bucket_key, window_seconds * 2)
                res = await pipe.execute()
                count = res[0]
                remaining = max(0, limit - count)
                reset = window_seconds - (now % window_seconds)
                return (count <= limit, remaining, reset)
            except Exception as e:
                logger.warning(f"Redis rate limit check error: {e}")

        # In-memory fallback rate limiter
        val = await self.get(bucket_key)
        count = int(val) + 1 if val else 1
        await self.set(bucket_key, str(count), ex=window_seconds * 2)
        remaining = max(0, limit - count)
        reset = window_seconds - (now % window_seconds)
        return (count <= limit, remaining, reset)


redis_manager = RedisManager()


async def get_redis() -> RedisManager:
    return redis_manager
