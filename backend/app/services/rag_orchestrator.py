"""升级版 RAG 在线编排器。

v3.3 升级:
- 邻居扩展落地: expand_neighbors=True 实际传给 retrieval_service.search()
- 忠实度反馈闭环: flagged 句子触发 LLM 二次生成，再次失败降级话术
- 管线延迟监控: 每阶段 yield perf 事件
- 查询分类路由: 事实查询跳过 HyDE+CRAG，概念查询跳过 HyDE
- 多轮对话摘要: 替换简单截断为 ConversationSummaryMemory
- 上下文 Token 预算: 按 CRAG 分数分配 chard 预算
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator, Sequence

from app.core.config import settings
from app.models.schemas import SourceCitation
from app.services.llm_service import llm_service
from app.services.metrics_service import metrics_service  # v4.0
from app.services.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)


class RAGOrchestrator:
    SYSTEM_PROMPT = """你是一个严谨的知识库问答助手。请遵守：
1. 优先基于【参考文档】回答，并在关键信息后标注 [1]、[2] 等引用。
2. 如果参考文档不足以回答，明确说明"根据已有文档，我无法确认"。
3. 不要编造参考文档中不存在的信息。
4. 回答要清晰、简洁、有条理。"""

    # v3.3: 二次生成修正引导 prompt
    CORRECTION_PROMPT = """你的上一轮回答中，以下句子被标记为可能无法从参考文档验证：
{corrections}

