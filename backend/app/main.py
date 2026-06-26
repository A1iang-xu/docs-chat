"""FastAPI 应用入口 —— 挂载路由、配置 CORS、启动服务"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.libraries import router as libraries_router  # v4.0
from app.api.stats import router as stats_router  # v4.0
from app.api.feedback import router as feedback_router  # v4.0
from app.api.evaluation import router as evaluation_router  # v4.3

# ── 日志配置 ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时恢复轻量索引，按需预加载重模型。"""
    logger.info("DocsChat 启动中...")
    try:
        from app.services.retrieval_service import retrieval_service
        from app.services.vector_store import vector_store
        from collections import defaultdict
        chunks = vector_store.get_all_chunks()
        if chunks:
            # v4.0: 按 library 分组重建 BM25
            by_library: dict[str, list[dict]] = defaultdict(list)
            for c in chunks:
                lib = c.get("library", "") or "default"
                by_library[lib].append(c)
            for lib, lib_chunks in by_library.items():
                retrieval_service.build_bm25_index(lib_chunks, library=lib)
            logger.info("BM25 索引恢复完成: %d 个库, %d chunks", len(by_library), len(chunks))
    except Exception as e:
        logger.warning(f"BM25 索引恢复失败: {e}")

    if settings.PRELOAD_RERANKER:
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

# v4.0: API Key 中间件（在 CORS 之后）
from app.middleware.api_key import ApiKeyMiddleware
app.add_middleware(ApiKeyMiddleware)

# v4.4: 速率限制中间件（在 API Key 之后）
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# ── 路由注册 ──
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(libraries_router)  # v4.0
app.include_router(stats_router)      # v4.0
app.include_router(feedback_router)   # v4.0
app.include_router(evaluation_router) # v4.3


# ═══════════════════════════════════════════
# 健康检查 & 外部模型服务调试
# ═══════════════════════════════════════════

@app.get("/health")
async def health_check():
    """基础健康检查 —— Docker healthcheck 使用。"""
    return {"status": "ok", "service": "DocsChat API"}


@app.get("/health/services")
async def health_services():
    """外部模型服务诊断端点。

    返回所有外部依赖（MinerU, BGE-M3 Embedding, Qwen-Reranker, DeepSeek LLM）
    的连接状态和配置信息。用于上线前的集成测试验证。
    """
    from app.services.vector_store import vector_store

    report = {
        "version": "0.1.0",
        "chunk_count": vector_store.get_chunk_count(),

        "mineru": await _mineru_health(),
        "embedding": _embedding_health(),
        "reranker": await _reranker_health(),
        "deepseek": _deepseek_health(),
        "quality_gate": _quality_gate_health(),
    }

    all_healthy = all(
        item.get("available", True)
        for section in ["mineru", "embedding", "reranker", "deepseek", "quality_gate"]
        for item in [report[section]]
        if isinstance(item, dict)
    )

    report["all_healthy"] = all_healthy
    return report


async def _mineru_health() -> dict:
    """探测 MinerU 服务状态。"""
    result = {
        "parser_type": settings.PARSER_TYPE,
        "mineru_url": settings.MINERU_URL or "(not set)",
        "mode": "fallback" if settings.PARSER_TYPE == "fallback" else ("api" if settings.MINERU_URL else "cli"),
        "available": True,
    }
    if settings.PARSER_TYPE == "fallback":
        result["mode"] = "pypdf (fallback)"
    elif settings.MINERU_URL:
        result["mode"] = "api"
        try:
            from app.services.mineru_document_service import mineru_document_service
            health = await mineru_document_service.check_mineru_api_health()
            result.update(health)
        except Exception as exc:
            result["available"] = False
            result["reason"] = str(exc)
    elif settings.MINERU_COMMAND:
        result["mode"] = "cli"
        result["command"] = settings.MINERU_COMMAND[:80]
        result["available"] = True
    else:
        result["available"] = False
        result["reason"] = "MINERU_URL / MINERU_COMMAND 均未配置"
    return result


def _embedding_health() -> dict:
    """Embedding 服务状态。"""
    return {
        "provider": settings.EMBEDDING_PROVIDER,
        "model": settings.EMBEDDING_MODEL,
        "dim": settings.EMBEDDING_DIM,
        "bge_m3_enabled": settings.ENABLE_BGE_M3,
        "api_base": settings.EMBEDDING_API_BASE or "(not set)",
        "available": True,  # chromadb_default 总是可用
    }


async def _reranker_health() -> dict:
    """Reranker 服务状态。"""
    try:
        from app.services.reranker_service import reranker
        return await reranker.check_health()
    except Exception as exc:
        return {
            "mode": "error",
            "model": settings.RERANKER_MODEL,
            "reranker_type": settings.RERANKER_TYPE,
            "available": False,
            "reason": str(exc),
        }


def _deepseek_health() -> dict:
    """DeepSeek LLM 服务配置状态。"""
    has_key = bool(settings.DEEPSEEK_API_KEY and not settings.DEEPSEEK_API_KEY.startswith("sk-your-"))
    return {
        "configured": has_key,
        "model": settings.DEEPSEEK_MODEL,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "available": has_key,
    }


def _quality_gate_health() -> dict:
    """质量门禁配置状态。"""
    return {
        "enabled": settings.QG_ENABLED,
        "min_chars": settings.QG_MIN_CHARS,
        "min_headings": settings.QG_MIN_HEADINGS,
        "min_tables": settings.QG_MIN_TABLES,
        "min_pages": settings.QG_MIN_PAGES,
        "available": True,
    }
