"""向量存储服务 —— Embedding 向量化、ChromaDB 持久化、语义检索

v3.2 升级:
- 新增 M3eEmbeddingFunction: 本地加载 moka-ai/m3e-base (768d 中文 Embedding)
- EMBEDDING_PROVIDER=m3e_local 配置分支
- 维度安全: 切换模型自动清空旧 collection 防止 C++ 崩溃

v4.0 升级:
- add_chunks 改用 upsert（确定性 ID 去重）
- metadata 增加 library/version/source_url/heading_path/code_language/is_code_block
- search 增加 where 参数，支持按库过滤
- 新增 get_libraries / get_library_chunks

Embedding 选型矩阵:
- chromadb_default: ChromaDB 内置 all-MiniLM-L6-v2 (384d, 英文偏重)
- m3e_local (v3.2): 本地 sentence_transformers 加载 m3e-base (768d, 中文专用)
- sentence_transformers: 本地加载任意 SentenceTransformer 模型
- remote: OpenAI-compatible API (vLLM/TGI)
"""
import asyncio
import logging
import time
from typing import List, Optional

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from app.core.config import settings
from app.services.document_service import DocumentChunk

logger = logging.getLogger(__name__)


class M3eEmbeddingFunction(EmbeddingFunction):
    """v3.2 新增: 本地 m3e-base 中文 Embedding 模型（768 维）。

    moka-ai/m3e-base:
    - 参数量: 110M
    - 维度: 768
    - 最大序列长度: 512 tokens
    - 训练数据: 2200万+ 中文句子对
    - MTEB 中文榜: 前 3 名
    """

    def __init__(self, model_name: str = "moka-ai/m3e-base", batch_size: int = 32):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("加载 m3e-base 中文 Embedding 模型: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("m3e-base 加载完成, dim=%s", self._model.get_sentence_embedding_dimension())
        return self._model

    def __call__(self, input: Documents) -> list[list[float]]:
        texts = list(input)
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # 归一化便于余弦相似度
        )
        return [emb.tolist() for emb in embeddings]


class RemoteEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_base="", api_key="", model="BAAI/bge-m3", max_retries=3, batch_size=32):
        self.api_base = (api_base or settings.EMBEDDING_API_BASE).rstrip("/")
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.max_retries = max_retries or settings.EMBEDDING_MAX_RETRIES
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

    def __call__(self, input: Documents) -> list[list[float]]:
        return asyncio.run(self._embed_batch(list(input)))

    async def _embed_batch(self, texts):
        import httpx
        all_embeddings = []
        total = len(texts)
        for i in range(0, total, self.batch_size):
            batch = texts[i:i + self.batch_size]
            payload = {"input": batch, "model": self.model}
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            last_error = None
            for attempt in range(self.max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(f"{self.api_base}/embeddings", json=payload, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        for item in sorted(data.get("data", []), key=lambda x: int(x.get("index", 0))):
                            all_embeddings.append(list(item["embedding"]))
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise RuntimeError(f"Embedding API failed: {last_error}") from last_error
        logger.info("remote embedding: %s texts -> %s vectors", total, len(all_embeddings))
        return all_embeddings


class VectorStoreService:
    COLLECTION_NAME = "docs_chat"
    CODE_COLLECTION_NAME = "docs_chat_code"  # v4.1: 代码块子索引
    _DIM_METADATA_KEY = "embedding_dim"

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.embedding_function: EmbeddingFunction = self._build_embedding_function()
        self._collection = None
        self._code_collection = None  # v4.1

    def _build_embedding_function(self) -> EmbeddingFunction:
        provider = settings.EMBEDDING_PROVIDER.lower()

        # v3.2: m3e_local 中文 Embedding
        if provider == "m3e_local":
            try:
                model = settings.EMBEDDING_MODEL or "moka-ai/m3e-base"
                logger.info("m3e-local embedding: %s (dim=%s)", model, settings.EMBEDDING_DIM)
                return M3eEmbeddingFunction(model_name=model, batch_size=settings.EMBEDDING_BATCH_SIZE)
            except Exception as exc:
                logger.warning("m3e_local 加载失败，回退默认: %s", exc)

        # BGE-M3 远程模式
        if settings.ENABLE_BGE_M3 and settings.EMBEDDING_API_BASE:
            logger.info("BGE-M3 mode: remote embedding @ %s", settings.EMBEDDING_API_BASE)
            return RemoteEmbeddingFunction()

        # 远程 Embedding API
        if provider == "remote" and settings.EMBEDDING_API_BASE:
            logger.info("remote embedding: %s model=%s", settings.EMBEDDING_API_BASE, settings.EMBEDDING_MODEL)
            return RemoteEmbeddingFunction()

        # 本地 SentenceTransformer
        if provider == "sentence_transformers":
            try:
                logger.info("local embedding: %s", settings.EMBEDDING_MODEL)
                return embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=settings.EMBEDDING_MODEL
                )
            except Exception as exc:
                logger.warning("sentence_transformers failed, fallback default: %s", exc)

        # 默认 ChromaDB 内置
        logger.info("ChromaDB default embedding: %s", settings.EMBEDDING_MODEL)
        return embedding_functions.DefaultEmbeddingFunction()

    def rebuild_embedding_function(self):
        """重建 embedding function（切换模型时调用）。"""
        self.embedding_function = self._build_embedding_function()
        self._collection = None
        logger.info("embedding function 已重建; 下次访问触发维度检查")

    @property
    def collection(self):
        if self._collection is None:
            existing = self._get_existing_collection()
            if existing is not None:
                stored_dim = int(existing.metadata.get(self._DIM_METADATA_KEY, 0))
                current_dim = int(settings.EMBEDDING_DIM)
                if stored_dim > 0 and stored_dim != current_dim:
                    logger.warning(
                        "DIMENSION MISMATCH: stored=%s current=%s. "
                        "Auto-clearing old ChromaDB collection to prevent C++ crash. "
                        "Re-upload documents to rebuild.",
                        stored_dim, current_dim,
                    )
                    self.client.delete_collection(self.COLLECTION_NAME)
                    existing = None
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": settings.EMBEDDING_MODEL,
                    self._DIM_METADATA_KEY: int(settings.EMBEDDING_DIM),
                },
                embedding_function=self.embedding_function,
            )
        return self._collection

    @property
    def code_collection(self):
        """v4.1: 代码块子索引 collection。"""
        if self._code_collection is None:
            self._code_collection = self.client.get_or_create_collection(
                name=self.CODE_COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": settings.EMBEDDING_MODEL,
                    self._DIM_METADATA_KEY: int(settings.EMBEDDING_DIM),
                },
                embedding_function=self.embedding_function,
            )
        return self._code_collection

    def _get_existing_collection(self):
        try:
            return self.client.get_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self.embedding_function,
            )
        except Exception:
            return None

    def add_chunks(self, chunks):
        """v4.0: upsert 模式（确定性 ID 去重） + 扩展元数据
        v4.1: 代码块路由到 code_collection，文本块走原 collection"""
        if not chunks:
            return 0

        # v4.1: 分离代码块和文本块
        code_chunks = [c for c in chunks if getattr(c, "is_code_block", False)]
        text_chunks = [c for c in chunks if not getattr(c, "is_code_block", False)]

        total = 0
        if text_chunks:
            total += self._upsert_collection(self.collection, text_chunks)
        if code_chunks:
            total += self._upsert_collection(self.code_collection, code_chunks)
        return total

    def _upsert_collection(self, collection, chunks) -> int:
        """向指定 collection upsert chunks。"""
        if not chunks:
            return 0
        ids = [c.chunk_id for c in chunks]
        texts = [c.content for c in chunks]
        metadatas = [{
            "document_name": c.document_name,
            "page": c.page,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "parser": str(c.metadata.get("parser", "")),
            "h1": str(c.metadata.get("h1", "")),
            "h2": str(c.metadata.get("h2", "")),
            "h3": str(c.metadata.get("h3", "")),
            "breadcrumb": str(c.metadata.get("breadcrumb", "")),
            # v4.0
            "library": getattr(c, "library", "") or "",
            "version": getattr(c, "version", "") or "",
            "source_url": getattr(c, "source_url", "") or "",
            "heading_path": getattr(c, "heading_path", "") or "",
            "code_language": getattr(c, "code_language", "") or "",
            "is_code_block": getattr(c, "is_code_block", False),
        } for c in chunks]
        logger.info("upserting %s chunks to '%s'", len(texts), collection.name)
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
        return len(ids)

    def search(self, query, top_k=None, where=None):
        """v4.0: 支持 where 过滤（按库/版本等元数据筛选）"""
        top_k = top_k or settings.RETRIEVAL_TOP_K
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["metadatas", "distances"],
        )
        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                similarity = 1.0 - distance if distance is not None else 0.0
                items.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "score": round(similarity, 4),
                    "breadcrumb": meta.get("breadcrumb", ""),
                    # v4.0
                    "library": meta.get("library", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": meta.get("heading_path", ""),
                    "version": meta.get("version", ""),
                })
        return items

    def search_code(self, query, top_k=None, where=None):
        """v4.1: 在代码子索引中检索。"""
        top_k = top_k or 5
        try:
            results = self.code_collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where,
                include=["metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("代码子索引检索失败: %s", exc)
            return []

        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                similarity = 1.0 - distance if distance is not None else 0.0
                items.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "score": round(similarity, 4),
                    "breadcrumb": meta.get("breadcrumb", ""),
                    "library": meta.get("library", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": meta.get("heading_path", ""),
                    "version": meta.get("version", ""),
                    "code_language": meta.get("code_language", ""),
                    "is_code_block": True,
                })
        return items

    def get_all_chunks(self):
        if self.collection.count() == 0:
            return []
        results = self.collection.get(include=["metadatas"])
        chunks = []
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "breadcrumb": meta.get("breadcrumb", ""),
                    # v4.0
                    "library": meta.get("library", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": meta.get("heading_path", ""),
                    "version": meta.get("version", ""),
                })
        return chunks

    def get_chunk_count(self):
        return self.collection.count()

    def get_unique_documents(self):
        if self.collection.count() == 0:
            return []
        results = self.collection.get(include=["metadatas"])
        doc_map: dict = {}
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                fn = meta.get("document_name", "")
                if not fn:
                    continue
                if fn not in doc_map:
                    doc_map[fn] = {"filename": fn, "chunk_count": 0, "page_count": meta.get("page", 0)}
                doc_map[fn]["chunk_count"] += 1
                doc_map[fn]["page_count"] = max(doc_map[fn]["page_count"], meta.get("page", 0))
        return list(doc_map.values())

    # ── v4.0: 多库命名空间 ──

    def get_libraries(self):
        """v4.1: 返回所有已入库的文档库列表（合并 text + code collection）。"""
        lib_map: dict[str, dict] = {}
        for coll in [self.collection, self.code_collection]:
            try:
                if coll.count() == 0:
                    continue
            except Exception:
                continue
            results = coll.get(include=["metadatas"])
            if results["ids"]:
                for i in range(len(results["ids"])):
                    meta = results["metadatas"][i] if results["metadatas"] else {}
                    lib = meta.get("library", "") or "default"
                    ver = meta.get("version", "") or "latest"
                    key = f"{lib}@{ver}"
                    if key not in lib_map:
                        lib_map[key] = {
                            "library": lib,
                            "version": ver,
                            "chunk_count": 0,
                            "source_url": meta.get("source_url", ""),
                        }
                    lib_map[key]["chunk_count"] += 1
        return list(lib_map.values())

    def get_library_chunks(self, library: str) -> list[dict]:
        """v4.0: 按库名获取所有 chunks（用于 BM25 按库重建）。"""
        if self.collection.count() == 0:
            return []
        try:
            results = self.collection.get(
                where={"library": library},
                include=["metadatas"],
            )
        except Exception:
            # 如果 collection 中没有 library 字段（旧数据），回退全量加手动过滤
            results = self.collection.get(include=["metadatas"])
        chunks = []
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                if library and meta.get("library", "") != library:
                    continue
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "breadcrumb": meta.get("breadcrumb", ""),
                    "library": meta.get("library", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": meta.get("heading_path", ""),
                    "version": meta.get("version", ""),
                })
        return chunks

    def clear(self):
        self.client.delete_collection(self.COLLECTION_NAME)
        try:
            self.client.delete_collection(self.CODE_COLLECTION_NAME)
        except Exception:
            pass
        self._collection = None
        self._code_collection = None
        logger.info("ChromaDB cleared (text + code collections)")


vector_store = VectorStoreService()
