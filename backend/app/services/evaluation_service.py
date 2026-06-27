"""v4.3: RAGAS 风格离线评估服务 —— LLM-as-judge 自实现。

评估指标:
- faithfulness: 答案是否忠于检索到的上下文（不幻觉）
- context_precision: 检索的上下文是否精准（相关上下文排名靠前）
- context_recall: 检索是否覆盖了回答所需的全部信息
- answer_relevancy: 答案是否切题

实现方式: 用 DeepSeek LLM 作为 judge，不依赖 ragas 库。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class EvaluationService:
    """离线评估服务: 对系统回答进行四项标准指标打分。"""

    def __init__(self):
        self.results_dir = Path(settings.EVALUATION_RESULTS_DIR)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    async def evaluate_single(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        expected: dict,
    ) -> dict[str, Any]:
        """评估单条问答，返回各指标分数 (0.0-1.0)。"""
        return {
            "query": query,
            "faithfulness": await self._eval_faithfulness(answer, contexts),
            "context_precision": await self._eval_context_precision(query, contexts),
            "context_recall": await self._eval_context_recall(expected, contexts),
            "answer_relevancy": await self._eval_answer_relevancy(query, answer),
            "keyword_coverage": self._eval_keyword_coverage(answer, expected),
        }

    async def evaluate_dataset(
        self,
        dataset: list[dict],
        library: str | None = None,
    ) -> dict[str, Any]:
        """批量评估，返回汇总报告。"""
        from app.services.rag_orchestrator import rag_orchestrator
        from app.services.retrieval_service import retrieval_service

        results: list[dict] = []
        for i, item in enumerate(dataset):
            query = item["query"]
            logger.info("评估进度: %d/%d — %s", i + 1, len(dataset), query[:50])

            try:
                # 检索（v4.5: 用 asyncio.to_thread 避免同步调用阻塞事件循环）
                docs = await asyncio.to_thread(
                    retrieval_service.search,
                    query, settings.RETRIEVAL_TOP_K, True,
                    expand_neighbors=True, library=library,
                )
                contexts = [d.get("content", "") for d in docs]

                # 生成（非流式，取最终答案）
                answer_parts: list[str] = []
                async for event in rag_orchestrator.chat_stream(
                    query=query, history=None, library=library,
                ):
                    if event.get("type") == "token":
                        answer_parts.append(event["data"])
                answer = "".join(answer_parts)

                if not answer.strip():
                    answer = "(no answer generated)"

                # 评估
                scores = await self.evaluate_single(query, answer, contexts, item)
                results.append(scores)
            except Exception as exc:
                logger.warning("评估失败: %s — %s", query[:50], exc)
                results.append({
                    "query": query,
                    "error": str(exc),
                    "faithfulness": 0.0,
                    "context_precision": 0.0,
                    "context_recall": 0.0,
                    "answer_relevancy": 0.0,
                    "keyword_coverage": 0.0,
                })

        # 汇总
        report = self._summarize(results)
        report["dataset_size"] = len(dataset)
        report["library"] = library
        report["timestamp"] = datetime.now().isoformat()
        report["details"] = results

        # 持久化
        self._save_report(report)
        return report

    # ── LLM-as-judge 评估方法 ──

    async def _eval_faithfulness(self, answer: str, contexts: list[str]) -> float:
        """faithfulness: 答案是否忠于上下文（不幻觉）。"""
        context_text = "\n---\n".join(contexts[:5])
        prompt = (
            "You are an evaluator. Rate the faithfulness of the answer to the given context.\n"
            "Faithfulness measures whether all claims in the answer are supported by the context.\n"
            "Output a single number from 0.0 to 1.0 (1.0 = fully faithful, 0.0 = complete hallucination).\n"
            "Output ONLY the number, no explanation.\n\n"
            f"Context:\n{context_text[:2000]}\n\n"
            f"Answer:\n{answer[:1000]}"
        )
        return await self._llm_score(prompt)

    async def _eval_context_precision(self, query: str, contexts: list[str]) -> float:
        """context_precision: 检索的上下文是否与查询相关。"""
        context_text = "\n---\n".join(contexts[:5])
        prompt = (
            "You are an evaluator. Rate the precision of retrieved contexts for the given query.\n"
            "Context precision measures how relevant the retrieved contexts are to the query.\n"
            "Output a single number from 0.0 to 1.0 (1.0 = all contexts highly relevant).\n"
            "Output ONLY the number, no explanation.\n\n"
            f"Query: {query}\n\n"
            f"Retrieved contexts:\n{context_text[:2000]}"
        )
        return await self._llm_score(prompt)

    async def _eval_context_recall(self, expected: dict, contexts: list[str]) -> float:
        """context_recall: 检索是否覆盖了期望关键词。"""
        keywords = expected.get("expected_keywords", [])
        if not keywords:
            return 1.0
        context_text = " ".join(contexts).lower()
        hits = sum(1 for kw in keywords if kw.lower() in context_text)
        return round(hits / len(keywords), 3)

    async def _eval_answer_relevancy(self, query: str, answer: str) -> float:
        """answer_relevancy: 答案是否切题。"""
        prompt = (
            "You are an evaluator. Rate how relevant the answer is to the query.\n"
            "Output a single number from 0.0 to 1.0 (1.0 = perfectly relevant).\n"
            "Output ONLY the number, no explanation.\n\n"
            f"Query: {query}\n\nAnswer: {answer[:1000]}"
        )
        return await self._llm_score(prompt)

    def _eval_keyword_coverage(self, answer: str, expected: dict) -> float:
        """关键词覆盖率: 期望关键词在答案中出现的比例。"""
        keywords = expected.get("expected_keywords", [])
        if not keywords:
            return 1.0
        answer_lower = answer.lower()
        hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
        return round(hits / len(keywords), 3)

    # ── 辅助方法 ──

    async def _llm_score(self, prompt: str) -> float:
        """调用 LLM 获取 0-1 分数，容错处理。"""
        try:
            result = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a strict evaluator. Output only a number.",
            )
            score = float(result.strip())
            return max(0.0, min(1.0, round(score, 3)))
        except (ValueError, TypeError):
            logger.warning("LLM 评分解析失败: %s", result[:100] if 'result' in dir() else "N/A")
            return 0.5
        except Exception as exc:
            logger.warning("LLM 评分失败: %s", exc)
            return 0.5

    def _summarize(self, results: list[dict]) -> dict:
        """汇总各项指标平均值。"""
        if not results:
            return {}
        metrics = ["faithfulness", "context_precision", "context_recall",
                    "answer_relevancy", "keyword_coverage"]
        summary = {}
        for m in metrics:
            vals = [r.get(m, 0) for r in results if not r.get("error")]
            summary[f"avg_{m}"] = round(sum(vals) / max(len(vals), 1), 3) if vals else 0.0
        summary["total_evaluated"] = len([r for r in results if not r.get("error")])
        summary["total_errors"] = len([r for r in results if r.get("error")])
        return summary

    def _save_report(self, report: dict) -> None:
        """持久化评估报告到 JSON 文件。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.results_dir / f"eval_{ts}.json"
        filepath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # 同时写一份 latest
        latest = self.results_dir / "latest.json"
        latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("评估报告已保存: %s", filepath)

    def get_latest_report(self) -> dict | None:
        """获取最近一次评估结果。"""
        latest = self.results_dir / "latest.json"
        if latest.exists():
            return json.loads(latest.read_text(encoding="utf-8"))
        return None

    async def generate_dataset_from_knowledge_base(
        self,
        library: str | None = None,
        num_queries: int = 10,
    ) -> list[dict]:
        """v4.5: 根据已有知识库内容自动生成评估数据集。

        从向量库中采样 chunks，用 LLM 为每个 chunk 生成测试问题和期望关键词。
        """
        from app.services.vector_store import vector_store

        all_chunks = vector_store.get_all_chunks()
        if library:
            all_chunks = [c for c in all_chunks if c.get("library", "") == library]

        if not all_chunks:
            raise ValueError("知识库为空，无法生成评估数据集")

        # 按文档分组，均匀采样
        import random
        random.seed(42)
        sample_size = min(num_queries, len(all_chunks))
        sampled = random.sample(all_chunks, sample_size)

        dataset = []
        for chunk in sampled:
            content = chunk.get("content", "")[:1500]
            doc_name = chunk.get("document_name", "未知文档")

            prompt = (
                "请根据以下文档片段，生成一个用于 RAG 系统评估的测试问题。\n"
                "要求：\n"
                "1. 问题应该能从该文档片段中找到答案\n"
                "2. 问题应该是具体、可验证的\n"
                "3. 同时提供 3-5 个期望关键词（答案中应包含的关键概念）\n\n"
                "请以 JSON 格式输出，格式为：\n"
                '{"query": "问题内容", "expected_keywords": ["关键词1", "关键词2"]}\n\n'
                f"文档来源: {doc_name}\n"
                f"文档片段:\n{content}"
            )

            try:
                result = await llm_service.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="你是一个测试数据生成器。只输出 JSON，不要额外解释。",
                )

                # 提取 JSON
                result = result.strip()
                if result.startswith("```"):
                    result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                item = json.loads(result)
                item["source_doc"] = doc_name
                item["source_chunk_id"] = chunk.get("chunk_id", "")
                dataset.append(item)
            except Exception as exc:
                logger.warning("生成测试问题失败 (%s): %s", doc_name, exc)
                continue

        # 持久化到数据集文件
        dataset_path = Path(settings.EVALUATION_DATASET_PATH)
        if not dataset_path.is_absolute():
            dataset_path = Path(settings.PROJECT_ROOT) / dataset_path
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("评估数据集已生成: %d 条查询 → %s", len(dataset), dataset_path)
        return dataset


evaluation_service = EvaluationService()
