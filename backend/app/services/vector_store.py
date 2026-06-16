"""向量存储服务 —— Embedding 向量化、ChromaDB 持久化、语义检索"""
import logging
from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from app.core.config import settings
from app.services.document_service import DocumentChunk

logger = logging.getLogger(__name__)


class VectorStoreService:
    """管理 ChromaDB 向量存储 —— 写入、检索、删除"""

    COLLECTION_NAME = "docs_chat"

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # 使用 ChromaDB 内置的 ONNX Embedding 函数（轻量、无需 torch）
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self._collection = None

    @property
    def collection(self):
        """懒加载 collection，挂载 embedding_function"""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
                embedding_function=self.embedding_function,
            )
        return self._collection

    def add_chunks(self, chunks: List[DocumentChunk]) -> int:
        """
        将文档分块向量化并存入 ChromaDB。
        Embedding 由 ChromaDB 内置的 embedding_function 自动处理。

        Args:
            chunks: 文档分块列表

        Returns:
            成功写入的向量数量
        """
        if not chunks:
            return 0

        # ── 准备 ChromaDB 写入数据 ──
        ids = [chunk.chunk_id for chunk in chunks]
        texts = [chunk.content for chunk in chunks]
        metadatas = [
            {
                "document_name": chunk.document_name,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,  # 原文存入 metadata 以便检索时直接返回
            }
            for chunk in chunks
        ]

        logger.info(f"开始向量化 {len(texts)} 个文本块 (模型: {settings.EMBEDDING_MODEL})")

        # ── 批量写入（ChromaDB 自动调用 embedding_function 生成向量）──
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info(f"ChromaDB 写入完成: {len(ids)} 条")
        return len(ids)

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[dict]:
        """
        向量语义检索。

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            检索结果列表，每项包含 content, document_name, page, score
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K

        # ChromaDB 自动将 query_texts 向量化并检索
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["metadatas", "distances"],
        )

        # 格式化返回
        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                # cosine distance → similarity score (余弦距离转相似度)
                similarity = 1.0 - distance if distance is not None else 0.0

                items.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "score": round(similarity, 4),
                })

        return items

    def get_chunk_count(self) -> int:
        """获取已存储的向量总数"""
        return self.collection.count()

    def clear(self):
        """清空向量库"""
        self.client.delete_collection(self.COLLECTION_NAME)
        self._collection = None
        logger.info("ChromaDB 已清空")


# 全局单例
vector_store = VectorStoreService()