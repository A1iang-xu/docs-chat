"""HyDE（Hypothetical Document Embeddings）查询增强服务。

v3.2 新增:
- LLM 先生成假设性答案，用答案向量替代原始 query 向量检索
- "用答案找答案"——穿透语义鸿沟

工作原理:
1. 收到用户 query
2. LLM 生成一段假设性答案（200 token）
3. 用假设答案的向量去 ChromaDB 检索
4. 假设答案天然包含领域术语，与真实文档语义空间更对齐

参考文献: Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels", 2022
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class HyDEService:
    """HyDE 假设文档生成器。

    使用时与 Query Rewrite 并行，不增加额外延迟。
    """

    SYSTEM_PROMPT = (
        "你是一个知识库文档生成助手。"
        "请根据用户问题生成一段假设性文档片段，模拟知识库中可能存在的答案。"
        "使用专业、客观的写作风格，包含相关术语和关键定义。"
    )

    async def generate(self, query: str) -> str:
        """根据用户 query 生成假设性答案。

        Args:
            query: 用户原始问题

        Returns:
            假设性答案文本（用于向量检索），为空时降级回原始 query
        """
        if not settings.HYDE_ENABLED or not query.strip():
            return ""

        prompt = (
            f"请基于以下问题生成一段 100-200 字的知识库文档片段，"
            f"假设你正在回答该问题。使用专业术语，模拟正式文档的语气。\n\n问题：{query}"
        )

        try:
            raw = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.SYSTEM_PROMPT,
            )
            hyde_text = raw.strip()
            if hyde_text and len(hyde_text) >= 20:
                logger.info("HyDE 生成: %s chars", len(hyde_text))
                return hyde_text[:settings.HYDE_MAX_TOKENS * 4]  # ~4 chars per token

            logger.warning("HyDE 生成结果过短，回退原始 query")
            return ""

        except Exception as exc:
            logger.warning("HyDE 生成失败，回退原始 query: %s", exc)
            return ""


hyde_service = HyDEService()
