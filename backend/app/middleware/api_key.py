"""v4.0: API Key 验证中间件 —— 公网 Demo 防护"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Bearer Token 校验中间件。

    DEMO_API_KEY_REQUIRED=true 时生效。
    健康检查端点始终放行。
    """

    # v4.0 需要 auth 的路径——仅限非只读操作
    _SKIP_PATHS = {
        "/health",
        "/health/services",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    async def dispatch(self, request, call_next):
        if not settings.DEMO_API_KEY_REQUIRED:
            return await call_next(request)

        # 健康检查 + openapi doc 始终放行
        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key", "code": "unauthorized"},
            )

        token = auth[len("Bearer "):]
        if settings.DEMO_API_KEY and token != settings.DEMO_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key", "code": "unauthorized"},
            )

        return await call_next(request)
