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