请重新生成回答，修正这些问题：
1. 对标记的句子，检查其关键断言是否真的在参考文档中
2. 如果文档确实没有，请移除或改为"根据已有文档，我无法确认..."
3. 保持其他验证通过的句子不变
4. 继续标注引用 [1]、[2]"""

    def __init__(self) -> None:
        self._llm_sem = asyncio.Semaphore(settings.CHAT_MAX_CONCURRENT_LLM)

    async def chat_stream(
        self,
        query: str,
        history: Sequence[dict] | None = None,
        user_id: str = "anonymous",
        library: str | None = None,  # v4.0: 按库过滤检索
    ) -> AsyncGenerator[dict, None]:
        t0 = time.time()
        from app.services.crag_service import crag_service
        from app.services.query_rewriter import query_rewriter
        from app.services.semantic_cache import semantic_cache

        # ── v4.4: L1 精确缓存（在分类前检查，<1ms）──
        from app.services.cache_service import cache_service
        l1_hit = cache_service.get(query, library)
        if l1_hit:
            if settings.METRICS_ENABLED:
                from app.services.metrics_service import metrics_service
                metrics_service.record_cache_hit()
                metrics_service.record_query()
            yield {"type": "cache", "data": json.dumps({"hit": True, "similarity": 1.0, "layer": "L1"})}
            yield {"type": "source", "data": json.dumps(l1_hit["sources"], ensure_ascii=False)}
            yield {"type": "token", "data": l1_hit["answer"]}
            yield self._perf("pipeline", t0)
            yield {"type": "done", "data": ""}
            return

        # ── v3.3: 查询分类路由（v4.1: 返回 dict） ──
        query_type = "synthesis"  # default
        is_code_query = False
        if settings.QUERY_CLASSIFIER_ENABLED:
            t_classify = time.time()
            from app.services.query_classifier import query_classifier
            classify_result = await query_classifier.classify(query, history)
            query_type = classify_result["query_type"]
            is_code_query = classify_result["is_code_query"]
            yield self._perf("classify", t_classify)
            logger.info(
                "查询分类: %s → %s (code=%s)", query[:50], query_type, is_code_query
            )

        # ── 语义缓存 ──
        cache_hit = await semantic_cache.lookup(query)
        if cache_hit:
            # v4.0: 记录缓存命中
            if settings.METRICS_ENABLED:
                from app.services.metrics_service import metrics_service
                metrics_service.record_cache_hit()
                metrics_service.record_query()
            yield {"type": "cache", "data": json.dumps({"hit": True, "similarity": cache_hit.similarity})}
            yield {"type": "source", "data": json.dumps(cache_hit.sources, ensure_ascii=False)}
            yield {"type": "token", "data": cache_hit.answer}
            yield self._perf("pipeline", t0)
            yield {"type": "done", "data": ""}
            return

        # v4.0: cache miss counter
        if settings.METRICS_ENABLED:
            from app.services.metrics_service import metrics_service as _ms
            _ms.record_cache_miss()

        # v4.4: stage 事件 —— 检索阶段开始
        yield {"type": "stage", "data": json.dumps({"stage": "retrieving", "label": "正在检索文档..."})}

        # v4.1: multi-hop planning（C4 Agentic 多跳检索）
        multi_hop_plan = None
        if settings.MULTI_HOP_ENABLED and query_type == "synthesis":
            from app.services.query_planner import query_planner
            t_plan = time.time()
            multi_hop_plan = await query_planner.plan(query, library)
            yield self._perf("plan", t_plan)

        if multi_hop_plan and multi_hop_plan["needs_multi_hop"]:
            # v4.1: 多跳路径 —— 为每个子查询分别检索（跳过 rewrite/hyde）
            t_retrieve = time.time()
            retrieval_lists = []
            for sub in multi_hop_plan["sub_queries"]:
                sub_lists = await self._parallel_retrieve(
                    [sub["query"]], expand_neighbors=True,
                    library=sub.get("library"),
                )
                retrieval_lists.extend(sub_lists)
            logger.info(
                "多跳检索: %d 子查询, %d 检索列表",
                len(multi_hop_plan["sub_queries"]), len(retrieval_lists),
            )
        else:
            # ── 并行: Query Rewrite + HyDE ──
            t_rewrite = time.time()
            # v4.5: 带历史上下文的查询改写
            rewrite_task = asyncio.create_task(
                query_rewriter.rewrite_with_history(query, history, settings.RAG_FUSION_VARIANTS)
                if history else
                query_rewriter.rewrite(query, settings.RAG_FUSION_VARIANTS)
            )

            hyde_task = None
            # v4.6: 对所有查询启用 HyDE——向量模型 all-MiniLM-L6-v2 不支持中文，
            # 中文查英文文档得分极低（<0.22），HyDE 生成假设性英文文档后检索分可达 0.6+
            if settings.HYDE_ENABLED:
                from app.services.hyde_service import hyde_service
                if settings.HYDE_PARALLEL:
                    hyde_task = asyncio.create_task(hyde_service.generate(query))
                else:
                    await rewrite_task
                    hyde_task = asyncio.create_task(hyde_service.generate(query))

            variants = await rewrite_task
            queries = [query, *variants]
            logger.info(
                "RAG Fusion 查询数: %s type=%s (user=%s)",
                len(queries), query_type, user_id,
            )
            yield self._perf("rewrite", t_rewrite)

            # ── 并行检索（v3.3: 邻居扩展落地, v4.5: 自适应权重）──
            t_retrieve = time.time()
            retrieval_lists = await self._parallel_retrieve(
                queries, expand_neighbors=True, library=library,
                query_type=query_type,  # v4.5
            )

            if hyde_task:
                try:
                    hyde_text = await hyde_task
                    if hyde_text:
                        hyde_docs = await asyncio.to_thread(
                            retrieval_service.search,
                            hyde_text,
                            settings.RETRIEVAL_TOP_K,
                            False,
                            expand_neighbors=True,
                            library=library,  # v4.0
                        )
                        retrieval_lists.append(hyde_docs)
                        logger.info("HyDE 检索: %s 条结果", len(hyde_docs))
                except Exception as exc:
                    logger.warning("HyDE 检索失败: %s", exc)

        # v3.3: 检索去重
        if settings.RETRIEVAL_DEDUP_ENABLED:
            retrieval_lists = [
                self._dedup_results(rl) for rl in retrieval_lists
            ]

        # v4.1: 代码子索引检索（C2）
        if is_code_query:
            try:
                code_docs = await asyncio.to_thread(
                    retrieval_service.search_code, query, 5, library,
                )
                if code_docs:
                    retrieval_lists.append(code_docs)
                    logger.info("代码子索引检索: %s 条结果", len(code_docs))
            except Exception as exc:
                logger.warning("代码子索引检索失败: %s", exc)

        yield self._perf("retrieve", t_retrieve)

        # ── RRF 融合 & Reranker ──
        candidates = self._rrf_fusion(retrieval_lists, top_k=max(settings.RERANKER_TOP_K * 3, 8))
        candidates = await self._rerank(query, candidates, top_k=max(settings.RERANKER_TOP_K, 5))

        # ── CRAG 评估 & 动态重写 ──
        # v3.3: 事实查询跳过 CRAG
        skip_crag = query_type == "fact_lookup"
        t_crag = time.time()
        crag_result = None
        if not skip_crag:
            crag_result = await crag_service.process(query=query, docs=candidates)
            if crag_result.should_retry and crag_result.rewrite_query:
                retry_docs = await asyncio.to_thread(
                    retrieval_service.search,
                    crag_result.rewrite_query,
                    max(settings.RERANKER_TOP_K * 2, 8),
                    False,
                    expand_neighbors=True,
                    library=library,  # v4.0
                )
                retry_docs = await self._rerank(query, retry_docs, top_k=max(settings.RERANKER_TOP_K, 5))
                crag_result = await crag_service.process(query=query, docs=retry_docs)
            docs = crag_result.docs[: settings.RERANKER_TOP_K]
        else:
            docs = candidates[: settings.RERANKER_TOP_K]
        yield self._perf("crag" if not skip_crag else "crag_skipped", t_crag)

        # ── v3.2: 上下文 sandwich 排序 ──
        ordered_docs = self._sandwich_order(docs)

        sources = self._build_sources(ordered_docs)
        sources_payload = [source.model_dump() for source in sources]

        # ── v3.3: 多轮对话摘要压缩 ──
        compressed_history = await self._summarize_history(history)

        # ── LLM 生成 ──
        t_gen = time.time()
        # v4.4: stage 事件 —— 生成阶段
        yield {"type": "stage", "data": json.dumps({"stage": "generating", "label": "正在生成回答..."})}
        messages = self._build_messages(query=query, docs=ordered_docs, history=compressed_history)
        answer_parts: list[str] = []
        # v4.5: 前缀缓冲 —— 收集前 150 字符检测并剥离冗余前缀（如"根据参考文档，"）
        _prefix_buffer: list[str] = []
        _prefix_sent = False
        async with self._llm_sem:
            async for token in llm_service.chat_stream(messages=messages, system_prompt=self.SYSTEM_PROMPT):
                answer_parts.append(token)
                if _prefix_sent:
                    yield {"type": "token", "data": token}
                    continue
                _prefix_buffer.append(token)
                buffered = "".join(_prefix_buffer)
                if len(buffered) >= 150 or "\n" in buffered or buffered.rstrip().endswith((".", "。", "!", "！", "?", "？")):
                    _prefix_sent = True
                    cleaned = self._strip_prefix(buffered)
                    if cleaned and cleaned != buffered:
                        # 前缀已剥离，调整 answer_parts
                        prefix_len = len(buffered) - len(cleaned)
                        # 从 answer_parts 中移除前缀对应的 token
                        accumulated = ""
                        cut = 0
                        for j, t in enumerate(answer_parts):
                            accumulated += t
                            cut += 1
                            if len(accumulated) >= prefix_len:
                                break
                        answer_parts = [cleaned] + answer_parts[cut:]
                        yield {"type": "token", "data": cleaned}
                    else:
                        for t in _prefix_buffer:
                            yield {"type": "token", "data": t}
        answer = "".join(answer_parts)
        yield self._perf("generate", t_gen)

        # v4.5: 回答后处理管线
        from app.services.answer_postprocessor import answer_postprocessor
        processed_answer = answer_postprocessor.process(answer, len(ordered_docs))
        if processed_answer != answer:
            # 后处理有修改，补发差异 token
            diff = processed_answer[len(answer):] if processed_answer.startswith(answer) else ""
            if diff:
                yield {"type": "token", "data": diff}
            answer = processed_answer

        # ── v3.3: 忠实度验证 + 反馈闭环 ──
        faithfulness_warned = False
        if settings.FAITHFULNESS_CHECK_ENABLED and answer.strip():
            # v4.4: stage 事件 —— 忠实度校验
            yield {"type": "stage", "data": json.dumps({"stage": "faithfulness_check", "label": "正在验证答案忠实度..."})}
            answer, sources_payload, faithfulness_warned, ff_events = await self._faithfulness_loop(
                query=query,
                answer=answer,
                docs=ordered_docs,
                sources_payload=sources_payload,
                messages_template=messages,
            )
            for evt in ff_events:
                yield evt

        # v4.5: 过滤未引用的来源，并重新编号为 1, 2, ...
        cited_indices = set()
        if answer:
            import re
            cited_indices = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
        if cited_indices:
            # 构建旧编号 → 新编号映射（按原始顺序排序后从 1 开始）
            sorted_cited = sorted(cited_indices)
            renumber_map = {old: new for new, old in enumerate(sorted_cited, start=1)}

            # 过滤 + 重新编号 sources
            sources_payload = [s for s in sources_payload if s.get("index") in cited_indices]
            for s in sources_payload:
                s["index"] = renumber_map[s["index"]]
            ordered_docs = [d for i, d in enumerate(ordered_docs) if (i + 1) in cited_indices]

            # 重新编号回答中的引用
            def _renumber_citation(match):
                old = int(match.group(1))
                return f"[{renumber_map.get(old, old)}]"
            renumbered_answer = re.sub(r"\[(\d+)\]", _renumber_citation, answer)
            if renumbered_answer != answer:
                answer = renumbered_answer
                # 发送替换事件，让前端用重新编号后的回答替换当前内容
                yield {"type": "replace", "data": renumbered_answer}

            # 补发过滤+重新编号后的来源列表
            yield {"type": "source", "data": json.dumps(sources_payload, ensure_ascii=False)}

        await semantic_cache.store(query=query, answer=answer, sources=sources_payload)

        # v4.4: 写入 L1 精确缓存
        cache_service.set(query, library, answer=answer, sources=sources_payload)

        # v4.0: 管线指标记录
        if settings.METRICS_ENABLED:
            from app.services.metrics_service import metrics_service
            ms_retrieve = round((time.time() - t_retrieve) * 1000)
            ms_generate = round((time.time() - t_gen) * 1000)
            retrieval_count = sum(len(rl) for rl in retrieval_lists)
            metrics_service.record_query(
                retrieval_count=retrieval_count,
                retrieve_ms=ms_retrieve,
                generate_ms=ms_generate,
            )
            if faithfulness_warned:
                metrics_service.record_faithfulness_warning()
        # v4.4: stage 事件 —— 完成
        yield {"type": "stage", "data": json.dumps({"stage": "complete", "label": "已完成"})}
        yield self._perf("pipeline", t0)
        yield {"type": "done", "data": ""}

    async def _parallel_retrieve(
        self,
        queries: list[str],
        expand_neighbors: bool = True,
        library: str | None = None,  # v4.0
        query_type: str | None = None,  # v4.5
    ) -> list[list[dict]]:
        """v3.3: 邻居扩展落地 —— expand_neighbors 参数实际传给 search()。
        v4.5: 传入 query_type 实现自适应权重"""
        tasks = [
            asyncio.to_thread(
                retrieval_service.search,
                query,
                settings.RETRIEVAL_TOP_K,
                False,  # use_reranker (handled separately)
                expand_neighbors=expand_neighbors,
                library=library,  # v4.0
                query_type=query_type,  # v4.5
            )
            for query in queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        lists: list[list[dict]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("检索分支失败: %s", result)
                continue
            lists.append(result)
        return lists

    async def _faithfulness_loop(
        self,
        query: str,
        answer: str,
        docs: list[dict],
        sources_payload: list[dict],
        messages_template: list[dict],
    ) -> tuple[str, list[dict], bool, list[dict]]:
        """v3.3 新增: 忠实度反馈闭环。

        1. 验证当前 answer
        2. 有 flagged 句子 → 二次生成（带修正引导）
        3. 二次仍失败 → 降级话术

        Returns: (answer, sources_payload, has_warning, events)
            events: 需要由调用方 yield 的 SSE 事件列表
        """
        from app.services.faithfulness_checker import faithfulness_checker

        has_warning = False
        events: list[dict] = []

        for attempt in range(settings.FAITHFULNESS_MAX_RETRIES + 1):
            is_faithful, flagged, hints = await faithfulness_checker.check(
                answer=answer,
                sources=docs,
            )

            if is_faithful:
                logger.info("忠实度验证通过 (attempt %d)", attempt + 1)
                return answer, sources_payload, has_warning, events

            has_warning = True

            if attempt >= settings.FAITHFULNESS_MAX_RETRIES:
                # 降级：在答案末尾追加免责声明
                logger.warning("忠实度纠正失败，降级话术: %d sentences flagged", len(flagged))
                answer = self._append_disclaimer(answer, hints or [])
                events.append({"type": "faithfulness_warning", "data": json.dumps({
                    "flagged_sentences": len(flagged),
                    "retries_exhausted": True,
                    "details": flagged[:3],
                }, ensure_ascii=False)})
                return answer, sources_payload, has_warning, events

            # 二次生成
            logger.info("忠实度反馈闭环: attempt %d, flags=%d", attempt + 1, len(flagged))
            events.append({"type": "faithfulness_warning", "data": json.dumps({
                "flagged_sentences": len(flagged),
                "retrying": True,
                "clear_content": True,  # v4.5: 通知前端清空已显示的原始答案
                "attempt": attempt + 1,
            }, ensure_ascii=False)})

            correction_text = "\n".join(hints or [])
            correction_msg = {
                "role": "user",
                "content": self.CORRECTION_PROMPT.format(corrections=correction_text),
            }
            regen_messages = messages_template + [{"role": "assistant", "content": answer}, correction_msg]

            new_parts: list[str] = []
            async with self._llm_sem:
                async for token in llm_service.chat_stream(
                    messages=regen_messages,
                    system_prompt=self.SYSTEM_PROMPT,
                ):
                    new_parts.append(token)
                    events.append({"type": "token", "data": token})
            answer = "".join(new_parts)

        return answer, sources_payload, has_warning, events

    def _append_disclaimer(self, answer: str, hints: list[str]) -> str:
        """v3.3: 在答案末尾追加降级话术。"""
        if not hints:
            return answer
        flagged_info = "; ".join(
            hint.split("—")[-1].strip()[:100]
            for hint in hints[:3]
        )
        return (
            answer
            + "\n\n---\n"
            + "⚠️ 根据已有文档，以上部分信息无法完全确认："
            + flagged_info
            + "。请以原始文档为准。"
        )

    async def _summarize_history(
        self,
        history: Sequence[dict] | None,
    ) -> Sequence[dict] | None:
        """v3.3 新增: 多轮对话摘要压缩。

        替换简单截断最近 6 条 → 用轻量 LLM 压缩历史为 200 字摘要。
        """
        if not settings.CONVERSATION_SUMMARY_ENABLED or not history:
            return history

        if len(history) <= settings.RAG_MAX_HISTORY_MESSAGES:
            return history

        try:
            hist_text = "\n".join(
                f"{msg.get('role', '?')}: {str(msg.get('content', ''))[:300]}"
                for msg in list(history)[-12:]
            )
            prompt = (
                "请将以下对话历史压缩为一段 200 字以内的摘要，保留关键事实、主题和用户意图。"
                f"\n\n对话历史：\n{hist_text}"
            )

            summary = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是对话摘要助手，简洁精炼。",
            )
            if summary.strip():
                logger.info("对话摘要: %s chars → %s chars", len(hist_text), len(summary))
                return [
                    {
                        "role": "system",
                        "content": f"【历史对话摘要】{summary.strip()[:200]}",
                    }
                ]

        except Exception as exc:
            logger.warning("对话摘要生成失败: %s", exc)

        return list(history)[-settings.RAG_MAX_HISTORY_MESSAGES:]

    def _dedup_results(self, results: list[dict]) -> list[dict]:
        """v3.3: 基于 content 前 200 字符做模糊去重。"""
        if not results:
            return results
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in results:
            fingerprint = str(r.get("content", ""))[:200].strip()
            if fingerprint and fingerprint not in seen:
                seen.add(fingerprint)
                deduped.append(r)
        if len(deduped) < len(results):
            logger.info("检索去重: %d → %d", len(results), len(deduped))
        return deduped

    def _rrf_fusion(self, ranked_lists: list[list[dict]], top_k: int) -> list[dict]:
        fused: dict[str, dict] = {}
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked):
                chunk_id = str(item.get("chunk_id", ""))
                if not chunk_id:
                    continue
                score = 1.0 / (retrieval_service.RRF_K + rank + 1)
                if chunk_id not in fused:
                    fused[chunk_id] = {**item, "score": score}
                else:
                    fused[chunk_id]["score"] = float(fused[chunk_id].get("score", 0)) + score
        return sorted(fused.values(), key=lambda item: float(item.get("score", 0)), reverse=True)[:top_k]

    async def _rerank(self, query: str, docs: list[dict], top_k: int) -> list[dict]:
        if not docs:
            return []
        # v4.5: reranker 同步调用阻塞线程池，默认跳过，使用 RRF 分数排序
        # 如需启用，设置环境变量 RERANKER_ENABLED=true
        if not os.environ.get("RERANKER_ENABLED", "false").lower() == "true":
            return docs[:top_k]
        try:
            from app.services.reranker_service import reranker
            return await asyncio.to_thread(reranker.rerank, query, docs, top_k)
        except Exception as exc:
            logger.warning("Reranker 不可用，使用 RRF 分数排序: %s", exc)
            return docs[:top_k]

    def _sandwich_order(self, docs: list[dict]) -> list[dict]:
        if not settings.CONTEXT_SANDWICH_ENABLED or len(docs) <= 3:
            return docs
        k = min(settings.CONTEXT_SANDWICH_TOP_K, len(docs) // 3)
        if k == 0:
            return docs
        sorted_docs = sorted(docs, key=lambda d: float(d.get("score", 0)), reverse=True)
        head = sorted_docs[:k]
        tail = sorted_docs[k:k * 2] if k * 2 <= len(sorted_docs) else []
        middle = sorted_docs[k * 2:] if k * 2 <= len(sorted_docs) else sorted_docs[k:]
        ordered = head + middle + list(reversed(tail))
        logger.info("上下文 sandwich 排序: head=%d middle=%d tail=%d", len(head), len(middle), len(tail))
        return ordered

    def _build_sources(self, docs: list[dict]) -> list[SourceCitation]:
        """v4.0: 引用溯源 —— 包含 source_url, heading_path, library, version"""
        return [
            SourceCitation(
                index=index + 1,
                content=str(doc.get("content", ""))[:300],
                page=doc.get("page"),
                documentName=doc.get("document_name"),
                relevanceScore=float(doc.get("crag_score", doc.get("score", 0.0))),
                # v4.0
                sourceUrl=doc.get("source_url"),
                headingPath=doc.get("heading_path"),
                library=doc.get("library"),
                version=doc.get("version"),
            )
            for index, doc in enumerate(docs)
        ]

    @staticmethod
    def _strip_prefix(text: str) -> str:
        """v4.5: 剥离 LLM 回答中的冗余前缀（如 '根据参考文档，'）。"""
        import re
        patterns = [
            r"^根据(?:提供的)?(?:参考)?文档[内容]*[，,。：:\s]*",
            r"^根据(?:上述)?文档[，,。：:\s]*",
            r"^根据已有文档[，,。：:\s]*",
            r"^根据(?:以上)?参考文档[，,。：:\s]*",
            r"^基于(?:提供的)?文档[，,。：:\s]*",
            r"^Based on (?:the )?(?:provided |reference )?documents?[，,。:\s]*",
            r"^According to (?:the )?documents?[，,。:\s]*",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text

    def _build_messages(
        self,
        query: str,
        docs: list[dict],
        history: Sequence[dict] | None,
    ) -> list[dict]:
        """v3.3: Token 预算管理 —— 按 CRAG 分数分配 chard 预算。"""
        if docs:
            if settings.CONTEXT_TOKEN_BUDGET_ENABLED:
                context_text = self._budget_context(docs)
            else:
                context_text = "\n\n---\n\n".join(
                    f"[{index + 1}] 来源: {doc.get('document_name', '未知')}, "
                    f"第{doc.get('page', '?')}页\n{doc.get('content', '')}"
                    for index, doc in enumerate(docs)
                )
        else:
            context_text = "（未检索到可靠参考文档）"

        messages = list(history or [])[-settings.RAG_MAX_HISTORY_MESSAGES * 2:]  # allow more with summaries
        messages.append({
            "role": "user",
            "content": f"【参考文档】\n{context_text}\n\n【用户问题】\n{query}\n\n请基于参考文档回答。",
        })
        return messages

    def _budget_context(self, docs: list[dict]) -> str:
        """v3.3: 按 CRAG 分数分配 Token 预算。

        高分 chunk 最多 800 chars，低分最多 300 chars。
        总预算不超过 CONTEXT_MAX_TOKENS × 4 (chars ≈ tokens × 4)。
        """
        max_chars = settings.CONTEXT_MAX_TOKENS * 4
        total_score = sum(max(float(d.get("score", 0)), 0.01) for d in docs)

        parts: list[str] = []
        used = 0

        for idx, doc in enumerate(docs):
            score = max(float(doc.get("score", 0)), 0.01)
            # 按分数比例分配，但设上下限
            budget = int(max_chars * score / total_score)
            budget = max(min(budget, 800), 150)  # 每 chunk 150-800 chars
            budget = min(budget, max_chars - used)

            content = str(doc.get("content", ""))[:budget]
            parts.append(
                f"[{idx + 1}] 来源: {doc.get('document_name', '未知')}, "
                f"第{doc.get('page', '?')}页 (score={score:.2f})\n{content}"
            )
            used += budget
            if used >= max_chars:
                break

        logger.info("Token 预算: %d docs → %d chars (limit=%d)", len(docs), used, max_chars)
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _perf(stage: str, t_start: float) -> dict:
        """v3.3: 管线延迟监控事件。同时推送至 metrics_service。"""
        ms = round((time.time() - t_start) * 1000)
        # v4.0: 记录到指标服务
        if settings.METRICS_ENABLED:
            metrics_service.record_latency(stage, ms)
        return {"type": "perf", "data": json.dumps({"stage": stage, "ms": ms})}


rag_orchestrator = RAGOrchestrator()
