"""v4.0: 管线指标聚合服务 —— 滑动窗口 P50/P95 + 缓存/幻觉计数器"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List


class MetricsService:
    """进程内指标聚合，无外部依赖。

    滑动窗口保留最近 100 条 per stage 用于 P50/P95 计算。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._latencies: Dict[str, List[float]] = defaultdict(list)
        self._window_size = 100

        # 计数器
        self.cache_hits = 0
        self.cache_misses = 0
        self.faithfulness_warnings = 0
        self.total_queries = 0
        self.total_retrieval_count = 0
        self.total_retrieve_ms: float = 0.0
        self.total_generate_ms: float = 0.0

    # ── recording ──

    def record_latency(self, stage: str, ms: float) -> None:
        with self._lock:
            self._latencies[stage].append(ms)
            if len(self._latencies[stage]) > self._window_size:
                self._latencies[stage] = self._latencies[stage][-self._window_size:]

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def record_query(self, retrieval_count: int = 0, retrieve_ms: float = 0, generate_ms: float = 0) -> None:
        with self._lock:
            self.total_queries += 1
            self.total_retrieval_count += retrieval_count
            self.total_retrieve_ms += retrieve_ms
            self.total_generate_ms += generate_ms

    def record_faithfulness_warning(self) -> None:
        with self._lock:
            self.faithfulness_warnings += 1

    # ── querying ──

    def _p50(self, stage: str) -> float | None:
        vals = sorted(self._latencies.get(stage, []))
        if not vals:
            return None
        return round(vals[len(vals) // 2], 1)

    def _p95(self, stage: str) -> float | None:
        vals = sorted(self._latencies.get(stage, []))
        if not vals:
            return None
        idx = int(len(vals) * 0.95)
        return round(vals[min(idx, len(vals) - 1)], 1)

    def get_stats(self) -> dict:
        with self._lock:
            stages = list(self._latencies.keys())
            # v4.5: 补充前端 DashboardView 期望的字段
            from app.services.vector_store import vector_store as _vs
            try:
                libraries = _vs.get_libraries()
                documents = _vs.get_unique_documents()
            except Exception:
                libraries = []
                documents = []
            return {
                "latency_p50": {s: self._p50(s) for s in stages},
                "latency_p95": {s: self._p95(s) for s in stages},
                "cache_hit_rate": round(
                    self.cache_hits / max(self.total_queries, 1), 3
                ),
                "faithfulness_warning_rate": round(
                    self.faithfulness_warnings / max(self.total_queries, 1), 3
                ),
                "total_queries": self.total_queries,
                "avg_retrieval_count": round(
                    self.total_retrieval_count / max(self.total_queries, 1), 1
                ),
                "avg_retrieve_ms": round(
                    self.total_retrieve_ms / max(self.total_queries, 1), 1
                ),
                "avg_generate_ms": round(
                    self.total_generate_ms / max(self.total_queries, 1), 1
                ),
                # v4.5: 前端期望的独立计数字段
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "faithfulness_warnings": self.faithfulness_warnings,
                "libraries": libraries,
                "documents": documents,
            }


# 全局单例
metrics_service = MetricsService()
