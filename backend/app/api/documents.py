import logging
import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.schemas import DocumentMeta
from app.services.document_service import document_service
from app.services.vector_store import vector_store
from app.services.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentMeta)
async def upload_document(file: UploadFile = File(...)):
    """
    上传 PDF 文档 → 解析 → 分块 → 向量化 → 存入 ChromaDB。

    返回文档元信息（页数、分块数、状态）。
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 格式")

    # ── 1. 保存上传文件 ──
    file_path = os.path.join(document_service.upload_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"文件已保存: {file_path}")

    try:
        # ── 2. 解析 + 分块 ──
        chunks = document_service.load_and_split(file_path)

        if not chunks:
            raise HTTPException(status_code=500, detail="文档解析失败，未生成有效分块")

        # ── 3. 向量化 + 存入 ChromaDB ──
        chunk_count = vector_store.add_chunks(chunks)

        # ── 4. 重建 BM25 索引 ──
        # 从 ChromaDB 获取所有分块数据用于 BM25
        all_chunks = [chunk.to_dict() for chunk in chunks]
        retrieval_service.build_bm25_index(all_chunks)

        doc_meta = DocumentMeta(
            filename=file.filename,
            page_count=chunks[0].metadata.get("total_pages", 0) if chunks else 0,
            chunk_count=chunk_count,
            status="ready",
        )

        logger.info(f"文档入库完成: {file.filename}, {doc_meta.chunk_count} 个块")
        return doc_meta

    except Exception as e:
        logger.error(f"文档处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


@router.get("/")
async def list_documents():
    """
    获取已上传的文档列表。

    用于前端页面刷新后恢复文档状态显示。
    """
    return vector_store.get_unique_documents()


@router.get("/status")
async def get_status():
    """获取向量库状态"""
    return {
        "chunk_count": vector_store.get_chunk_count(),
        "has_bm25_index": retrieval_service.bm25 is not None,
    }