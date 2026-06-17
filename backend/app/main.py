"""FastAPI 应用入口 —— 挂载路由、配置 CORS、启动服务"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router

# ── 日志配置 ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预加载 Reranker 模型，避免首次请求等待下载"""
    logger.info("DocsChat 启动中...")
    try:
        from app.services.reranker_service import reranker
        reranker._lazy_load()
        logger.info("Reranker 模型预加载完成")
    except Exception as e:
        logger.warning(f"Reranker 预加载失败（首次请求时将自动重试）: {e}")
    yield
    logger.info("DocsChat 关闭")


app = FastAPI(
    title="DocsChat API",
    description="RAG 智能对话系统后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──
app.include_router(chat_router)
app.include_router(documents_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocsChat API"}


# ── 启动入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)