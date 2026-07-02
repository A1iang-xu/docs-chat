"""v4.0: 文档库管理 API —— URL 抓取入库与库清单查询"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.schemas import DocumentJob, IngestUrlRequest, LibraryInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.post("/ingest-url", response_model=DocumentJob)
async def ingest_url(request: IngestUrlRequest):
    """提交文档站 URL，异步抓取入库。

    示例请求体:
        {"url": "https://vuejs.org/guide/introduction.html",
         "library_slug": "vue",
         "version": "latest"}
    """
    from app.services.web_ingestion_service import web_ingestion_service

    job_id = await web_ingestion_service.ingest_url(
        url=request.url,
        library_slug=request.library_slug,
        version=request.version,
    )
    job = web_ingestion_service.get_job(job_id)
    if job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="任务创建失败")
    return job


@router.get("/ingest-jobs/{job_id}", response_model=DocumentJob)
async def get_ingest_job(job_id: str):
    """查询 URL 抓取任务状态。"""
    from app.services.web_ingestion_service import web_ingestion_service

    job = web_ingestion_service.get_job(job_id)
    if job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/ingest-jobs", response_model=list[DocumentJob])
async def list_ingest_jobs():
    """列出所有 URL 抓取任务。"""
    from app.services.web_ingestion_service import web_ingestion_service
    return web_ingestion_service.list_jobs()


@router.get("/", response_model=list[LibraryInfo])
async def list_libraries():
    """返回所有已入库的文档库。"""
    import asyncio
    from app.services.vector_store import vector_store

    return await asyncio.to_thread(vector_store.get_libraries)


@router.post("/")
async def create_library(request: dict):
    """v4.5: 创建文档库（空库，不包含文档）。"""
    import asyncio
    library_name = request.get("library", "").strip()
    if not library_name:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    from app.services.vector_store import vector_store
    try:
        existing = await asyncio.to_thread(vector_store.get_libraries)
        if any(lib.library == library_name for lib in existing):
            return {"status": "exists", "library": library_name, "message": "知识库已存在"}
    except Exception:
        pass
    # 持久化注册空库
    vector_store.register_library(library_name)
    return {"status": "created", "library": library_name, "message": "知识库已就绪，请通过文档入库添加文档"}


@router.delete("/{library}")
async def delete_library(library: str):
    """v4.5: 删除指定文档库及其所有 chunks。"""
    if library == "default":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="不能删除默认文档库，请使用 /documents/clear 清空全部数据")
    from app.services.vector_store import vector_store
    deleted = vector_store.delete_library(library)
    if deleted == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"文档库 '{library}' 不存在或已为空")
    # -1 表示仅删除了注册表空库记录
    if deleted == -1:
        deleted = 0
    # 清除 BM25 索引
    try:
        from app.services.retrieval_service import retrieval_service
        if library in retrieval_service.bm25_indexes:
            del retrieval_service.bm25_indexes[library]
    except Exception:
        pass
    # 清除缓存
    try:
        from app.services.semantic_cache import semantic_cache
        await semantic_cache.clear()
    except Exception:
        pass
    try:
        from app.services.cache_service import cache_service
        cache_service.invalidate()
    except Exception:
        pass
    return {"status": "deleted", "library": library, "chunks_removed": deleted}
