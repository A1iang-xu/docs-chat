"""v4.4: L1 精确缓存服务测试"""
import time
import pytest
from unittest.mock import patch
from app.services.cache_service import CacheService


class TestCacheServiceBasic:
    """基础功能测试"""

    def test_set_and_get(self):
        """写入后应能读取"""
        cache = CacheService()
        cache.set("什么是 ref", "vue", answer="ref 是响应式引用", sources=[{"index": 1}])
        result = cache.get("什么是 ref", "vue")
        assert result is not None
        assert result["answer"] == "ref 是响应式引用"
        assert result["sources"] == [{"index": 1}]
        assert result["similarity"] == 1.0

    def test_miss_when_empty(self):
        """空缓存应返回 None"""
        cache = CacheService()
        assert cache.get("任意查询", None) is None

    def test_miss_when_different_library(self):
        """不同 library 不应命中"""
        cache = CacheService()
        cache.set("什么是 ref", "vue", answer="Vue ref", sources=[])
        assert cache.get("什么是 ref", "react") is None

    def test_case_insensitive_query(self):
        """查询大小写不敏感"""
        cache = CacheService()
        cache.set("What is ref", "vue", answer="ref", sources=[])
        assert cache.get("what is REF", "vue") is not None

    def test_strip_whitespace(self):
        """查询前后空格不影响命中"""
        cache = CacheService()
        cache.set("  什么是 ref  ", "vue", answer="ref", sources=[])
        assert cache.get("什么是 ref", "vue") is not None


class TestCacheExpiry:
    """TTL 过期测试"""

    def test_expired_entry_returns_none(self):
        """过期条目应返回 None"""
        cache = CacheService()
        cache.set("query1", None, answer="a1", sources=[])
        # 手动设置过期时间
        key = list(cache._store.keys())[0]
        cache._store[key] = (time.time() - 1, cache._store[key][1])
        assert cache.get("query1", None) is None

    def test_invalidate_all(self):
        """invalidate() 清除全部缓存"""
        cache = CacheService()
        cache.set("q1", None, answer="a1", sources=[])
        cache.set("q2", None, answer="a2", sources=[])
        count = cache.invalidate()
        assert count == 2
        assert cache.get("q1", None) is None
        assert cache.get("q2", None) is None

    def test_invalidate_by_library(self):
        """invalidate(library) 清除缓存"""
        cache = CacheService()
        cache.set("q1", "vue", answer="a1", sources=[])
        count = cache.invalidate(library="vue")
        assert count >= 1
        assert cache.get("q1", "vue") is None


class TestCacheEviction:
    """容量控制测试"""

    def test_evict_oldest_when_full(self):
        """超过最大容量时应淘汰旧条目"""
        cache = CacheService()
        cache._max_entries = 5  # 设置小容量便于测试
        for i in range(5):
            cache.set(f"query_{i}", None, answer=f"a{i}", sources=[])
        assert len(cache._store) == 5
        # 写入第 6 个，应触发淘汰
        cache.set("query_5", None, answer="a5", sources=[])
        assert len(cache._store) <= 5


class TestCacheStats:
    """统计信息测试"""

    def test_stats_returns_dict(self):
        """stats() 应返回统计字典"""
        cache = CacheService()
        cache.set("q1", None, answer="a1", sources=[])
        stats = cache.stats()
        assert "enabled" in stats
        assert "total_entries" in stats
        assert "active_entries" in stats
        assert "ttl_seconds" in stats
        assert stats["total_entries"] >= 1
