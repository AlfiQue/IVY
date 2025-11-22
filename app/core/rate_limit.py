from __future__ import annotations

from collections import deque
from time import monotonic
from typing import Deque, Optional

from fastapi import HTTPException, Request, status
from app.core.config import Settings
from app.core.metrics import inc_rate_limited


class RateLimiter:
    def __init__(self, rps: int) -> None:
        self.rps = rps
        self.calls: Deque[float] = deque()

    def _check(self) -> None:
        now = monotonic()
        while self.calls and now - self.calls[0] > 1:
            self.calls.popleft()
        if len(self.calls) >= self.rps:
            try:
                inc_rate_limited()
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        self.calls.append(now)

    async def __call__(self, request: Request, call_next):
        self._check()
        return await call_next(request)


def rate_limit_middleware(rps: int) -> RateLimiter:
    # Try Redis backend if configured
    settings = Settings()
    if settings.rate_limit_backend.lower() == "redis" and settings.redis_url:
        try:
            import redis  # type: ignore

            return RedisRateLimiter(rps, redis.from_url(settings.redis_url))  # type: ignore
        except Exception:
            pass
    return RateLimiter(rps)


class RedisRateLimiter:
    def __init__(self, rps: int, client) -> None:  # type: ignore
        self.rps = rps
        self.client = client

    def _key(self, request: Request) -> str:
        ip = (request.client.host if request.client else "?")
        path = request.url.path
        return f"ivy:rl:{path}:{ip}"

    async def __call__(self, request: Request, call_next):
        try:
            key = self._key(request)
            pipe = self.client.pipeline()
            pipe.incr(key, 1)
            pipe.expire(key, 1)
            res = pipe.execute()
            count = int(res[0]) if res else 0
            if count > self.rps:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        except HTTPException:
            raise
        except Exception:
            # Fallback soft-fail to next handler
            pass
        return await call_next(request)
