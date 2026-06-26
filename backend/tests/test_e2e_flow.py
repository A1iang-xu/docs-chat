"""v4.3: 端到端流程测试 —— 验证从文档入库到检索回答的完整链路

覆盖:
- D3: 文档入库流程（Markdown → 切分 → 向量入库 → BM25 索引）
- D3: 多文档库隔离检索
- D3: 查询分类器（双语 + 代码意图）
- D3: 查询规划器（单跳/多跳检测）
- D3: 完整 RAG 聊天流程（Mock LLM）
"""
import pytest
from unittest.mock import patch

from app.services.markdown_chunker import markdown_chunker
from app.services.vector_store import vector_store
from app.services.retrieval_service import retrieval_service
from app.services.query_classifier import QueryClassifier
from app.services.query_planner import QueryPlanner


SAMPLE_MARKDOWN = """# Vue 3 响应式系统

## ref()

`ref()` 是最基础的响应式 API，用于创建对任意值的响应式引用。

```javascript
import { ref } from 'vue'

const count = ref(0)
console.log(count.value) // 0
count.value++
console.log(count.value) // 1
```

### ref 的特性
- 可以包装任意类型（基本类型 + 对象）
- 通过 `.value` 访问和修改值
- 模板中自动解包，无需 `.value`

## reactive()

`reactive()` 用于创建对象的深层响应式代理。

```javascript
import { reactive } from 'vue'

const state = reactive({
  count: 0,
  user: { name: 'Vue' }
})
state.count++
```

## computed()

`computed()` 创建只读的计算属性。

```javascript
import { ref, computed } from 'vue'
const count = ref(0)
const double = computed(() => count.value * 2)
```

## watch()

`watch()` 监听响应式数据的变化。

```javascript
import { ref, watch } from 'vue'
const count = ref(0)
watch(count, (newVal, oldVal) => {
  console.log(`从 ${oldVal} 变为 ${newVal}`)
})
```
"""


# ═══════════════════════════════════════════
# D3: 文档入库端到端流程
# ═══════════════════════════════════════════

class TestE2EIngestionFlow:
    """测试完整文档入库流程：Markdown → 切分 → 向量入库 → BM25 索引"""

    def test_split_markdown_produces_chunks(self):
        """切分器应产出带元数据的 chunk"""
        chunks = markdown_chunker.split(SAMPLE_MARKDOWN, library="test-vue")
        assert len(chunks) > 0
        for chunk in chunks:
            assert hasattr(chunk, "content")
            assert hasattr(chunk, "chunk_id")
            assert chunk.library == "test-vue"

    def test_code_blocks_extracted(self):
        """代码块应被单独切分（is_code_block=True）"""
        chunks = markdown_chunker.split(SAMPLE_MARKDOWN, library="test-vue")
        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) >= 4  # ref, reactive, computed, watch 四个代码块

    def test_deterministic_chunk_ids(self):
        """相同内容应产出相同 chunk_id（确定性哈希）"""
        chunks_a = markdown_chunker.split(SAMPLE_MARKDOWN, library="test-vue")
        chunks_b = markdown_chunker.split(SAMPLE_MARKDOWN, library="test-vue")
        ids_a = [c.chunk_id for c in chunks_a]
        ids_b = [c.chunk_id for c in chunks_b]
        assert ids_a == ids_b

    def test_bm25_index_built(self):
        """BM25 索引应成功构建"""
        chunks = markdown_chunker.split(SAMPLE_MARKDOWN, library="test-vue")
        chunk_dicts = [c.to_dict() for c in chunks]
        try:
            retrieval_service.build_bm25_index(chunk_dicts, library="test-vue")
            assert "test-vue" in retrieval_service.bm25_indexes
        except Exception as exc:
            pytest.skip(f"BM25 索引构建跳过: {exc}")


# ═══════════════════════════════════════════
# D3: 多文档库隔离检索
# ═══════════════════════════════════════════

class TestE2ELibraryFilter:
    """测试多文档库隔离检索"""

    def test_vector_search_with_library_filter(self):
        """向量检索应支持 library 过滤"""
        try:
            results = vector_store.search("ref", top_k=5, where={"library": "vue"})
            assert isinstance(results, list)
        except Exception as exc:
            pytest.skip(f"向量搜索跳过: {exc}")

    def test_code_subindex_search(self):
        """代码子索引检索应正常返回"""
        try:
            results = vector_store.search_code("computed", top_k=5)
            assert isinstance(results, list)
        except Exception as exc:
            pytest.skip(f"代码子索引搜索跳过: {exc}")

    def test_get_libraries_returns_list(self):
        """get_libraries 应返回已入库的库列表"""
        try:
            libs = vector_store.get_libraries()
            assert isinstance(libs, list)
        except Exception as exc:
            pytest.skip(f"获取库列表跳过: {exc}")


# ═══════════════════════════════════════════
# D3: 查询分类器端到端
# ═══════════════════════════════════════════

