"""文档 API —— 上传、URL 抓取、异步解析任务、文档状态。"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.models.schemas import DocumentJob
from app.services.ingestion_service import ingestion_service
from app.services.mineru_document_service import mineru_document_service
from app.services.retrieval_service import retrieval_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".html", ".json"}


class FetchUrlRequest(BaseModel):
    """v4.5: URL 抓取入库请求"""
    filename: str = Field(..., min_length=1)
    library: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)


@router.post("/upload", response_model=DocumentJob)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    library: Optional[str] = Query(default=None, description="v4.0: 指定文档库（默认 default）"),
):
    """上传文档（v4.0: 支持 PDF/TXT/MD/HTML/JSON）后立即返回异步解析任务。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = Path(file.filename).suffix.lower()
    # v4.0: 放宽仅 PDF 的限制，支持常见文档格式
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    safe_name = _safe_filename(file.filename)
    file_path = Path(mineru_document_service.upload_dir) / safe_name
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with file_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
    except Exception as exc:
        logger.exception("保存上传文件失败")
        raise HTTPException(status_code=500, detail=f"保存上传文件失败: {exc}") from exc

    job = ingestion_service.create_job(file_path=file_path, original_filename=safe_name)
    # v4.0: 传递 library 参数
    state = ingestion_service._jobs.get(job.job_id)
    if state and library:
        state.library = library
    background_tasks.add_task(ingestion_service.run_job, job.job_id)
    logger.info("文档上传成功，已创建摄取任务: %s %s (library=%s)", job.job_id, safe_name, library or "default")
    return job


@router.post("/fetch", response_model=DocumentJob)
async def fetch_url(request: FetchUrlRequest):
    """v4.5: 提交文档 URL，异步抓取入库。"""
    from app.services.web_ingestion_service import web_ingestion_service

    job_id = await web_ingestion_service.ingest_url(
        url=request.url,
        library_slug=request.library,
        version="latest",
    )
    job = web_ingestion_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="任务创建失败")
    logger.info("URL 抓取任务已创建: %s library=%s url=%s", job_id, request.library, request.url)
    return job


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """v4.5: 删除指定文档及其所有 chunks。"""
    from app.services.vector_store import vector_store

    deleted = vector_store.delete_document(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"文档 '{doc_id}' 不存在或已为空")
    logger.info("文档 '%s' 已删除，移除 %d 个 chunks", doc_id, deleted)
    return {"status": "deleted", "document": doc_id, "chunks_removed": deleted}


@router.get("/jobs/{job_id}", response_model=DocumentJob)
async def get_job(job_id: str):
    """查询异步任务状态（支持上传任务和 URL 抓取任务）。"""
    job = ingestion_service.get_job(job_id)
    if job is None:
        from app.services.web_ingestion_service import web_ingestion_service
        job = web_ingestion_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/jobs", response_model=list[DocumentJob])
async def list_jobs():
    return ingestion_service.list_jobs()


@router.get("/")
async def list_documents():
    return vector_store.get_unique_documents()


@router.get("/status")
async def get_status():
    return {
        "chunk_count": vector_store.get_chunk_count(),
        "has_bm25_index": retrieval_service.bm25 is not None,
        "jobs": [job.model_dump() for job in ingestion_service.list_jobs()],
    }


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", filename).strip("._")
    return cleaned or "document.pdf"
