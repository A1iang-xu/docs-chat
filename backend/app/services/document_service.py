"""文档处理服务 —— PDF 解析、元数据提取、分块策略"""
import hashlib
import os
import logging
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from app.core.config import settings

logger = logging.getLogger(__name__)


def _deterministic_chunk_id(library: str, source: str, chunk_index: int, content: str) -> str:
    """v4.0: 确定性 chunk_id（sha256），PDF 路径去重。

    PDF 无 source_url/heading_path，用 file_path + chunk_index + content 前缀生成稳定 ID，
    使同一 PDF 重新入库时 upsert 覆盖而非新增重复块。
    """
    raw = f"{library}|{source}|{chunk_index}|{content[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


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
        # v4.0 新增: 文档站场景元数据
        source_url: str = "",
        library: str = "",
        version: str = "",
        heading_path: str = "",
        code_language: str = "",
        is_code_block: bool = False,
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.document_name = document_name
        self.page = page
        self.chunk_index = chunk_index
        self.metadata = metadata or {}
        self.source_url = source_url
        self.library = library
        self.version = version
        self.heading_path = heading_path
        self.code_language = code_language
        self.is_code_block = is_code_block

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "document_name": self.document_name,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
            "source_url": self.source_url,
            "library": self.library,
            "version": self.version,
            "heading_path": self.heading_path,
            "code_language": self.code_language,
            "is_code_block": self.is_code_block,
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
        """加载 PDF 并执行递归字符分块。"""
        chunk_size = chunk_size or settings.CHUNK_SIZE
        chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

        logger.info(f"加载 PDF: {file_path} (chunk_size={chunk_size}, overlap={chunk_overlap})")

        loader = PyPDFLoader(file_path)
        raw_docs = loader.load()
        document_name = os.path.basename(file_path)
        total_pages = len(raw_docs)

        logger.info(f"PDF 加载完成: {total_pages} 页")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )

        langchain_chunks = text_splitter.split_documents(raw_docs)

        chunks: List[DocumentChunk] = []
        for i, lc_chunk in enumerate(langchain_chunks):
            page = lc_chunk.metadata.get("page", 0) + 1
            chunk = DocumentChunk(
                chunk_id=_deterministic_chunk_id(
                    library=document_name,
                    source=lc_chunk.metadata.get("source", file_path),
                    chunk_index=i,
                    content=lc_chunk.page_content,
                ),
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
