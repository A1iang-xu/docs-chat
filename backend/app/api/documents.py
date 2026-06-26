"""文档 API —— 上传、异步解析任务、文档状态。"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from app.models.schemas import DocumentJob
from app.services.ingestion_service import ingestion_service
from app.services.mineru_document_service import mineru_document_service
from app.services.retrieval_service import retrieval_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".html", ".json"}


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


@router.get("/jobs/{job_id}", response_model=DocumentJob)
async def get_job(job_id: str):
    job = ingestion_service.get_job(job_id)
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
