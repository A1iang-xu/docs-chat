"""Reranker 重排序服务 —— 在混合检索后对结果做精排

架构要求: Qwen3-Reranker-0.6B (RERANKER_TYPE=qwen) 远程模式,
          BGE-Reranker-v2-m3 (RERANKER_TYPE=fallback) 本地 CrossEncoder 降级。
本地模型缓存: HuggingFace 默认 ~/.cache/huggingface/hub/ (可通过 HF_HOME 修改)。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from sentence_transformers import CrossEncoder

from app.core.config import settings

logger = logging.getLogger(__name__)


class RemoteReranker:
    def __init__(self, api_url="", model="", timeout=30, max_retries=2):
        self.api_url = (api_url or settings.RERANKER_API_URL).rstrip("/")
        self.model = model or settings.RERANKER_MODEL
        self.timeout = timeout or settings.RERANKER_API_TIMEOUT
        self.max_retries = max_retries
        self._available: bool | None = None

    async def check_availability(self) -> bool:
        if self._available is not None:
            return self._available
        if not self.api_url:
            self._available = False
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.api_url + "/health")
                self._available = resp.status_code < 500
        except Exception:
            self._available = False
        return self._available

    async def rerank(self, query, documents, top_k=5):
        if not documents:
            return []
        try:
            return await self._rerank_via_endpoint(query, documents, top_k)
        except Exception as exc:
            logger.warning("remote /rerank failed, try scoring: %s", exc)
            try:
                return await self._rerank_via_scoring(query, documents, top_k)
            except Exception as exc2:
                raise RuntimeError(f"remote reranker unavailable: {exc2}") from exc2

    async def _rerank_via_endpoint(self, query, documents, top_k):
        import httpx
        doc_texts = [str(d.get("content", ""))[:settings.RERANKER_MAX_LENGTH] for d in documents]
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.api_url + "/rerank",
                        json={"model": self.model, "query": query, "documents": doc_texts, "top_n": top_k},
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    results = data.get("results", [])
                    ranked = []
                    for r in sorted(results, key=lambda r: r.get("relevance_score", 0), reverse=True):
                        idx = int(r.get("index", 0))
                        if idx < len(documents):
                            ranked.append({**documents[idx], "score": float(r.get("relevance_score", 0))})
                    return ranked[:top_k]
            except Exception as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise exc
        return documents[:top_k]

    async def _rerank_via_scoring(self, query, documents, top_k):
        import httpx
        import numpy as np
        doc_texts = [str(d.get("content", ""))[:settings.RERANKER_MAX_LENGTH] for d in documents]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.api_url + "/embeddings",
                json={"model": self.model, "input": [query] + doc_texts},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            embeds = [item["embedding"] for item in sorted(data.get("data", []), key=lambda x: int(x.get("index", 0)))]
        if len(embeds) < 2:
            return documents[:top_k]
        qv = np.array(embeds[0])
        for i, de in enumerate(embeds[1:]):
            dv = np.array(de)
            documents[i]["score"] = float(np.dot(qv, dv) / (np.linalg.norm(qv) * np.linalg.norm(dv) + 1e-8))
        return sorted(documents, key=lambda x: float(x.get("score", 0)), reverse=True)[:top_k]


class RerankerService:
    def __init__(self):
        self.model: CrossEncoder | None = None
        self.model_name = settings.RERANKER_MODEL
        self._loaded = False
        self._remote: RemoteReranker | None = None
        self._use_remote: bool | None = None

    async def _probe_mode(self) -> bool:
        if self._use_remote is not None:
            return self._use_remote
        if settings.RERANKER_TYPE == "qwen" and settings.RERANKER_API_URL:
            self._remote = RemoteReranker()
            self._use_remote = await self._remote.check_availability()
            if self._use_remote:
                logger.info("reranker mode: remote Qwen @ %s", settings.RERANKER_API_URL)
                return True
        self._use_remote = False
        logger.info("reranker mode: local %s", self.model_name)
        return False

    def _lazy_load(self):
        if not self._loaded:
            logger.info("loading local reranker: %s (cache: %s)", self.model_name, _hf_dir())
            try:
                self.model = CrossEncoder(self.model_name, max_length=settings.RERANKER_MAX_LENGTH)
                self._loaded = True
                logger.info("local reranker loaded")
            except Exception as exc:
                logger.error("local reranker load failed: %s", exc)
                raise

    def rerank(self, query, documents, top_k=None):
        return asyncio.run(self._rerank_async(query, documents, top_k))

    async def _rerank_async(self, query, documents, top_k=None):
        top_k = top_k or settings.RERANKER_TOP_K
        if not documents:
            return []

        use_remote = await self._probe_mode()
        if use_remote and self._remote:
            try:
                return await self._remote.rerank(query, documents, top_k)
            except Exception as exc:
                logger.warning("remote reranker failed, fallback to local: %s", exc)

        local_ok = False
        try:
            self._lazy_load()
            local_ok = True
        except Exception as exc:
            logger.error("local reranker unavailable: %s", exc)

        if local_ok:
            pairs = [[query, d["content"]] for d in documents]
            scores = self.model.predict(pairs, show_progress_bar=False)
            for i, d in enumerate(documents):
                d["score"] = float(scores[i])
            return sorted(documents, key=lambda x: x["score"], reverse=True)[:top_k]

        return sorted(documents, key=lambda x: float(x.get("score", 0)), reverse=True)[:top_k]

    async def check_health(self):
        use_remote = await self._probe_mode()
        return {
            "mode": "remote" if use_remote else "local",
            "model": self.model_name,
            "remote_url": settings.RERANKER_API_URL if use_remote else None,
            "reranker_type": settings.RERANKER_TYPE,
            "local_loaded": self._loaded,
        }


reranker = RerankerService()

def _hf_dir():
    return os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface/hub"))
