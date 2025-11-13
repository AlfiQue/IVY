from __future__ import annotations

from collections import deque
from time import monotonic
from typing import Awaitable, Callable, Deque, Dict

from fastapi import HTTPException, Request, status
from app.core.config import Settings
from app.core.metrics import inc_rate_limited


class RateLimiter:
    def __init__(self, rps: int) -> None:
        self.rps = max(1, rps)
        self.calls: Dict[str, Deque[float]] = {}

    def _bucket(self, request: Request) -> str:
        ip = request.client.host if request.client else "?"
        path = request.url.path
        return f"{ip}:{path}"

    def _check(self, request: Request) -> None:
        bucket = self._bucket(request)
        dq = self.calls.setdefault(bucket, deque())
        now = monotonic()
        while dq and now - dq[0] > 1:
            dq.popleft()
        if len(dq) >= self.rps:
            try:
                inc_rate_limited()
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        dq.append(now)

    async def __call__(self, request: Request, call_next):
        self._check(request)
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


def limit_dependency(rps: int) -> Callable[[Request], Awaitable[None]]:
    limiter = RateLimiter(rps)

    async def dependency(request: Request) -> None:
        limiter._check(request)

    return dependency


class RedisRateLimiter:
    def __init__(self, rps: int, client) -> None:  # type: ignore
        self.rps = rps
        self.client = client

    def _key(self, request: Request) -> str:
        ip = request.client.host if request.client else "?"
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
