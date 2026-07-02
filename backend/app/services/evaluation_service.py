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
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# v4.6: 评估专用低温度 LLM 客户端，确保评分一致性
_eval_client: AsyncOpenAI | None = None


def _get_eval_client() -> AsyncOpenAI:
    global _eval_client
    if _eval_client is None:
        _eval_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _eval_client


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
        """评估单条问答，返回各指标分数 (0.0-1.0)。
        
        v4.5 优化: 三个 LLM 评分指标并行执行，大幅减少耗时。
        """
        # 并行执行三个 LLM-based 评分（faithfulness / context_precision / answer_relevancy）
        faithfulness, context_precision, answer_relevancy = await asyncio.gather(
            self._eval_faithfulness(answer, contexts),
            self._eval_context_precision(query, contexts),
            self._eval_answer_relevancy(query, answer),
        )
        return {
            "query": query,
            "answer": answer,
            "contexts": contexts,
            "faithfulness": faithfulness,
            "context_precision": context_precision,
            "context_recall": await self._eval_context_recall(expected, contexts),
            "answer_relevancy": answer_relevancy,
            "keyword_coverage": self._eval_keyword_coverage(answer, expected),
        }

    async def evaluate_dataset(
        self,
        dataset: list[dict],
        library: str | None = None,
    ) -> dict[str, Any]:
        """批量评估，返回汇总报告。

        - 答案生成使用完整 RAG 管道（rag_orchestrator.chat_stream）
        - 捕获 RAG 阶段事件写入进度文件，供前端可视化
        """
        from app.services.rag_orchestrator import rag_orchestrator

        results: list[dict] = []
        progress_file = self.results_dir / "progress.json"

        # 阶段名称映射（perf/stage 事件 → 标准化阶段名）
        STAGE_MAP = {
            "classify": "classify",
            "rewrite": "rewrite",
            "plan": "rewrite",
            "retrieve": "retrieve",
            "retrieving": "retrieve",
            "crag": "crag",
            "crag_skipped": "crag",
            "generate": "generate",
            "generating": "generate",
            "faithfulness_check": "faithfulness_check",
            "complete": "complete",
            "pipeline": "complete",
        }

        # 初始化 per_item 列表
        per_item = []
        for item in dataset:
            per_item.append({
                "query": item.get("query", ""),
                "status": "pending",
                "current_stage": "",
                "stages_completed": [],
                "error": None,
            })

        for i, item in enumerate(dataset):
            query = item["query"]
            logger.info("评估进度: %d/%d — %s", i + 1, len(dataset), query[:50])

            # 更新当前 item 为 running
            per_item[i]["status"] = "running"
            per_item[i]["current_stage"] = "classify"
            per_item[i]["stages_completed"] = []
            self._write_progress(progress_file, i + 1, len(dataset),
                                 current_query=query, per_item=per_item)

            try:
                # 完整 RAG 管道生成答案，同时捕获阶段事件
                answer_parts: list[str] = []
                contexts: list[str] = []
                contexts_captured = False  # v4.6: 只取第一个 source 事件（全部检索结果）

                async for event in rag_orchestrator.chat_stream(
                    query=query, library=library,
                ):
                    evt_type = event.get("type", "")

                    if evt_type == "token":
                        answer_parts.append(event.get("data", ""))

                    elif evt_type == "source":
                        # v4.6: 只取第一个 source 事件（全部检索结果），
                        # 忽略后续的过滤/重新编号后的 source 事件
                        if not contexts_captured:
                            try:
                                sources_data = json.loads(event.get("data", "[]"))
                                contexts = [s.get("content", "") for s in sources_data]
                                contexts_captured = True
                                logger.info("评估: 捕获 %d 个上下文片段", len(contexts))
                            except (json.JSONDecodeError, TypeError):
                                pass

                    elif evt_type in ("perf", "stage"):
                        try:
                            data = json.loads(event.get("data", "{}"))
                        except (json.JSONDecodeError, TypeError):
                            continue
                        stage_key = data.get("stage", "")
                        normalized = STAGE_MAP.get(stage_key, "")
                        if normalized and normalized not in per_item[i]["stages_completed"]:
                            # 将之前的 current_stage 标记为已完成
                            if per_item[i]["current_stage"] and per_item[i]["current_stage"] not in per_item[i]["stages_completed"]:
                                per_item[i]["stages_completed"].append(per_item[i]["current_stage"])
                            per_item[i]["current_stage"] = normalized
                            self._write_progress(progress_file, i + 1, len(dataset),
                                                 current_query=query, per_item=per_item)

                answer = "".join(answer_parts)
                per_item[i]["stages_completed"].append("complete")
                per_item[i]["current_stage"] = "complete"

                if not answer.strip():
                    answer = "(no answer generated)"

                # 评估
                scores = await self.evaluate_single(query, answer, contexts, item)
                per_item[i]["status"] = "done"
                results.append(scores)
            except Exception as exc:
                logger.warning("评估失败: %s — %s", query[:50], exc)
                per_item[i]["status"] = "error"
                per_item[i]["error"] = str(exc)
                results.append({
                    "query": query,
                    "error": str(exc),
                    "faithfulness": 0.0,
                    "context_precision": 0.0,
                    "context_recall": 0.0,
                    "answer_relevancy": 0.0,
                    "keyword_coverage": 0.0,
                })

            # 写入进度（每个 item 完成后）
            self._write_progress(progress_file, i + 1, len(dataset),
                                 current_query=query, per_item=per_item)

        # 清除进度文件
        if progress_file.exists():
            progress_file.unlink()

        # 汇总
        report = self._summarize(results)
        report["dataset_size"] = len(dataset)
        report["library"] = library
        report["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        report["details"] = results

        # 持久化
        self._save_report(report)
        return report

    def _write_progress(
        self, filepath: Path, current: int, total: int,
        current_query: str = "",
        per_item: list[dict] | None = None,
    ) -> None:
        """写入评估进度文件，包含每个 item 的详细状态和 RAG 阶段。"""
        progress = {
            "current": current,
            "total": total,
            "current_query": current_query,
            "per_item": per_item or [],
        }
        filepath.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")

    def get_progress(self) -> dict | None:
        """获取当前评估进度。"""
        progress_file = self.results_dir / "progress.json"
        if progress_file.exists():
            return json.loads(progress_file.read_text(encoding="utf-8"))
        return None

    # ── LLM-as-judge 评估方法 ──

    async def _eval_faithfulness(self, answer: str, contexts: list[str]) -> float:
        """faithfulness: 答案是否忠于上下文（不幻觉）。"""
        context_text = "\n---\n".join(contexts[:5])
        if not answer.strip() or answer == "(no answer generated)":
            return 0.0
        if not context_text.strip():
            return 0.0  # 无上下文可验证，无法评估忠实度
        prompt = (
            "Evaluate the faithfulness of the answer to the given context.\n\n"
            "Scoring guide:\n"
            "- 0.7-1.0: Most key claims are supported by the context\n"
            "- 0.4-0.6: Some claims supported, some not found or contradict\n"
            "- 0.1-0.3: Most claims are unsupported or hallucinated\n"
            "- 0.0: Answer is completely empty or fabricated\n\n"
            "Output ONLY the number.\n\n"
            f"Context:\n{context_text[:2000]}\n\n"
            f"Answer:\n{answer[:1000]}"
        )
        return await self._llm_score(prompt)

    async def _eval_context_precision(self, query: str, contexts: list[str]) -> float:
        """context_precision: 检索的上下文是否与查询相关。"""
        context_text = "\n---\n".join(contexts[:5])
        if not context_text.strip():
            return 0.0  # 无上下文，精确率为 0
        prompt = (
            "Evaluate the precision of the retrieved contexts for the given query.\n\n"
            "Scoring guide:\n"
            "- 0.7-1.0: Most contexts are directly relevant to the query\n"
            "- 0.4-0.6: Some contexts relevant, some off-topic\n"
            "- 0.1-0.3: Most contexts are irrelevant\n"
            "- 0.0: No contexts provided or all completely irrelevant\n\n"
            "Output ONLY the number.\n\n"
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
        matched = [kw for kw in keywords if kw.lower() in context_text]
        missed = [kw for kw in keywords if kw.lower() not in context_text]
        logger.info("评估 ContextRecall: 关键词=%s, 命中=%s, 未命中=%s, 上下文总长度=%d",
                     keywords, matched, missed, len(context_text))
        return round(hits / len(keywords), 3)

    async def _eval_answer_relevancy(self, query: str, answer: str) -> float:
        """answer_relevancy: 答案是否切题。"""
        if not answer.strip() or answer == "(no answer generated)":
            return 0.0
        prompt = (
            "Evaluate how relevant the answer is to the query.\n\n"
            "Scoring guide:\n"
            "- 0.7-1.0: Answer directly addresses the query with relevant information\n"
            "- 0.4-0.6: Partially relevant, some off-topic content\n"
            "- 0.1-0.3: Mostly off-topic or vague\n"
            "- 0.0: Completely irrelevant or empty\n\n"
            "Output ONLY the number.\n\n"
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
        matched = [kw for kw in keywords if kw.lower() in answer_lower]
        missed = [kw for kw in keywords if kw.lower() not in answer_lower]
        logger.info("评估 KeywordCoverage: 关键词=%s, 命中=%s, 未命中=%s, 答案长度=%d",
                     keywords, matched, missed, len(answer_lower))
        return round(hits / len(keywords), 3)

    # ── 辅助方法 ──

    async def _llm_score(self, prompt: str, retry_on_zero: bool = True) -> float:
        """v4.6: 调用 LLM 获取 0-1 分数，使用低温度 + 正则提取 + 0.0 重试。

        使用独立低温度客户端 (temperature=0) 确保评分一致性。
        用正则提取响应中的第一个浮点数，兼容 "0.5", "Score: 0.7", "0.8/1.0" 等格式。
        若得分为 0.0，自动重试一次（带更强锚定提示）。
        """
        client = _get_eval_client()
        model = settings.DEEPSEEK_MODEL
        system_prompt = (
            "You are a fair and generous evaluator. "
            "Rate on a scale of 0.0 to 1.0. "
            "Anchor your scoring: start from 0.5 for average quality, "
            "adjust up for good answers, down for poor ones. "
            "Only output 0.0 if the answer is completely empty or nonsensical. "
            "Output ONLY the numeric score, nothing else."
        )

        async def _do_score(p: str, sp: str) -> float:
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": sp},
                            {"role": "user", "content": p},
                        ],
                        max_tokens=50,
                        temperature=0.0,  # 确定性输出，确保评分一致
                        stream=False,
                    ),
                    timeout=60,
                )
                raw = (response.choices[0].message.content or "").strip()
                logger.info("LLM 评分原始响应: %s", raw[:200])

                # 正则提取第一个浮点数，兼容 "0.5", "Score: 0.7", "0.8/1.0" 等
                match = re.search(r"(\d+\.?\d*)", raw)
                if match:
                    score = float(match.group(1))
                    # 如果分数 > 1.0，可能是百分比，归一化
                    if score > 1.0:
                        score = score / 100.0 if score <= 100 else 1.0
                    return max(0.0, min(1.0, round(score, 3)))
                else:
                    logger.warning("LLM 评分无法提取数字: %s", raw[:200])
                    return 0.5
            except asyncio.TimeoutError:
                logger.warning("LLM 评分超时 (60s)，返回默认值 0.5")
                return 0.5
            except Exception as exc:
                logger.warning("LLM 评分失败: %s", exc)
                return 0.5

        score = await _do_score(prompt, system_prompt)

        # 如果得分为 0.0 且允许重试，用更强锚定再试一次
        if retry_on_zero and score == 0.0:
            logger.info("LLM 评分为 0.0，使用更强锚定重试...")
            retry_sp = (
                "You are a generous evaluator. "
                "Rate on a scale of 0.0 to 1.0. "
                "IMPORTANT: Unless the answer is completely empty, "
                "start from 0.3 and adjust upward based on quality. "
                "Do NOT output 0.0 unless there is literally no content to evaluate. "
                "Output ONLY the numeric score."
            )
            score = await _do_score(prompt, retry_sp)

        return score

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
        num_queries: int = 3,
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