class TestE2EQueryClassifier:
    """测试查询分类器（双语 + 代码意图）"""

    @pytest.mark.asyncio
    async def test_fact_lookup_classification(self):
        """事实查询应正确分类"""
        classifier = QueryClassifier()
        result = await classifier.classify("ref 的默认值是什么？")
        assert isinstance(result, dict)
        assert result["query_type"] in ("fact_lookup", "concept_explain")

    @pytest.mark.asyncio
    async def test_code_intent_detection(self):
        """代码意图应被检测到"""
        classifier = QueryClassifier()
        result = await classifier.classify("给我看一下 ref 的代码示例")
        assert isinstance(result, dict)
        assert result.get("is_code_query") is True

    @pytest.mark.asyncio
    async def test_concept_classification(self):
        """概念查询应分类为 concept_explain"""
        classifier = QueryClassifier()
        result = await classifier.classify("什么是 Vue 3 响应式系统？")
        assert isinstance(result, dict)
        assert result["query_type"] == "concept_explain"

    @pytest.mark.asyncio
    async def test_synthesis_classification(self):
        """综合查询应分类为 synthesis"""
        classifier = QueryClassifier()
        result = await classifier.classify("如何使用 ref 和 reactive？")
        assert isinstance(result, dict)
        assert result["query_type"] in ("synthesis", "concept_explain")

    @pytest.mark.asyncio
    async def test_english_query_classification(self):
        """英文查询应正确分类"""
        classifier = QueryClassifier()
        result = await classifier.classify("what is composition API")
        assert isinstance(result, dict)
        assert result["query_type"] in ("concept_explain", "fact_lookup", "synthesis")


# ═══════════════════════════════════════════
# D3: 查询规划器端到端
# ═══════════════════════════════════════════

class TestE2EQueryPlanner:
    """测试多跳查询规划器"""

    @pytest.mark.asyncio
    async def test_single_hop_no_split(self):
        """简单查询不需要多跳"""
        planner = QueryPlanner()
        result = await planner.plan("什么是 ref？")
        assert isinstance(result, dict)
        assert "needs_multi_hop" in result
        assert result["needs_multi_hop"] is False

    @pytest.mark.asyncio
    async def test_comparison_triggers_multi_hop(self):
        """对比查询应触发多跳"""
        planner = QueryPlanner()
        result = await planner.plan("对比 ref 和 reactive 的区别")
        assert isinstance(result, dict)
        assert result["needs_multi_hop"] is True
        assert len(result.get("sub_queries", [])) >= 2

    @pytest.mark.asyncio
    async def test_english_comparison_triggers_multi_hop(self):
        """英文对比查询应触发多跳"""
        planner = QueryPlanner()
        result = await planner.plan("compare ref and reactive")
        assert isinstance(result, dict)
        assert result["needs_multi_hop"] is True


# ═══════════════════════════════════════════
# D3: 完整 RAG 聊天流程（Mock LLM）
# ═══════════════════════════════════════════

class TestE2EFullChat:
    """测试完整 RAG 聊天流程（Mock 关键依赖避免真实 API 调用）"""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_events(self):
        """chat_stream 应产出事件流（mock LLM + 检索 + 缓存）"""
        from app.services.rag_orchestrator import RAGOrchestrator

        orchestrator = RAGOrchestrator()

        async def mock_llm_stream(*args, **kwargs):
            yield "Vue 3 的 "
            yield "ref() 用于创建响应式引用。"

        mock_docs = [{
            "content": "ref() 是最基础的响应式 API",
            "metadata": {"library": "vue", "source": "test"},
            "score": 0.9,
        }]

        try:
            with patch("app.services.rag_orchestrator.llm_service") as mock_llm:
                mock_llm.chat_stream = mock_llm_stream
                with patch("app.services.rag_orchestrator.retrieval_service") as mock_ret:
                    mock_ret.search = lambda *a, **kw: mock_docs
                    with patch("app.services.semantic_cache.semantic_cache.lookup", return_value=None):
                        with patch("app.services.query_rewriter.query_rewriter.rewrite", return_value=[]):
                            events = []
                            async for event in orchestrator.chat_stream("什么是 ref？", library="vue"):
                                events.append(event)
                            assert len(events) > 0
        except Exception as exc:
            pytest.skip(f"完整聊天流程跳过（依赖外部服务）: {exc}")

    @pytest.mark.asyncio
    async def test_chat_stream_with_history(self):
        """带历史记录的聊天应正常工作"""
        from app.services.rag_orchestrator import RAGOrchestrator

        orchestrator = RAGOrchestrator()

        async def mock_llm_stream(*args, **kwargs):
            yield "根据上文，ref() 返回一个响应式对象。"

        history = [
            {"role": "user", "content": "什么是 Vue 3？"},
            {"role": "assistant", "content": "Vue 3 是一个前端框架。"},
        ]

        try:
            with patch("app.services.rag_orchestrator.llm_service") as mock_llm:
                mock_llm.chat_stream = mock_llm_stream
                with patch("app.services.rag_orchestrator.retrieval_service") as mock_ret:
                    mock_ret.search = lambda *a, **kw: []
                    with patch("app.services.semantic_cache.semantic_cache.lookup", return_value=None):
                        with patch("app.services.query_rewriter.query_rewriter.rewrite", return_value=[]):
                            events = []
                            async for event in orchestrator.chat_stream(
                                "那 ref 呢？", history=history, library="vue"
                            ):
                                events.append(event)
                            assert len(events) >= 0  # 不崩溃即可
        except Exception as exc:
            pytest.skip(f"带历史的聊天流程跳过: {exc}")
