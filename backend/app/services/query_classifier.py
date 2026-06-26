"""查询分类路由服务。

v3.3 新增:
- 将用户查询分为 fact_lookup / concept_explain / synthesis 三类
- 事实查询: 跳过 HyDE + CRAG → 节省 Token 60% 延迟 50%
- 概念查询: 跳过 HyDE → 节省 Token 30%
- 综合推理: 走完整管线

v4.1 升级:
- 正则增加英文关键词（双语），适配开发者文档场景
- LLM 兜底 prompt 改为英文双语 + few-shot 示例
- 新增 detect_code_intent: 检测代码意图，供 C2 代码子索引路由
- classify 返回 dict: {query_type, is_code_query}
- 分类结果 LRU 缓存，避免相同查询重复分类

分类逻辑（轻量关键词+规则优先，LLM 兜底）:
- fact_lookup: 包含"是多少/哪天/谁/什么时间/在哪/代码/参数/版本"
              或 "what is/how many/which version/parameter/config/api reference"
- concept_explain: 包含"是什么/什么意思/如何理解/定义/原理"
              或 "what does/what is/explain/define/concept/principle/why"
- synthesis: 包含"如何/怎么/比较/区别/分析/总结/优缺点"
              或 "how to/how do/compare/difference/vs/best practice/tutorial/guide"
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Sequence

from app.core.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# ── v4.1: 双语快速分类规则（0 延迟，命中率 ~80%）──
_FACT_PATTERNS = re.compile(
    r"(是多少|哪天|几月|几点|谁|什么人|什么时间|什么时候|在哪|哪里"
    r"|代码|参数|版本|配置|几行|多少页|第几章|具体数字|截至)"
    r"|(what\s+is|how\s+many|which\s+version|parameter|config\b|version\b"
    r"|api\s+reference|return\s+type|default\s+value)",
    re.IGNORECASE,
)
_CONCEPT_PATTERNS = re.compile(
    r"(是什么|什么是|什么意思|如何理解|定义|概念|原理|为什么|原因|解释|介绍)"
    r"|(what\s+does|what\s+is|explain|define|concept|principle"
    r"|why\b|reason|introduction|overview|understand)",
    re.IGNORECASE,
)
_SYNTHESIS_PATTERNS = re.compile(
    r"(如何|怎么|怎样|比较|区别|vs|对比|分析|总结|归纳|梳理|评估"
    r"|优缺点|利弊|方案|建议|推荐|步骤|流程|方法)"
    r"|(how\s+to|how\s+do|how\s+can|compare|difference|vs\.?"
    r"|versus|best\s+practice|step\s+by|tutorial|guide\b|example)",
    re.IGNORECASE,
)

# ── v4.1: 代码意图检测 ──
_CODE_INTENT_PATTERNS = re.compile(
    r"(怎么写|示例|代码|写法|用法|写一个|实现|示例代码|代码示例)"
    r"|(how\s+to\s+write|code\s+example|sample\s+code|implementation"
    r"|snippet|how\s+do\s+i\s+(write|create|implement|use))",
    re.IGNORECASE,
)

# ── v4.1: few-shot 示例（开发者场景典型查询）──
_FEW_SHOT_EXAMPLES = """Examples:
Query: "ref() 的返回类型是什么" → fact_lookup
Query: "what is the default value of props" → fact_lookup
Query: "FastAPI 的 version 参数" → fact_lookup
Query: "defineProps 的返回类型" → fact_lookup
Query: "什么是响应式" → concept_explain
Query: "explain dependency injection in FastAPI" → concept_explain
Query: "computed 和 watch 的原理" → concept_explain
Query: "what is composition API" → concept_explain
Query: "Vue2 和 Vue3 响应式有什么区别" → synthesis
Query: "how to migrate from options API to composition API" → synthesis
Query: "compare ref and reactive" → synthesis
Query: "how to use ref()" → synthesis
Query: "what is the difference between ref and reactive" → synthesis"""


class _LRUCache:
    """简单的 LRU 缓存，用于分类结果去重。"""

    def __init__(self, capacity: int = 200):
        self._capacity = capacity
        self._store: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, key: str, value: str) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._capacity:
            self._store.popitem(last=False)


class QueryClassifier:
    """查询分类器: 轻量双语规则优先，LLM 兜底。v4.1 增加代码意图检测。"""

    def __init__(self) -> None:
        if settings.QUERY_CLASSIFIER_CACHE_ENABLED:
            self._cache = _LRUCache(settings.QUERY_CLASSIFIER_CACHE_SIZE)
        else:
            self._cache = None

    async def classify(
        self,
        query: str,
        history: Sequence[dict] | None = None,
    ) -> dict:
        """分类查询，返回 {query_type, is_code_query}。

        query_type: fact_lookup / concept_explain / synthesis
        is_code_query: True 表示查询含代码意图（如"怎么写"/"code example"）
        """
        if not settings.QUERY_CLASSIFIER_ENABLED:
            return {"query_type": "synthesis", "is_code_query": False}

        q = query.strip()
        is_code_query = self.detect_code_intent(q)

        # v4.1: 缓存命中
        cache_key = q
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("查询分类（缓存）: %s", cached)
                return {"query_type": cached, "is_code_query": is_code_query}

        # 规则优先: 统计各类型模式匹配数
        fact_count = len(_FACT_PATTERNS.findall(q))
        concept_count = len(_CONCEPT_PATTERNS.findall(q))
        synthesis_count = len(_SYNTHESIS_PATTERNS.findall(q))

        query_type = None

        # 短查询且单一模式 → 直接规则判定
        if len(q) < 30:
            if fact_count > concept_count and fact_count > synthesis_count:
                query_type = "fact_lookup"
            elif concept_count > fact_count and concept_count > synthesis_count:
                query_type = "concept_explain"
            elif synthesis_count > fact_count:
                query_type = "synthesis"

        # 中等长度: 有强规则信号直接用
        if query_type is None:
            if synthesis_count >= 2 or (synthesis_count >= 1 and len(q) > 40):
                query_type = "synthesis"
            elif fact_count >= 2 and synthesis_count == 0:
                query_type = "fact_lookup"
            elif concept_count >= 2 and synthesis_count == 0:
                query_type = "concept_explain"

        if query_type is None:
            # LLM 兜底（仅模糊查询触发，~10-20% 情况）
            try:
                query_type = await self._llm_classify(q)
            except Exception as exc:
                logger.warning("LLM 分类失败，回退 synthesis: %s", exc)
                query_type = "synthesis"

        logger.info("查询分类: %s → %s (code_intent=%s)", q[:50], query_type, is_code_query)

        # v4.1: 写入缓存
        if self._cache is not None:
            self._cache.put(cache_key, query_type)

        return {"query_type": query_type, "is_code_query": is_code_query}

    def detect_code_intent(self, query: str) -> bool:
        """v4.1: 检测查询是否含代码意图。

        触发条件: "怎么写"/"示例代码"/"how to write"/"code example" 等。
        用于 C2 代码子索引路由。
        """
        return bool(_CODE_INTENT_PATTERNS.search(query))

    async def _llm_classify(self, query: str) -> str:
        """LLM 兜底分类（v4.1: 双语 prompt + few-shot）。"""
        few_shot = ""
        if settings.QUERY_CLASSIFIER_FEW_SHOT_ENABLED:
            few_shot = "\n" + _FEW_SHOT_EXAMPLES + "\n"

        prompt = (
            "Classify the following developer query into one of three categories:\n"
            "- fact_lookup: queries for specific facts, numbers, parameters, "
            "API signatures, return types, version numbers\n"
            "- concept_explain: queries for concept definitions, principles, "
            "explanations, overviews\n"
            "- synthesis: queries requiring comparison, analysis, step-by-step "
            "guides, best practices, multi-source synthesis\n"
            "Output only the category label (fact_lookup / concept_explain / synthesis), "
            "no explanation."
            f"{few_shot}"
            f"\nQuery: {query}"
        )
        result = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a query classifier. Output only the label.",
        )
        label = result.strip().lower()
        if label in ("fact_lookup", "concept_explain", "synthesis"):
            logger.info("查询分类（LLM）: %s", label)
            return label
        return "synthesis"


query_classifier = QueryClassifier()
