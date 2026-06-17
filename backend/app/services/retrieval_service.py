"""混合检索服务 —— BM25 关键词检索 + 向量语义检索 + RRF 融合 + Reranker 精排"""
import logging
from typing import List
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    混合检索流程:
    1. 向量语义检索 → 获取 top_k 个结果
    2. BM25 关键词检索 → 获取 top_k 个结果
    3. RRF (Reciprocal Rank Fusion) 融合排序
    4. （可选）Reranker 精排

    面试要点: 能解释为什么需要混合检索——向量检索擅长语义匹配但可能漏掉精确关键词，
    BM25 擅长精确匹配但缺乏语义理解，两者互补。
    """

    RRF_K = 60  # RRF 平滑参数

    def __init__(self):
        # BM25 索引数据（在 build_bm25_index 中初始化）
        self.bm25: BM25Okapi | None = None
        self.bm25_chunks: List[dict] = []

    def build_bm25_index(self, chunks: List[dict]):
        """
        构建 BM25 索引。

        Args:
            chunks: 文档块列表，每项需包含 content 字段
        """
        if not chunks:
            logger.warning("BM25 索引构建失败: 无可用数据")
            return

        # 简单分词（按空格和标点切割）
        tokenized = [_tokenize(chunk["content"]) for chunk in chunks]
        self.bm25 = BM25Okapi(tokenized)
        self.bm25_chunks = chunks
        logger.info(f"BM25 索引构建完成: {len(chunks)} 个文档")

    def search(self, query: str, top_k: int | None = None, use_reranker: bool = True) -> List[dict]:
        """
        混合检索 —— 向量 + BM25 → RRF 融合 → (可选) Reranker 精排。

        Args:
            query: 查询文本
            top_k: 最终返回数量
            use_reranker: 是否使用 Reranker 精排（默认开启）

        Returns:
            排序后的检索结果
        """
        top_k = top_k or settings.RERANKER_TOP_K

        # ── 1. 向量语义检索 ──
        vector_results = vector_store.search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"向量检索: {len(vector_results)} 条结果")

        # ── 2. BM25 关键词检索 ──
        bm25_results = self._bm25_search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"BM25 检索: {len(bm25_results)} 条结果")

        # ── 3. RRF 融合 ──
        merged = self._rrf_fusion(vector_results, bm25_results, top_k=top_k * 2)
        logger.info(f"RRF 融合: {len(merged)} 条结果")

        # ── 4. Reranker 精排（可选） ──
        if use_reranker and merged:
            try:
                from app.services.reranker_service import reranker
                merged = reranker.rerank(query, merged, top_k=top_k)
                logger.info(f"Reranker 精排: {len(merged)} 条结果")
            except ImportError:
                logger.warning("Reranker 模型未安装，跳过精排")
                merged = merged[:top_k]
        else:
            merged = merged[:top_k]

        return merged

    def _bm25_search(self, query: str, top_k: int) -> List[dict]:
        """BM25 关键词检索"""
        if self.bm25 is None or not self.bm25_chunks:
            return []

        tokenized_query = _tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        # 获取 top_k
        indexed = [(i, scores[i]) for i in range(len(scores))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed[:top_k]

        results = []
        for idx, score in top_indices:
            if score > 0:
                chunk = self.bm25_chunks[idx]
                results.append({
                    "chunk_id": chunk.get("chunk_id", f"bm25_{idx}"),
                    "content": chunk.get("content", ""),
                    "document_name": chunk.get("document_name", ""),
                    "page": chunk.get("page", 0),
                    "score": float(score),
                })
        return results

    def _rrf_fusion(
        self,
        vector_results: List[dict],
        bm25_results: List[dict],
        top_k: int,
    ) -> List[dict]:
        """
        RRF 融合排序。

        公式: RRF(d) = Σ 1/(k + rank_i(d))
        其中 k=60, rank_i(d) 是文档在第 i 个排序列表中的排名

        面试要点: 能解释 RRF 为什么比简单的线性加权更好——
        不需要做分数归一化，不受各自分数量纲影响，简单且效果稳定。
        """
        # 用于去重和累加分数
        chunk_map: dict[str, dict] = {}

        # 向量检索结果
        for rank, item in enumerate(vector_results):
            chunk_id = item["chunk_id"]
            rrf_score = 1.0 / (self.RRF_K + rank + 1)
            if chunk_id in chunk_map:
                chunk_map[chunk_id]["score"] += rrf_score
            else:
                chunk_map[chunk_id] = {**item, "score": rrf_score}

        # BM25 检索结果
        for rank, item in enumerate(bm25_results):
            chunk_id = item["chunk_id"]
            rrf_score = 1.0 / (self.RRF_K + rank + 1)
            if chunk_id in chunk_map:
                chunk_map[chunk_id]["score"] += rrf_score
            else:
                chunk_map[chunk_id] = {**item, "score": rrf_score}

        # 按 RRF 分数降序排列
        merged = sorted(chunk_map.values(), key=lambda x: x["score"], reverse=True)
        return merged[:top_k]


def _tokenize(text: str) -> List[str]:
    """简单中文/英文分词"""
    import re
    # 提取中文字符和英文单词
    tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+', text.lower())
    return tokens if tokens else text.lower().split()


# 全局单例
retrieval_service = RetrievalService()