"""轻量 CRAG：检索结果质量评估与纠偏。

v3.2 升级:
- 动态重写: 替换硬编码 "相关定义 条件 步骤 结论" 后缀，
  改为 LLM 根据评估失败原因动态生成针对性重写 query
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


@dataclass
class CRAGResult:
    docs: list[dict]
    should_retry: bool
    rewrite_query: str | None = None
    failure_reasons: list[str] | None = None


class CRAGService:
    SYSTEM_PROMPT = "你是 RAG 检索质量评估器，只输出 JSON。"

    async def process(self, query: str, docs: list[dict]) -> CRAGResult:
        if not settings.CRAG_ENABLED or not docs:
            return CRAGResult(docs=docs, should_retry=False)

        evaluated = await self._evaluate(query, docs[: settings.RERANKER_TOP_K])
        incorrect_count = sum(
            1 for item in evaluated
            if float(item.get("crag_score", 0.0)) <= settings.CRAG_INCORRECT_THRESHOLD
        )
        incorrect_ratio = incorrect_count / max(len(evaluated), 1)
        should_retry = incorrect_ratio >= settings.CRAG_RETRY_INCORRECT_RATIO

        if should_retry:
            # v3.2: 动态重写 —— 收集失败原因，让 LLM 生成针对性 query
            failure_reasons = [
                str(item.get("reason", ""))
                for item in evaluated
                if float(item.get("crag_score", 0.0)) <= settings.CRAG_INCORRECT_THRESHOLD
            ]
            rewrite_query = await self._generate_rewrite_query(
                original_query=query,
                failure_reasons=failure_reasons,
            )
            logger.info("CRAG 动态重写: %s → %s", query, rewrite_query)
            return CRAGResult(
                docs=evaluated,
                should_retry=True,
                rewrite_query=rewrite_query,
                failure_reasons=failure_reasons,
            )

        filtered = [
            item for item in evaluated
            if float(item.get("crag_score", 0.0)) > settings.CRAG_INCORRECT_THRESHOLD
        ]
        return CRAGResult(docs=filtered or evaluated, should_retry=False)

    async def _evaluate(self, query: str, docs: list[dict]) -> list[dict]:
        prompt_docs = [
            {
                "index": idx,
                "content": str(doc.get("content", ""))[:900],
            }
            for idx, doc in enumerate(docs)
        ]
        prompt = (
            "请判断每个候选文档是否能支撑回答用户问题，给出 0 到 1 的相关性/忠实度分数。"
            "输出格式必须是 JSON 数组：[{\"index\":0,\"score\":0.92,\"reason\":\"...\"}]。"
            "如果文档不相关，请在 reason 中说明具体缺少哪方面信息。"
            f"\n用户问题：{query}\n候选文档：{json.dumps(prompt_docs, ensure_ascii=False)}"
        )
        try:
            raw = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.SYSTEM_PROMPT,
            )
            scores = self._parse_scores(raw)
            by_index = {int(item["index"]): float(item["score"]) for item in scores}
            reasons = {int(item["index"]): str(item.get("reason", "")) for item in scores}
        except Exception as exc:
            logger.warning("CRAG LLM 评估失败，使用检索分数降级: %s", exc)
            by_index = {
                idx: max(0.0, min(1.0, float(doc.get("score", 0.0))))
                for idx, doc in enumerate(docs)
            }
            reasons = {}

        evaluated: list[dict] = []
        for idx, doc in enumerate(docs):
            score = by_index.get(idx, max(0.0, min(1.0, float(doc.get("score", 0.0)))))
            grade = "correct"
            if score <= settings.CRAG_INCORRECT_THRESHOLD:
                grade = "incorrect"
            elif score < settings.CRAG_CORRECT_THRESHOLD:
                grade = "ambiguous"
            evaluated.append({
                **doc,
                "crag_score": score,
                "crag_grade": grade,
                "reason": reasons.get(idx, ""),
            })

        return sorted(evaluated, key=lambda x: float(x.get("crag_score", 0)), reverse=True)

    async def _generate_rewrite_query(
        self,
        original_query: str,
        failure_reasons: list[str],
    ) -> str:
        """v3.2 新增: LLM 根据评估失败原因动态生成针对性重写 query。

        替换旧版硬编码: f"{query} 相关定义 条件 步骤 结论"
        """
        if not failure_reasons:
            # 保底：通用去噪
            return f"{original_query} -请用更具体的关键词重述，去除模糊限定词"

        reasons_text = "\n".join(f"- {r}" for r in failure_reasons[:5])
        prompt = (
            "用户问题进行知识库检索后，部分文档不相关。请根据不相关原因，"
            "将原始问题改写成一个更适合检索的 query。"
            "要求：保留原问题核心意图，补充缺失的关键词或角度，去掉导致歧义的表述。"
            "只输出改写后的 query 文本，不要解释。"
            f"\n原始问题：{original_query}"
            f"\n不相关原因：\n{reasons_text}"
        )

        try:
            raw = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是检索查询优化器，只输出改写后的 query。",
            )
            rewritten = raw.strip()
            if rewritten and len(rewritten) >= 3:
                return rewritten
        except Exception as exc:
            logger.warning("CRAG 动态重写 LLM 调用失败: %s", exc)

        # 最终保底
        return f"{original_query} 相关定义 条件 步骤 结论"

    def _parse_scores(self, text: str) -> list[dict]:
        match = re.search(r"\[[\s\S]*\]", text.strip())
        payload = match.group(0) if match else text
        parsed = json.loads(payload)
        if not isinstance(parsed, list):
            return []
        return [
            {"index": int(item.get("index", 0)), "score": float(item.get("score", 0)),
             "reason": str(item.get("reason", ""))}
            for item in parsed
            if isinstance(item, dict)
        ]


crag_service = CRAGService()
