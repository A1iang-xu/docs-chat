"""查询规划器 —— 将复杂查询拆解为多个子查询。

v4.1 新增（C4 Agentic 多跳检索）:
- 检测跨库/跨版本对比查询（如 "Vue2 和 Vue3 的响应式区别"）
- LLM 拆解为多个独立子查询，分别检索后综合
- 规则优先检测对比模式，LLM 兜底拆解

触发条件:
- query_type == "synthesis"（依赖 C1 分类准确率）
- 检测到对比模式（"和...区别"/"vs"/"compare...and"/"difference between"）
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# ── 对比模式检测（双语）──
_COMPARISON_PATTERNS = re.compile(
    r"(和.{1,20}的?(区别|差异|对比|比较|不同))"
    r"|(与.{1,20}的?(区别|差异|对比|比较|不同))"
    r"|(vs\.?\s|versus\s)"
    r"|(compare\s+\w+.{0,10}\s+and\s+\w+)"
    r"|(difference\s+between\s+\w+.{0,10}\s+and\s+\w+)"
    r"|(哪个更好|哪个更适合|应该选哪个)",
    re.IGNORECASE,
)


class QueryPlanner:
    """查询规划器: 检测是否需要多跳，若需要则拆解为子查询。"""

    async def plan(
        self,
        query: str,
        library: str | None = None,
    ) -> dict[str, Any]:
        """规划查询，返回执行计划。

        Returns:
            {
                "needs_multi_hop": bool,
                "sub_queries": [{"query": str, "library": str | None}],
                "reason": str,
            }
        """
        # 不开启多跳 或 非对比查询 → 单跳
        if not settings.MULTI_HOP_ENABLED:
            return self._single_hop(query, library)

        if not self._detect_comparison(query):
            return self._single_hop(query, library)

        # 检测到对比模式 → LLM 拆解
        try:
            plan = await self._split_comparison(query, library)
            if plan["needs_multi_hop"]:
                logger.info(
                    "多跳规划: %s → %d 子查询",
                    query[:50],
                    len(plan["sub_queries"]),
                )
                return plan
        except Exception as exc:
            logger.warning("多跳拆解失败，回退单跳: %s", exc)

        return self._single_hop(query, library)

    def _detect_comparison(self, query: str) -> bool:
        """检测对比类查询（双语规则）。"""
        return bool(_COMPARISON_PATTERNS.search(query))

    def _single_hop(self, query: str, library: str | None) -> dict[str, Any]:
        """单跳计划（默认路径）。"""
        return {
            "needs_multi_hop": False,
            "sub_queries": [{"query": query, "library": library}],
            "reason": "no_comparison_detected",
        }

    async def _split_comparison(
        self,
        query: str,
        library: str | None,
    ) -> dict[str, Any]:
        """LLM 拆解对比查询为子查询。

        示例:
            "Vue2 和 Vue3 的响应式有什么区别"
            → [
                {"query": "Vue2 响应式原理", "library": "vue"},
                {"query": "Vue3 响应式原理", "library": "vue"},
              ]

            "compare ref and reactive"
            → [
                {"query": "Vue ref API 用法", "library": "vue"},
                {"query": "Vue reactive API 用法", "library": "vue"},
              ]
        """
        prompt = (
            "Split this comparison query into independent sub-queries.\n"
            "Each sub-query should target ONE side of the comparison.\n"
            "Keep each sub-query self-contained (usable as a standalone search query).\n\n"
            "Output JSON format:\n"
            '{"sub_queries": [{"query": "...", "library": "... or null}]}\n\n'
            f"Original query: {query}\n"
            f"Current library context: {library or 'none'}\n\n"
            "Rules:\n"
            "- At most 3 sub-queries\n"
            '- library: set if the sub-query targets a specific library/version, '
            'otherwise null\n'
            "- Output valid JSON only, no markdown fences, no explanation"
        )

        result = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a query planner. Output valid JSON only.",
        )

        sub_queries = self._parse_plan(result, library)

        if len(sub_queries) <= 1:
            return self._single_hop(query, library)

        # 限制最大子查询数
        sub_queries = sub_queries[: settings.MULTI_HOP_MAX_SUB_QUERIES]

        return {
            "needs_multi_hop": True,
            "sub_queries": sub_queries,
            "reason": "comparison_detected",
        }

    def _parse_plan(
        self,
        llm_output: str,
        fallback_library: str | None,
    ) -> list[dict[str, Any]]:
        """解析 LLM 输出的 JSON 计划，容错处理。"""
        text = llm_output.strip()

        # 去除可能的 markdown 代码围栏
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 片段
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.warning("LLM 计划解析失败: %s", text[:100])
                    return []
            else:
                return []

        sub_queries = data.get("sub_queries", [])
        if not isinstance(sub_queries, list):
            return []

        result: list[dict[str, Any]] = []
        for sq in sub_queries:
            if not isinstance(sq, dict):
                continue
            q = str(sq.get("query", "")).strip()
            if not q:
                continue
            lib = sq.get("library")
            if lib in ("", "null", "None", "none"):
                lib = fallback_library
            result.append({"query": q, "library": lib})

        return result


query_planner = QueryPlanner()
