"""SSE 鉴权与用户级限流。"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import settings


class TokenBucketLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True


class SecurityService:
    def __init__(self) -> None:
        self.limiter = TokenBucketLimiter(
            max_requests=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )

    def get_user_id(self, request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            if settings.AUTH_REQUIRED:
                raise HTTPException(status_code=401, detail="缺少 Bearer Token")
            return request.client.host if request.client else "anonymous"

        token = auth.removeprefix("Bearer ").strip()
        if settings.AUTH_REQUIRED:
            self._validate_token_shape(token)
        return token[-24:] if len(token) >= 24 else token

    def ensure_allowed(self, user_id: str) -> None:
        if not self.limiter.allow(user_id):
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

    def _validate_token_shape(self, token: str) -> None:
        if not token or len(token) < 20:
            raise HTTPException(status_code=401, detail="Token 无效")


security_service = SecurityService()
