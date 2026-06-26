"""v4.5: 混合检索权重自适应测试"""
import pytest
from app.services.retrieval_service import RetrievalService


class TestHybridWeights:
    """测试查询类型 → 权重映射"""

    def test_weight_mapping_exists(self):
        """权重映射应存在"""
        assert hasattr(RetrievalService, "HYBRID_WEIGHTS")
        weights = RetrievalService.HYBRID_WEIGHTS
        assert "fact_lookup" in weights
        assert "concept_explain" in weights
        assert "synthesis" in weights
        assert "code" in weights

    def test_fact_lookup_bm25_heavier(self):
        """事实查询应 BM25 权重 >= 向量权重"""
        bm25_w, vector_w = RetrievalService.HYBRID_WEIGHTS["fact_lookup"]
        assert bm25_w >= vector_w

    def test_concept_explain_vector_heavier(self):
        """概念解释应向量权重 > BM25 权重"""
        bm25_w, vector_w = RetrievalService.HYBRID_WEIGHTS["concept_explain"]
        assert vector_w > bm25_w

    def test_code_bm25_heaviest(self):
        """代码查询应 BM25 权重最高"""
        bm25_w, vector_w = RetrievalService.HYBRID_WEIGHTS["code"]
        assert bm25_w > vector_w

    def test_synthesis_balanced(self):
        """综合查询应偏向量但不太极端"""
        bm25_w, vector_w = RetrievalService.HYBRID_WEIGHTS["synthesis"]
        assert vector_w > bm25_w
        assert bm25_w > 0.2  # 不应太低


class TestWeightedRRFFusion:
    """测试加权 RRF 融合"""

    def setup_method(self):
        self.service = RetrievalService()

    def test_weighted_fusion_returns_results(self):
        """加权融合应返回结果"""
        vector_results = [
            {"chunk_id": "a", "content": "doc A", "score": 0.9},
            {"chunk_id": "b", "content": "doc B", "score": 0.8},
        ]
        bm25_results = [
            {"chunk_id": "b", "content": "doc B", "score": 1.5},
            {"chunk_id": "c", "content": "doc C", "score": 1.0},
        ]
        merged = self.service._weighted_rrf_fusion(
            vector_results, bm25_results, top_k=5,
            vector_weight=0.7, bm25_weight=0.3,
        )
        assert len(merged) > 0
        assert len(merged) <= 5

    def test_weighted_fusion_merges_duplicates(self):
        """重复 chunk_id 应合并分数"""
        vector_results = [{"chunk_id": "x", "content": "doc X", "score": 0.9}]
        bm25_results = [{"chunk_id": "x", "content": "doc X", "score": 1.0}]
        merged = self.service._weighted_rrf_fusion(
            vector_results, bm25_results, top_k=5,
            vector_weight=0.5, bm25_weight=0.5,
        )
        assert len(merged) == 1
        # 两路都命中，分数应高于单路
        assert merged[0]["score"] > 0

    def test_weight_affects_ranking(self):
        """不同权重应影响排序结果"""
        vector_results = [
            {"chunk_id": "a", "content": "doc A", "score": 0.9},
            {"chunk_id": "b", "content": "doc B", "score": 0.8},
        ]
        bm25_results = [
            {"chunk_id": "b", "content": "doc B", "score": 1.5},
            {"chunk_id": "a", "content": "doc A", "score": 1.0},
        ]
        # 高 BM25 权重 → b 应排前面（b 在 BM25 中排名更高）
        merged_bm25 = self.service._weighted_rrf_fusion(
            vector_results, bm25_results, top_k=2,
            vector_weight=0.2, bm25_weight=0.8,
        )
        # 高向量权重 → a 应排前面（a 在向量中排名更高）
        merged_vector = self.service._weighted_rrf_fusion(
            vector_results, bm25_results, top_k=2,
            vector_weight=0.8, bm25_weight=0.2,
        )
        # 两种排序的首选应不同
        assert merged_bm25[0]["chunk_id"] != merged_vector[0]["chunk_id"]
