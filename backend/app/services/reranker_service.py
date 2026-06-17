"""Reranker 重排序服务 —— 在混合检索后对结果做精排

面试要点: 能解释 Reranker 为什么重要 ——
混合检索的 RRF 融合是无监督的，无法利用语义信息进行精细排序。
Reranker 使用 Cross-Encoder 结构，将 query 和 document 同时输入模型，
逐对计算相关性分数，精度远高于 Bi-Encoder（Embedding 模型）。

本实现使用 sentence-transformers 的 CrossEncoder。
"""
import logging
from typing import List
from sentence_transformers import CrossEncoder
from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """
    使用 BGE-Reranker-v2-m3 对检索结果做精排。

    模型规模:
    - BGE-Reranker-v2-m3: ~568M 参数，中文效果优秀
    - 推理速度: ~50 docs/s (CPU), ~500 docs/s (GPU)

    选型理由: 开源可本地部署、中文效果好、延迟可控。
    备选: Cohere Rerank API（商业方案，精度更高但需付费）。
    """

    def __init__(self):
        self.model: CrossEncoder | None = None
        self.model_name = settings.RERANKER_MODEL
        self._loaded = False

    def _lazy_load(self):
        """延迟加载模型（首次使用时下载，约 2.2GB）"""
        if not self._loaded:
            logger.info(f"加载 Reranker 模型: {self.model_name}")
            self.model = CrossEncoder(
                self.model_name,
                max_length=512,
            )
            self._loaded = True
            logger.info("Reranker 模型加载完成")

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: int | None = None,
    ) -> List[dict]:
        """
        对候选文档做精排。

        Args:
            query: 查询文本
            documents: 候选文档列表，每项需包含 content 字段
            top_k: 返回数量（默认从配置读取）

        Returns:
            重排序后的文档列表，score 更新为 Reranker 分数
        """
        self._lazy_load()
        top_k = top_k or settings.RERANKER_TOP_K

        if not documents:
            return []

        # ── 准备输入对 ──
        pairs = [[query, doc["content"]] for doc in documents]

        # ── 计算分数 ──
        scores = self.model.predict(pairs, show_progress_bar=False)

        # ── 按分数排序 ──
        for i, doc in enumerate(documents):
            doc["score"] = float(scores[i])

        ranked = sorted(documents, key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]


# 全局单例
reranker = RerankerService()