"""文档处理服务 —— PDF 解析、元数据提取、分块策略"""
import os
import logging
from typing import List, Optional
from uuid import uuid4

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentChunk:
    """文档分块数据结构"""
    def __init__(
        self,
        chunk_id: str,
        content: str,
        document_name: str,
        page: int,
        chunk_index: int,
        metadata: Optional[dict] = None,
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.document_name = document_name
        self.page = page
        self.chunk_index = chunk_index
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "document_name": self.document_name,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


class DocumentService:
    """PDF 文档加载、解析与分块"""

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def load_and_split(
        self,
        file_path: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[DocumentChunk]:
        """
        加载 PDF 并执行递归字符分块。

        Args:
            file_path: PDF 文件路径
            chunk_size: 分块大小（默认从配置读取）
            chunk_overlap: 分块重叠（默认从配置读取）

        Returns:
            DocumentChunk 列表
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

        logger.info(f"加载 PDF: {file_path} (chunk_size={chunk_size}, overlap={chunk_overlap})")

        # ── 1. 加载 PDF ──
        loader = PyPDFLoader(file_path)
        raw_docs = loader.load()
        document_name = os.path.basename(file_path)
        total_pages = len(raw_docs)

        logger.info(f"PDF 加载完成: {total_pages} 页")

        # ── 2. 递归字符分块 ──
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )

        langchain_chunks = text_splitter.split_documents(raw_docs)

        # ── 3. 转换为自定义 DocumentChunk，保留元数据 ──
        chunks: List[DocumentChunk] = []
        for i, lc_chunk in enumerate(langchain_chunks):
            page = lc_chunk.metadata.get("page", 0) + 1  # 页码从 1 开始
            chunk = DocumentChunk(
                chunk_id=uuid4().hex,
                content=lc_chunk.page_content,
                document_name=document_name,
                page=page,
                chunk_index=i,
                metadata={
                    "source": lc_chunk.metadata.get("source", ""),
                    "total_pages": total_pages,
                },
            )
            chunks.append(chunk)

        logger.info(f"分块完成: {len(chunks)} 个块 (chunk_size={chunk_size}, overlap={chunk_overlap})")
        return chunks


# 全局单例
document_service = DocumentService()