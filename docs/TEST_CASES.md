# DocsChat v3.1 测试用例文档

**项目**：docs-chat | **版本**：v3.1 | **日期**：2026-06-20  
**测试框架**：pytest + pytest-asyncio（后端）/ Vitest + @vue/test-utils（前端）

---

## 目录

1. [测试架构总览](#1-测试架构总览)
2. [后端测试用例](#2-后端测试用例)
   - [2.1 健康检查](#21-健康检查)
   - [2.2 文档上传](#22-文档上传)
   - [2.3 SSE 流式对话](#23-sse-流式对话)
   - [2.4 LLM 服务层](#24-llm-服务层)
   - [2.5 外部模型服务](#25-外部模型服务)
   - [2.6 E2E 全链路](#26-e2e-全链路)
3. [前端测试用例](#3-前端测试用例)
   - [3.1 useSSE Composable](#31-usesse-composable)
   - [3.2 ChatMessage 组件](#32-chatmessage-组件)
   - [3.3 MessageInput 组件](#33-messageinput-组件)
4. [运行测试命令](#4-运行测试命令)
5. [测试覆盖率矩阵](#5-测试覆盖率矩阵)

---

## 1. 测试架构总览

```
tests/
├── conftest.py                    # 全局 fixtures（AsyncClient）
├── test_health.py                 # 健康检查端点
├── test_documents.py              # 文档上传 API
├── test_chat.py                   # SSE 流式对话
├── test_llm_service.py            # LLM 服务层单元测试
├── test_external_services.py      # 外部模型服务集成测试
│   ├── TestQualityGate            # 质量门禁
│   ├── TestMinerUAPIService       # MinerU API
│   ├── TestRemoteEmbedding        # BGE-M3 Embedding
│   ├── TestQwenReranker           # Qwen3-Reranker
│   └── TestE2EIngestion           # 摄取链路
└── e2e_pipeline_test.py           # 全链路联调与防御边界
    ├── TestAsyncIngestionStateMachine   # 异步摄取状态机
    ├── TestSemanticCacheIntegration     # 语义缓存
    ├── TestCRAGHallucinationGuard       # CRAG 防幻觉
    ├── TestSSEResilience                # SSE 安全与容错
    ├── TestLoggingAudit                 # 日志复核
    └── TestE2EFullPipeline              # 全链路综合
```

**测试策略**：
- **单元测试**：Mock 外部依赖，验证单一函数/模块逻辑
- **集成测试**：Mock 外部 API，验证多模块协作
- **E2E 测试**：模拟完整数据流，验证状态机、边界条件、容错降级

---

## 2. 后端测试用例

### 2.1 健康检查

**文件**：`backend/tests/test_health.py`  
**运行**：`pytest tests/test_health.py -v`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-HL-001 | 健康检查端点返回正确格式 | 后端服务正常启动 | GET `/health` | 200 OK，`{"status":"ok","service":"DocsChat API"}` | ✅ 已实现 |
| TC-HL-002 | 服务诊断端点返回结构完整 | 后端服务正常启动 | GET `/health/services` | 返回包含 `mineru`/`embedding`/`reranker`/`deepseek`/`quality_gate`/`all_healthy` 字段的 JSON | ⚠️ 未覆盖 |
| TC-HL-003 | 服务诊断当 DeepSeek 不可用时 all_healthy=false | DEEPSEEK_API_KEY 为占位符 | GET `/health/services` | `all_healthy: false`，`deepseek.available: false` | ⚠️ 未覆盖 |
| TC-HL-004 | 服务诊断当所有外部服务正常时 all_healthy=true | 所有外部服务 Mock 可用 | GET `/health/services` | `all_healthy: true` | ⚠️ 未覆盖 |

---

### 2.2 文档上传

**文件**：`backend/tests/test_documents.py`  
**运行**：`pytest tests/test_documents.py -v`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-DOC-001 | 非 PDF 文件被拒绝 | 准备 .txt 文件 | POST `/documents/upload`，file 为 test.txt | 400 或 422，拒绝上传 | ✅ 已实现 |
| TC-DOC-002 | 未携带文件被拒绝 | 无 | POST `/documents/upload` 不带 file 字段 | 422 | ✅ 已实现 |
| TC-DOC-003 | 合法 PDF 上传返回 job_id | 准备有效 PDF 文件 | POST `/documents/upload`，file 为 test.pdf | 201，返回 `{job_id, filename, status: "queued"}` | ⚠️ 未覆盖 |
| TC-DOC-004 | 上传后轮询任务状态（queued → running → ready） | 上传 PDF 触发异步解析 | GET `/documents/jobs/{job_id}` 轮询 | 状态依序流转：queued → running → ready | ⚠️ 未覆盖 |
| TC-DOC-005 | 上传后轮询任务状态（queued → running → failed） | 上传内容不足的 PDF | GET `/documents/jobs/{job_id}` 轮询 | 状态流转：queued → running → failed，error 字段非空 | ⚠️ 未覆盖 |
| TC-DOC-006 | 轮询不存在的 job_id 返回 404 | 无 | GET `/documents/jobs/nonexistent` | 404 | ⚠️ 未覆盖 |
| TC-DOC-007 | 列出所有任务 | 存在多个 job | GET `/documents/jobs` | 返回任务列表，包含各 job 状态 | ⚠️ 未覆盖 |
| TC-DOC-008 | 文档列表返回已入库文档 | 知识库中有文档 | GET `/documents/` | 返回文档列表，含 `filename`、`chunk_count` | ⚠️ 未覆盖 |
| TC-DOC-009 | 超大文件上传（> 限制） | 准备 > 限制大小的 PDF | POST `/documents/upload` | 413 或后端拒绝 | ⚠️ 未覆盖 |

---

### 2.3 SSE 流式对话

**文件**：`backend/tests/test_chat.py`  
**运行**：`pytest tests/test_chat.py -v`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-CHAT-001 | SSE 端点返回 `data:` 前缀格式 | Mock LLM 流式响应 | POST `/chat/stream`，content="你好" | 200，响应体包含 `data:` 和 `done` 事件 | ✅ 已实现 |
| TC-CHAT-002 | 空消息被拒绝 | 无 | POST `/chat/stream`，content="" | 422 | ✅ 已实现 |
| TC-CHAT-003 | SSE 包含 `source` 事件 | Mock 检索 + LLM | POST `/chat/stream?rag=true`，知识库非空 | 200，响应包含 `source` 事件和引用文档 | ⚠️ 未覆盖 |
| TC-CHAT-004 | SSE 包含 `cache` 事件（缓存命中） | Mock 语义缓存命中 | POST `/chat/stream?rag=true`，相似问题 | 200，响应包含 `cache` 事件，`hit: true` | ⚠️ 未覆盖 |
| TC-CHAT-005 | SSE 客户端断连后优雅中止 | 模拟断连 | POST `/chat/stream`，中途断开连接 | 无异常崩溃，Semaphore 释放 | ⚠️ 未覆盖 |
| TC-CHAT-006 | 非 RAG 模式直接对话 | Mock LLM | POST `/chat/stream?rag=false` | 200，不触发检索，直接 LLM 生成 | ⚠️ 未覆盖 |
| TC-CHAT-007 | 消息过长被拒绝 | 无 | POST `/chat/stream`，content 超过限制 | 422 | ⚠️ 未覆盖 |
| TC-CHAT-008 | 缺少 conversation_id 被拒绝 | 无 | POST `/chat/stream`，不传 conversation_id | 422 | ⚠️ 未覆盖 |

---

### 2.4 LLM 服务层

**文件**：`backend/tests/test_llm_service.py`  
**运行**：`pytest tests/test_llm_service.py -v`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-LLM-001 | 流式调用逐 token 返回 | Mock OpenAI AsyncOpenAI | `chat_stream([{"role":"user","content":"Hi"}])` | 返回 token 列表，包含 "Hello"，`stream=True` | ✅ 已实现 |
| TC-LLM-002 | 系统提示词被正确注入 | Mock OpenAI | `chat_stream(messages, system_prompt="You are...")` | messages[0] 为 system role，messages[1] 为 user role | ✅ 已实现 |
| TC-LLM-003 | 非流式调用返回完整内容 | Mock OpenAI | `chat([{"role":"user","content":"Hello"}])` | 返回 "完整回答" | ✅ 已实现 |
| TC-LLM-004 | API 调用失败自动重试（指数退避） | Mock API 连续失败 | `chat_stream()`，API 返回 429/500 | 重试最多 3 次，全失败后抛出异常 | ⚠️ 未覆盖 |
| TC-LLM-005 | API 超时处理 | Mock API 超时 | `chat_stream()`，API 超时 | 抛出超时异常，不阻塞 | ⚠️ 未覆盖 |
| TC-LLM-006 | API Key 无效时返回明确错误 | DEEPSEEK_API_KEY=invalid | `chat_stream()` | 抛出 401 错误，包含 authentication_error | ⚠️ 未覆盖 |

---

### 2.5 外部模型服务

**文件**：`backend/tests/test_external_services.py`  
**运行**：`pytest tests/test_external_services.py -v`

#### 2.5.1 质量门禁

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-QG-001 | 健康文档通过质量门禁 | 准备含标题和表格的 chunks | `quality_gate.validate()` | `passed=true`，标题数/表格数正确 | ✅ 已实现 |
| TC-QG-002 | 空 chunks 被拒绝 | chunks=[] | `quality_gate.validate()` | `passed=false`，警告 "无有效分块" | ✅ 已实现 |
| TC-QG-003 | 字符数不足被拒绝 | 设置 QG_MIN_CHARS=5000 | `quality_gate.validate()` | `passed=false`，警告含 "总字符数" | ✅ 已实现 |
| TC-QG-004 | 标题和表格计数正确 | Markdown 含 3 个标题 + 1 个表格 | `quality_gate.validate()` | `heading_count=3`, `table_count=1` | ✅ 已实现 |
| TC-QG-005 | 门禁关闭时总是通过 | QG_ENABLED=false | `quality_gate.validate()` | `passed=true` 不受内容影响 | ✅ 已实现 |
| TC-QG-006 | 页数不足被拒绝 | 设置 QG_MIN_PAGES=5，实际 1 页 | `quality_gate.validate()` | `passed=false` | ⚠️ 未覆盖 |

#### 2.5.2 MinerU API

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-MU-001 | MinerU API 成功解析返回 Markdown | Mock HTTP 200 | `load_and_split()` | 返回 chunks 列表，内容为 Markdown 分块 | ✅ 已实现 |
| TC-MU-002 | MinerU API 失败自动回退到 CLI | Mock API 抛异常 | `load_and_split()` | 调用 `_parse_with_mineru`（CLI 模式） | ✅ 已实现 |
| TC-MU-003 | MinerU API + CLI 均失败回退到 PyPDF | Mock API + CLI 均抛异常 | `load_and_split()` | 调用 `_parse_with_pypdf` | ✅ 已实现 |
| TC-MU-004 | MinerU 健康检查 | 无真实服务 | `check_mineru_api_health()` | `available: false` | ✅ 已实现 |
| TC-MU-005 | MinerU API 超时处理 | Mock HTTP 超时 | `load_and_split()` | 超时后走降级链 | ⚠️ 未覆盖 |
| TC-MU-006 | MinerU CLI 超时处理 | Mock 子进程超过 1800s | `_parse_with_mineru()` | TimeoutExpired，走 PyPDF 降级 | ⚠️ 未覆盖 |

#### 2.5.3 BGE-M3 Embedding

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-EMB-001 | 远程 Embedding 批量调用正确 | Mock HTTP 返回 1024 维向量 | `_embed_batch(["text1","text2","text3"])` | 返回 3 个 1024 维向量，batch_size=2→2 次请求 | ✅ 已实现 |
| TC-EMB-002 | ENABLE_BGE_M3=true 时构建 RemoteEmbeddingFunction | 配置 BGE_M3_ENABLED=true | `_build_embedding_function()` | 返回 `RemoteEmbeddingFunction` 实例 | ✅ 已实现 |
| TC-EMB-003 | 无特殊配置时使用 ChromaDB 默认 Embedding | BGE_M3_ENABLED=false | `_build_embedding_function()` | 返回 `DefaultEmbeddingFunction` 实例 | ✅ 已实现 |
| TC-EMB-004 | 维度自动检测与清理 | 旧 Collection 384 维，配置 1024 维 | 首次访问 `collection` | 自动删除旧 Collection，重建 1024 维 | ⚠️ 未覆盖 |
| TC-EMB-005 | Embedding API 不可用时的降级 | Mock HTTP 连续失败 | `_embed_batch()` | 抛出可恢复异常，不崩溃 | ⚠️ 未覆盖 |

#### 2.5.4 Qwen3-Reranker

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-RR-001 | 远程 Reranker 正确排序 | Mock HTTP 返回 relevance_score | `rerank("query", docs, top_k=3)` | 返回 3 个文档，按 score 降序排列 | ✅ 已实现 |
| TC-RR-002 | QWEN_RERANKER_ENABLED=true 自动切换远程模式 | 配置环境变量 | `_probe_mode()` | 探测远程模式 | ✅ 已实现 |
| TC-RR-003 | Reranker 服务不可用时降级为无精排 | RERANKER_API_URL 不可达 | `rerank()` | 原样返回 docs，不报错 | ⚠️ 未覆盖 |
| TC-RR-004 | 文档数少于 top_k 时返回全部 | docs 只有 2 条，top_k=5 | `rerank()` | 返回 2 条文档 | ⚠️ 未覆盖 |

---

### 2.6 E2E 全链路

**文件**：`backend/tests/e2e_pipeline_test.py`  
**运行**：`pytest tests/e2e_pipeline_test.py -v`

#### 2.6.1 异步摄取状态机

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-E2E-001 | Job 生命周期：QUEUED → RUNNING → READY | 创建 job | `create_job` → `_mark(RUNNING)` → `_mark(READY)` | 状态依序变更，page_count/chunk_count 更新 | ✅ 已实现 |
| TC-E2E-002 | 查询不存在的 job_id 返回 None | 无 | `get_job("nonexistent")` | 返回 None | ✅ 已实现 |
| TC-E2E-003 | `list_jobs` 返回所有任务 | 创建 2 个 job | `list_jobs()` | 列表长度 +2 | ✅ 已实现 |
| TC-E2E-004 | 解析失败时 job 状态变为 failed 并记录错误 | 创建 job | `_mark(FAILED)`，设置 error="MinerU API timeout" | `status=failed`，`error` 包含 "timeout" | ✅ 已实现 |
| TC-E2E-005 | Semaphore 并发限制为 2 | INGESTION_MAX_CONCURRENT_JOBS=2 | 检查 `_sem._value` | 值为 2 | ✅ 已实现 |

#### 2.6.2 语义缓存

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-CACHE-001 | 空缓存时查询返回 None（cache miss） | ChromaDB count=0 | `lookup("什么是向量检索")` | 返回 None | ✅ 已实现 |
| TC-CACHE-002 | 写入缓存后相同 query 命中 | Mock ChromaDB 返回匹配结果 | `lookup("测试查询")` | 返回 `CacheHit`，`answer="缓存答案"`，`similarity≥0.85` | ✅ 已实现 |
| TC-CACHE-003 | TTL 过期后返回 None | Mock 缓存 created_at 超过 86400s | `lookup("历史查询")` | 返回 None | ✅ 已实现 |
| TC-CACHE-004 | 缓存禁用时不查询 | SEMANTIC_CACHE_ENABLED=false | `lookup()` | 直接返回 None | ✅ 已实现 |
| TC-CACHE-005 | 同一 query 多次写入幂等 | Mock ChromaDB | `store("幂等查询", ...)` 调用 2 次 | upsert 的 ids 为单个 UUID | ✅ 已实现 |
| TC-CACHE-006 | 相似度低于阈值时返回 None | Mock 距离 > 0.15（阈值 0.92 对应距离 0.08） | `lookup()` | 返回 None | ⚠️ 未覆盖 |

#### 2.6.3 CRAG 防幻觉

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-CRAG-001 | 高质量文档 → should_retry=False | Mock LLM 返回 scores [0.95, 0.90] | `process("测试", docs)` | `should_retry=False` | ✅ 已实现 |
| TC-CRAG-002 | 多个低分文档 → should_retry=True + rewrite_query | Mock LLM 返回 4/5 incorrect | `process("测试", docs)` | `should_retry=True`，`rewrite_query` 非空 | ✅ 已实现 |
| TC-CRAG-003 | CRAG 禁用时原样返回 docs | CRAG_ENABLED=false | `process("test", docs)` | `should_retry=False`，`docs` 不变 | ✅ 已实现 |
| TC-CRAG-004 | 空文档列表不崩溃 | docs=[] | `process("test", [])` | `should_retry=False`，`docs=[]` | ✅ 已实现 |
| TC-CRAG-005 | LLM 评估失败时降级到检索分数 | Mock LLM 抛异常 | `process("test", docs)` | 正常返回，`len(docs) > 0` | ✅ 已实现 |
| TC-CRAG-006 | 分数分类阈值正确 | 各种分数值 | 验证 correct/ambiguous/incorrect 分类 | 0.95→correct, 0.50→ambiguous, 0.10→incorrect | ✅ 已实现 |
| TC-CRAG-007 | 重检索后仍低质量 → 话术降级 | 二次检索后 incorrect_ratio 仍 ≥ 60% | `process()` | 最终返回 "无法确认" 降级话术 | ⚠️ 未覆盖 |

#### 2.6.4 SSE 安全与容错

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-SRE-001 | 限流器允许合法请求 | 创建 TokenBucketLimiter(5, 60) | 5 次 `allow("user_123")` | 全部返回 True | ✅ 已实现 |
| TC-SRE-002 | 限流器拒绝超额请求 | 创建 TokenBucketLimiter(3, 60) | 3 次后第 4 次 `allow()` | 第 4 次返回 False | ✅ 已实现 |
| TC-SRE-003 | 滑动窗口过期恢复 | 创建 TokenBucketLimiter(2, 0.01) | 用完 2 次 → sleep 0.02s → 再请求 | 恢复可用，返回 True | ✅ 已实现 |
| TC-SRE-004 | 无 Auth header 时用 IP 作为 user_id | 请求无 Authorization | `get_user_id()` | 返回 client IP "192.168.1.1" | ✅ 已实现 |
| TC-SRE-005 | Bearer token 正常提取 | Authorization: Bearer abc... | `get_user_id()` | 返回 token 后 24 位 | ✅ 已实现 |
| TC-SRE-006 | SSE 事件 JSON 格式符合规范 | 无 | 构造 SSEEvent("token", "Hello") | `model_dump_json()` 正确序列化 | ✅ 已实现 |
| TC-SRE-007 | 心跳包装器在无数据时发送心跳 | 慢速生成器 | `_with_heartbeat(slow_gen(), 0.01)` | 至少包含 2 个数据事件 | ✅ 已实现 |
| TC-SRE-008 | 客户端断连时 GeneratorExit 优雅释放 | 模拟 `request.is_disconnected()` 返回 True | 生成器循环中途中断 | 不抛出未捕获异常，Semaphore 释放 | ⚠️ 未覆盖 |

#### 2.6.5 日志复核

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-LOG-001 | 摄取流程日志包含状态迁移 | 创建 job 并模拟状态变更 | 检查日志 | 日志包含 RUNNING / READY 状态 | ✅ 已实现 |
| TC-LOG-002 | Reranker 模式选择有日志记录 | 无 | 记录 reranker mode 日志 | 日志包含 "reranker mode" | ✅ 已实现 |
| TC-LOG-003 | 配置字段存在且可读 | 无 | 检查所有新增配置字段 | `PARSER_TYPE`、`ENABLE_BGE_M3`、`RERANKER_TYPE` 等均可用 | ✅ 已实现 |

#### 2.6.6 全链路综合

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-E2E-010 | 完整文件 → 分块 → 入库流程 | Mock 所有外部依赖 | 模拟完整摄取流程 | job 状态 ready，page_count=2, chunk_count=2 | ✅ 已实现 |
| TC-E2E-011 | RAG 编排器对象结构完整 | 无 | 检查 `rag_orchestrator` 对象 | 存在 `chat_stream`、`_llm_sem`、`SYSTEM_PROMPT` | ✅ 已实现 |
| TC-E2E-012 | RRF 融合去重 + 分数累加 | 向量结果 2 条 + BM25 结果 2 条（重叠 1 条） | `_rrf_fusion()` | 返回 3 条（去重），重叠条 RRF 分数更高 | ✅ 已实现 |
| TC-E2E-013 | QueryRewriter JSON 解析 | 输入 `["v1","v2","v3"]` | `_parse_json_array()` | 返回 `["v1","v2","v3"]` | ✅ 已实现 |
| TC-E2E-014 | QueryRewriter 带前缀文本解析 | 输入 `some text ["a","b"] more` | `_parse_json_array()` | 正则提取，返回 `["a","b"]` | ✅ 已实现 |
| TC-E2E-015 | QueryRewriter 空输入抛异常 | 输入 `""` | `_parse_json_array("")` | 抛出 JSONDecodeError | ✅ 已实现 |

---

## 3. 前端测试用例

### 3.1 useSSE Composable

**文件**：`frontend/src/composables/__test__/useSSE.spec.ts`  
**运行**：`npx vitest run src/composables/__test__/useSSE.spec.ts`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-FE-SSE-001 | 初始状态正确 | 调用 `useSSE()` | 检查响应式状态 | content='', sources=[], isStreaming=false, error=null | ✅ 已实现 |
| TC-FE-SSE-002 | abort 后 isStreaming 变为 false | isStreaming=true | `abort('用户取消')` | isStreaming=false | ✅ 已实现 |
| TC-FE-SSE-003 | abort 传入 reason 时设置 error | 无 | `abort('连接超时')` | error='连接超时' | ✅ 已实现 |
| TC-FE-SSE-004 | connect 时重置状态 | 设置 content/sources/error 旧值 | `connect()` | 状态重置，content='', sources=[], error 为连接错误 | ✅ 已实现 |
| TC-FE-SSE-005 | 流式接收 token 事件 | Mock fetch Response | `connect()` → 模拟 SSE 推送 | content 逐段拼接，isStreaming=true | ⚠️ 未覆盖 |
| TC-FE-SSE-006 | 接收 source 事件更新引用 | Mock fetch Response | `connect()` → 模拟 SSE source 事件 | sources 更新为引用列表 | ⚠️ 未覆盖 |
| TC-FE-SSE-007 | done 事件结束流 | Mock fetch Response | `connect()` → 模拟 SSE done 事件 | isStreaming=false | ⚠️ 未覆盖 |
| TC-FE-SSE-008 | error 事件处理 | Mock fetch Response | `connect()` → 模拟 SSE error 事件 | error 设置错误信息，isStreaming=false | ⚠️ 未覆盖 |
| TC-FE-SSE-009 | 连接失败自动重试（指数退避） | Mock fetch 失败 2 次，第 3 次成功 | `connect()` | 重试 2 次后成功，延迟符合指数退避 | ⚠️ 未覆盖 |
| TC-FE-SSE-010 | 重试超过最大次数后停止 | Mock fetch 持续失败 | `connect()` | 达到 maxRetries 后停止，error 设置 | ⚠️ 未覆盖 |

### 3.2 ChatMessage 组件

**文件**：`frontend/src/components/__test__/ChatMessage.spec.ts`  
**运行**：`npx vitest run src/components/__test__/ChatMessage.spec.ts`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-FE-CM-001 | 渲染用户消息为纯文本 | 用户消息 content="你好世界" | 挂载组件 | 角色标签 "你"，文本内容 "你好世界" | ✅ 已实现 |
| TC-FE-CM-002 | 用户消息中 HTML 标签被转义 | content="`<script>alert('xss')</script>`" | 挂载组件 | HTML 不包含 `<script>`，包含 `&lt;script&gt;` | ✅ 已实现 |
| TC-FE-CM-003 | AI 消息渲染 Markdown 标题 | content="## 标题\n\n正文" | 挂载组件 | 角色标签 "DocsChat"，包含 `<h2>` | ✅ 已实现 |
| TC-FE-CM-004 | AI 消息中代码块渲染为 pre/code | content="\`\`\`python\nprint('hello')\n\`\`\`" | 挂载组件 | 存在 `<pre>` 和 `<code>`，内容含 "print" | ✅ 已实现 |
| TC-FE-CM-005 | 渲染来源引用卡片 | 1 个 SourceCitation | 挂载组件 | 显示 "参考来源："，badge "[1]"，tooltip 含原文和分数 | ✅ 已实现 |
| TC-FE-CM-006 | 无来源时不渲染来源区域 | sources=[] | 挂载组件 | 不渲染 `.sources` 区域 | ✅ 已实现 |
| TC-FE-CM-007 | 空消息不报错 | content="" | 挂载组件 | 不抛出异常 | ✅ 已实现 |
| TC-FE-CM-008 | AI 消息中表格渲染 | content 含 Markdown 表格 | 挂载组件 | 渲染为 `<table>` 元素 | ⚠️ 未覆盖 |

### 3.3 MessageInput 组件

**文件**：`frontend/src/components/__test__/MessageInput.spec.ts`  
**运行**：`npx vitest run src/components/__test__/MessageInput.spec.ts`

| 编号 | 用例名称 | 前置条件 | 操作 | 预期结果 | 状态 |
|------|----------|----------|------|----------|------|
| TC-FE-MI-001 | 输入框接受用户输入 | isSending=false | textarea.setValue('你好') | textarea.value='你好' | ✅ 已实现 |
| TC-FE-MI-002 | 点击发送按钮触发 send 事件并清空 | isSending=false | setValue('测试消息') → click button | emit('send', '测试消息')，textarea 清空 | ✅ 已实现 |
| TC-FE-MI-003 | 发送中状态禁止发送 | isSending=true | setValue('测试') → click button | 不 emit('send')，按钮 disabled | ✅ 已实现 |
| TC-FE-MI-004 | 空内容不触发发送（空白字符） | isSending=false | setValue('   ') → click button | 不 emit('send') | ✅ 已实现 |
| TC-FE-MI-005 | Enter 键发送消息 | isSending=false | setValue('Enter 测试') → keydown Enter | emit('send') | ✅ 已实现 |
| TC-FE-MI-006 | Shift+Enter 不发送（换行） | isSending=false | setValue('不发送') → keydown Shift+Enter | 不 emit('send') | ✅ 已实现 |
| TC-FE-MI-007 | 空内容不触发 Enter 发送 | isSending=false | textarea 为空 → keydown Enter | 不 emit('send') | ⚠️ 未覆盖 |

---

## 4. 运行测试命令

### 4.1 后端测试

```powershell
# 进入后端目录
cd backend

# 运行全部测试
pytest -v -s

# 运行指定模块
pytest tests/test_health.py -v
pytest tests/test_documents.py -v
pytest tests/test_chat.py -v
pytest tests/test_llm_service.py -v
pytest tests/test_external_services.py -v
pytest tests/e2e_pipeline_test.py -v

# 按关键字过滤
pytest -v -k "crag"          # 只运行 CRAG 相关测试
pytest -v -k "cache"         # 只运行语义缓存测试
pytest -v -k "rate_limit"    # 只运行限流测试

# 按标记过滤
pytest -v -m asyncio         # 只运行异步测试

# 生成覆盖率报告
pip install pytest-cov
pytest --cov=app --cov-report=html --cov-report=term
```

### 4.2 前端测试

```powershell
# 进入前端目录
cd frontend

# 运行全部测试
npx vitest run

# 运行指定模块
npx vitest run src/composables/__test__/useSSE.spec.ts
npx vitest run src/components/__test__/ChatMessage.spec.ts
npx vitest run src/components/__test__/MessageInput.spec.ts

# 监听模式（开发时）
npx vitest

# 生成覆盖率报告
npx vitest run --coverage
```

### 4.3 E2E 验证脚本

```powershell
cd backend
python scripts/test_e2e.py
```

---

## 5. 测试覆盖率矩阵

### 5.1 总体统计

| 层级 | 总用例数 | 已实现 | 未覆盖 | 覆盖率 |
|------|---------|--------|--------|--------|
| 后端 API 层 | 19 | 5 | 14 | 26.3% |
| 后端服务层 | 27 | 10 | 17 | 37.0% |
| E2E 全链路 | 28 | 28 | 0 | 100% |
| 前端 Composable | 10 | 4 | 6 | 40.0% |
| 前端组件 | 15 | 13 | 2 | 86.7% |
| **总计** | **99** | **60** | **39** | **60.6%** |

### 5.2 按模块分布

| 模块 | 已实现 | 未覆盖 | 测试文件 |
|------|--------|--------|----------|
| 健康检查 | 1 | 3 | `test_health.py` |
| 文档上传 API | 2 | 7 | `test_documents.py` |
| SSE 对话 | 2 | 6 | `test_chat.py` |
| LLM 服务层 | 3 | 3 | `test_llm_service.py` |
| 质量门禁 | 5 | 1 | `test_external_services.py` |
| MinerU | 4 | 2 | `test_external_services.py` |
| BGE-M3 Embedding | 3 | 2 | `test_external_services.py` |
| Qwen3-Reranker | 2 | 2 | `test_external_services.py` |
| 异步摄取状态机 | 5 | 0 | `e2e_pipeline_test.py` |
| 语义缓存 | 5 | 1 | `e2e_pipeline_test.py` |
| CRAG 防幻觉 | 6 | 1 | `e2e_pipeline_test.py` |
| SSE 安全 | 7 | 1 | `e2e_pipeline_test.py` |
| 日志复核 | 3 | 0 | `e2e_pipeline_test.py` |
| 全链路综合 | 6 | 0 | `e2e_pipeline_test.py` |
| useSSE | 4 | 6 | `useSSE.spec.ts` |
| ChatMessage | 7 | 1 | `ChatMessage.spec.ts` |
| MessageInput | 6 | 1 | `MessageInput.spec.ts` |

### 5.3 未覆盖用例优先级

#### 高优先级（影响核心功能）

| 编号 | 用例 | 建议 |
|------|------|------|
| TC-DOC-003 | 合法 PDF 上传返回 job_id | 补充上传 + 异步解析的完整流程测试 |
| TC-DOC-004 | 轮询状态流转（queued→running→ready） | 补充轮询 API 测试 |
| TC-CHAT-003 | SSE 包含 source 事件 | Mock 检索 + LLM 双重依赖 |
| TC-CHAT-004 | SSE 缓存命中事件 | 需要 Mock 语义缓存 |
| TC-CACHE-006 | 相似度低于阈值 | 边界测试 |
| TC-FE-SSE-005 | 流式接收 token | Mock ReadableStream |
| TC-FE-SSE-009 | 连接失败自动重试 | Mock fetch 失败/成功序列 |

#### 中优先级（增强健壮性）

| 编号 | 用例 | 建议 |
|------|------|------|
| TC-LLM-004 | API 重试逻辑 | 验证 3 次重试 + 指数退避 |
| TC-LLM-005 | API 超时处理 | 验证超时不阻塞 |
| TC-EMB-004 | 维度自动检测与清理 | 关键安全功能 |
| TC-CRAG-007 | 重检索后话术降级 | 完整的防幻觉链路 |
| TC-SRE-008 | 客户端断连优雅释放 | 验证 GeneratorExit 处理 |

#### 低优先级（完善覆盖率）

| 编号 | 用例 | 建议 |
|------|------|------|
| TC-HL-002~004 | 服务诊断端点 | 补充健康检查结构验证 |
| TC-DOC-009 | 超大文件上传 | 边界测试 |
| TC-CHAT-007 | 消息过长 | 边界测试 |
| TC-MU-005~006 | MinerU 超时 | 降级链完整性 |
| TC-EMB-005 | Embedding API 降级 | 容错测试 |
| TC-RR-003~004 | Reranker 降级 | 容错测试 |
| TC-FE-SSE-010 | 重试耗尽 | 前端容错 |
| TC-FE-CM-008 | 表格渲染 | 组件完整性 |
| TC-FE-MI-007 | 空内容 Enter | 边界测试 |

---

> **维护说明**：本文档随代码变更同步更新。新增功能时，请同时更新对应测试用例编号和状态标记。`✅ 已实现` 表示存在对应的自动化测试代码，`⚠️ 未覆盖` 表示需要补充测试。