"""v4.4: 速率限制中间件 —— 基于 IP 的滑动窗口限流

使用内存字典实现，无需 Redis 依赖。
每个 IP 在 RATE_LIMIT_WINDOW_SECONDS 秒内最多 RATE_LIMIT_REQUESTS 次请求。
"""
import time
import logging
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按 IP 地址的滑动窗口速率限制。"""

    # 健康检查等端点不限流
    _SKIP_PATHS = {
        "/health",
        "/health/services",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }

    # v4.5: GET 只读端点不限流（监控面板自动刷新不应被限流）
    _SKIP_GET_PREFIXES = (
        "/stats",
        "/feedback/stats",
        "/evaluation/latest",
        "/evaluation/history",
        "/documents/jobs",
        "/documents/status",
        "/libraries",
    )

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._max_requests = settings.RATE_LIMIT_REQUESTS
        self._window = settings.RATE_LIMIT_WINDOW_SECONDS

    async def dispatch(self, request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # 跳过健康检查等端点
        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        # v4.5: GET 只读端点跳过限流（监控面板自动刷新不应被限流）
        if request.method == "GET":
            for prefix in self._SKIP_GET_PREFIXES:
                if request.url.path.startswith(prefix):
                    return await call_next(request)

        # 获取客户端 IP（支持代理转发）
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        now = time.time()
        ip_queue = self._requests[client_ip]

        # 清除窗口外的旧记录
        while ip_queue and ip_queue[0] < now - self._window:
            ip_queue.popleft()

        # 检查是否超限
        if len(ip_queue) >= self._max_requests:
            retry_after = int(self._window - (now - ip_queue[0]))
            logger.warning("速率限制触发: IP=%s, count=%d", client_ip, len(ip_queue))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"请求过于频繁，请 {retry_after} 秒后重试",
                    "code": "rate_limited",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        # 记录本次请求
        ip_queue.append(now)

        # 定期清理空队列防止内存泄漏
        if len(self._requests) > 10000:
            self._cleanup_stale_entries(now)

        return await call_next(request)

    def _cleanup_stale_entries(self, now: float) -> None:
        """清理过期的 IP 记录。"""
        stale_keys = [
            ip for ip, queue in self._requests.items()
            if not queue or queue[-1] < now - self._window
        ]
        for key in stale_keys:
            del self._requests[key]
        logger.debug("速率限制清理: %d stale IPs removed", len(stale_keys))
