"""RAG Fusion 查询改写服务。

v4.5 升级:
- 新增 rewrite_with_history(): 结合对话历史做指代消解
"""
from __future__ import annotations

import json
import logging
import re
from typing import Sequence

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class QueryRewriter:
    SYSTEM_PROMPT = "你是 RAG 检索查询改写器，只输出 JSON 数组。"

    async def rewrite(self, query: str, n: int | None = None) -> list[str]:
        n = n or settings.RAG_FUSION_VARIANTS
        if n <= 0 or len(query.strip()) < 4:
            return []

        prompt = (
            f"请把用户问题改写成 {n} 个适合知识库检索的中文查询变体。"
            "要求：覆盖不同表达方式和关键词，不要回答问题，不要引入原问题没有的实体。"
            f"\n用户问题：{query}\n只输出 JSON 字符串数组。"
        )

        try:
            raw = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.SYSTEM_PROMPT,
            )
            variants = self._parse_json_array(raw)
            deduped: list[str] = []
            for item in variants:
                normalized = item.strip()
                if normalized and normalized != query and normalized not in deduped:
                    deduped.append(normalized)
            return deduped[:n]
        except Exception as exc:
            logger.warning("查询改写失败，降级为原始 query: %s", exc)
            return []

    async def rewrite_with_history(
        self,
        query: str,
        history: Sequence[dict] | None,
        n: int | None = None,
    ) -> list[str]:
        """v4.5: 结合对话历史的查询改写 + 指代消解。

        将简短/指代性查询（如"那个 ref"）结合历史上下文扩展为完整查询变体。

        Args:
            query: 用户当前查询
            history: 对话历史 [{role, content}, ...]
            n: 变体数量

        Returns:
            改写后的查询变体列表（包含指代消解后的完整查询）
        """
        n = n or settings.RAG_FUSION_VARIANTS
        if n <= 0 or len(query.strip()) < 2:
            return []

        # 构建历史上下文摘要（取最近 4 轮）
        hist_text = ""
        if history:
            recent = list(history)[-4:]
            hist_text = "\n".join(
                f"{'用户' if msg.get('role') == 'user' else '助手'}: {str(msg.get('content', ''))[:150]}"
                for msg in recent
            )

        if not hist_text:
            return await self.rewrite(query, n)

        prompt = (
            f"你是查询改写助手。根据对话历史，将用户当前问题改写成 {n} 个适合知识库检索的查询变体。\n"
            "要求：\n"
            "1. 消解指代词（如'那个'、'它'、'这个'），替换为具体实体\n"
            "2. 补充必要的上下文信息，使查询可独立理解\n"
            "3. 覆盖不同表达方式和关键词\n"
            "4. 不要回答问题\n\n"
            f"【对话历史】\n{hist_text}\n\n"
            f"【当前问题】\n{query}\n\n"
            "只输出 JSON 字符串数组。"
        )

        try:
            raw = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.SYSTEM_PROMPT,
            )
            variants = self._parse_json_array(raw)
            deduped: list[str] = []
            for item in variants:
                normalized = item.strip()
                if normalized and normalized != query and normalized not in deduped:
                    deduped.append(normalized)
            logger.info("v4.5 历史改写: %d 变体 (query=%s)", len(deduped), query[:50])
            return deduped[:n]
        except Exception as exc:
            logger.warning("v4.5 历史改写失败，降级为普通改写: %s", exc)
            return await self.rewrite(query, n)

    def _parse_json_array(self, text: str) -> list[str]:
        text = text.strip()
        match = re.search(r"\[[\s\S]*\]", text)
        payload = match.group(0) if match else text
        parsed = json.loads(payload)
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]


query_rewriter = QueryRewriter()
