"""异步文档摄取编排服务。"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict
from uuid import uuid4

from app.core.config import settings
from app.models.schemas import DocumentJob
from app.services.retrieval_service import retrieval_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


@dataclass
class IngestionJobState:
    job_id: str
    filename: str
    status: JobStatus
    file_path: Path
    page_count: int = 0
    chunk_count: int = 0
    error: str | None = None
    library: str = ""       # v4.0: 所属文档库
    source_url: str = ""    # v4.0: 来源 URL
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_schema(self) -> DocumentJob:
        return DocumentJob(
            job_id=self.job_id,
            filename=self.filename,
            status=self.status.value,
            page_count=self.page_count,
            chunk_count=self.chunk_count,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class IngestionService:
    """控制解析并发，并记录上传任务状态。"""

    def __init__(self) -> None:
        self._jobs: Dict[str, IngestionJobState] = {}
        self._sem = asyncio.Semaphore(settings.INGESTION_MAX_CONCURRENT_JOBS)

    def create_job(self, file_path: Path, original_filename: str) -> DocumentJob:
        now = datetime.now()
        state = IngestionJobState(
            job_id=uuid4().hex,
            filename=original_filename,
            status=JobStatus.QUEUED,
            file_path=file_path,
            created_at=now,
            updated_at=now,
        )
        self._jobs[state.job_id] = state
        return state.to_schema()

    def get_job(self, job_id: str) -> DocumentJob | None:
        state = self._jobs.get(job_id)
        return state.to_schema() if state else None

    def list_jobs(self) -> list[DocumentJob]:
        return [state.to_schema() for state in self._jobs.values()]

    async def run_job(self, job_id: str) -> None:
        state = self._jobs[job_id]
        async with self._sem:
            self._mark(state, JobStatus.RUNNING)
            try:
                from app.services.mineru_document_service import mineru_document_service

                chunks = await mineru_document_service.load_and_split(state.file_path)
                if not chunks:
                    raise ValueError("文档解析完成，但未生成可入库的有效分块")

                # ── 质量门禁 ──
                from app.services.quality_gate import quality_gate
                markdown_source = ""
                try:
                    markdown_source = str(state.file_path.read_bytes())
                except Exception:
                    pass  # 非文本文件回退
                qg_report = quality_gate.validate(
                    document_name=state.filename,
                    chunks=chunks,
                    markdown_source=markdown_source,
                )
                logger.info("质量门禁报告: %s", qg_report.to_dict())
                if not qg_report.passed:
                    logger.warning("质量门禁不通过但仍继续入库: %s", state.filename)

                state.page_count = max((chunk.page for chunk in chunks), default=0)
                state.chunk_count = await asyncio.to_thread(vector_store.add_chunks, chunks)

                # v4.0: 按库增量重建 BM25（PDF 上传属于 "default" 库）
                lib = state.library or "default"
                lib_chunks = await asyncio.to_thread(vector_store.get_library_chunks, lib)
                await asyncio.to_thread(retrieval_service.build_bm25_index, lib_chunks, library=lib)

                self._mark(state, JobStatus.READY)
                logger.info("文档摄取完成: %s chunks=%s", state.filename, state.chunk_count)

                # v4.5: 文档入库后失效缓存，避免返回陈旧答案
                try:
                    from app.services.cache_service import cache_service
                    cache_service.invalidate()
                    from app.services.semantic_cache import semantic_cache
                    await semantic_cache.clear()
                    logger.info("缓存已失效 (文档入库触发)")
                except Exception as cache_exc:
                    logger.warning("缓存失效失败 (非致命): %s", cache_exc)
            except Exception as exc:
                logger.exception("文档摄取失败: job_id=%s filename=%s", job_id, state.filename)
                state.error = str(exc)
                self._mark(state, JobStatus.FAILED)

    def _mark(self, state: IngestionJobState, status: JobStatus) -> None:
        state.status = status
        state.updated_at = datetime.now()


ingestion_service = IngestionService()
