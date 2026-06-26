"""v4.4: L1 精确缓存服务 —— query+library 的 SHA256 精确匹配。

两级缓存架构:
- L1 (本模块): 精确匹配，<1ms 延迟，TTL 过期
- L2 (semantic_cache): 向量相似度匹配，~50ms 延迟

L1 命中时跳过完整 RAG 流程，直接返回缓存的 answer + sources。
文档库更新时调用 invalidate() 失效相关缓存。
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """L1 精确缓存: 内存字典 + TTL 过期清理。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ttl: int = settings.CACHE_L1_TTL_SECONDS
        self._max_entries: int = 500  # 防止内存无限增长
        self._enabled: bool = settings.CACHE_L1_ENABLED

    def _make_key(self, query: str, library: str | None) -> str:
        """生成缓存 key: query + library 的 SHA256。"""
        raw = f"{query.strip().lower()}|{library or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, query: str, library: str | None = None) -> dict[str, Any] | None:
        """查 L1 缓存。命中返回 {answer, sources, similarity}，未命中返回 None。"""
        if not self._enabled:
            return None

        key = self._make_key(query, library)
        entry = self._store.get(key)
        if entry is None:
            return None

        expire_ts, value = entry
        if time.time() >= expire_ts:
            del self._store[key]
            logger.debug("L1 缓存过期: key=%s", key[:8])
            return None

        logger.info("L1 缓存命中: key=%s", key[:8])
        return value

    def set(
        self,
        query: str,
        library: str | None,
        answer: str,
        sources: list[dict],
    ) -> None:
        """写入 L1 缓存。"""
        if not self._enabled:
            return

        # 容量控制: 超过上限时清除最早的条目
        if len(self._store) >= self._max_entries:
            self._evict_oldest()

        key = self._make_key(query, library)
        self._store[key] = (
            time.time() + self._ttl,
            {
                "answer": answer,
                "sources": sources,
                "similarity": 1.0,  # 精确匹配 = 1.0
            },
        )
        logger.debug("L1 缓存写入: key=%s, ttl=%ds", key[:8], self._ttl)

    def invalidate(self, library: str | None = None) -> int:
        """失效缓存。指定 library 时只清除该库的缓存，否则清除全部。

        文档库更新（重新入库/删除）时调用。
        Returns: 被清除的条目数
        """
        if not self._store:
            return 0

        if library is None:
            count = len(self._store)
            self._store.clear()
            logger.info("L1 缓存全量失效: %d entries", count)
            return count

        # 按 library 清除需要遍历（key 是 hash，无法直接过滤）
        # 这里简单清空全部，因为按 library 精确清除需要额外存储映射
        count = len(self._store)
        self._store.clear()
        logger.info("L1 缓存失效 (library=%s): %d entries", library, count)
        return count

    def stats(self) -> dict[str, Any]:
        """返回缓存统计信息。"""
        now = time.time()
        active = sum(1 for _, (ts, _) in self._store.items() if ts > now)
        expired = len(self._store) - active
        return {
            "enabled": self._enabled,
            "total_entries": len(self._store),
            "active_entries": active,
            "expired_entries": expired,
            "ttl_seconds": self._ttl,
            "max_entries": self._max_entries,
        }

    def _evict_oldest(self) -> None:
        """清除最早过期的条目（淘汰约 25% 容量）。"""
        if not self._store:
            return
        # 按过期时间排序，清除最早的 1/4
        sorted_keys = sorted(self._store.keys(), key=lambda k: self._store[k][0])
        evict_count = max(len(sorted_keys) // 4, 1)
        for key in sorted_keys[:evict_count]:
            del self._store[key]
        logger.debug("L1 缓存淘汰: %d entries", evict_count)


cache_service = CacheService()
