# DocsChat

面向开发者的技术文档智能助手。粘一个官方文档站链接（如 `vuejs.org`、`fastapi.tiangolo.com`），自动抓取入库即可问答。支持 PDF 上传、URL 自动抓取、多库命名空间、代码感知分块、引用溯源、可观测管线与用户反馈闭环。

## 核心能力

| 能力 | 说明 |
|------|------|
| URL 自动入库 | 输入文档站地址，Crawl4AI 自动抓取（Sitemap 优先 + 同域受控 BFS），Playwright 渲染 SPA 文档站，Fit Markdown 去噪 |
| 代码感知分块 | MarkdownHeader 按标题切分 + 代码块围栏保护，代码块不截断，标注语言 |
| 多库命名空间 | Vue、FastAPI、LangChain 各自独立，检索时按库过滤，BM25 按库增量 |
| URL 引用溯源 | 答案引用可点击跳转回原文页面，含标题路径 |
| 双语查询分类 | 中英文关键词 + few-shot，事实/概念/综合三类路由，跳过冗余管线节省 Token |
| 代码子索引 | 代码块独立 collection，代码意图查询路由到代码子索引 |
| Agentic 多跳 | 对比类查询自动拆解为子查询分别检索再综合 |
| 可观测管线 | P50/P95 延迟、缓存命中率、忠实度警告率等实时指标 |
| 用户反馈闭环 | 答案 👍/👎 落库，驱动评估与调参 |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / SSE / ChromaDB / BM25 / jieba |
| RAG | LangChain / BGE-M3 Embedding / BGE-Reranker / CRAG / HyDE / RRF |
| 大模型 | DeepSeek V4 API（OpenAI 兼容）/ Ollama + Qwen2（本地备用） |
| 抓取 | Crawl4AI v0.5.0（Playwright + Fit Markdown） |
| 前端 | Vite + Vue3 + TypeScript / Pinia / Axios |
| 部署 | Docker Compose |

## 快速启动

### 前置要求

- Python 3.10+
- Node.js 20+
- Docker & Docker Compose（可选）

### 1. 后端

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入 DEEPSEEK_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

### 3. Docker 一键启动

```bash
cp backend/.env.example backend/.env  # 编辑填入 API Key
docker compose up --build
```

## 使用方式

### PDF 上传

在前端上传 PDF 文件，系统自动解析、分块、入库。

### URL 自动入库

```bash
# 通过 API 提交文档站 URL
curl -X POST http://localhost:8000/libraries/ingest-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://vuejs.org/guide", "library_slug": "vue", "version": "3"}'

# 轮询任务状态
curl http://localhost:8000/documents/jobs/{job_id}

# 查看已入库的库
curl http://localhost:8000/libraries/
```

### 问答

在前端选择库（或"全部库"），输入问题即可。答案引用可点击跳转回原文。

## 项目结构

```
docs-chat/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由: chat, documents, libraries, feedback, stats
│   │   ├── core/           # 配置 (config.py)
│   │   ├── middleware/     # API Key 中间件
│   │   ├── models/         # Pydantic schemas
│   │   ├── services/       # RAG 核心逻辑
│   │   │   ├── rag_orchestrator.py     # 主编排器
│   │   │   ├── query_classifier.py     # 双语查询分类
│   │   │   ├── query_planner.py        # 多跳查询规划
│   │   │   ├── markdown_chunker.py     # 代码感知分块
│   │   │   ├── web_ingestion_service.py # URL 抓取入库
│   │   │   ├── vector_store.py         # ChromaDB (text + code 子索引)
│   │   │   ├── retrieval_service.py    # 混合检索 + 按库 BM25
│   │   │   ├── metrics_service.py      # 可观测指标聚合
│   │   │   └── feedback_service.py     # 用户反馈存储
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── stores/         # libraryStore, conversation, message
│   │   ├── components/     # ChatMessage, LibrarySelector, ...
│   │   └── views/
│   └── Dockerfile
├── docker-compose.yml
└── docs/                   # 升级方案文档
```

## 版本演进

| 版本 | 主题 | 核心升级 |
|------|------|---------|
| v3.0 | 骨架搭建 | FastAPI + ChromaDB + DeepSeek 基础 RAG |
| v3.1 | 外部服务补齐 | MinerU / BGE-M3 / CRAG / 语义缓存 / 限流 |
| v3.2 | 检索质量优化 | jieba / 语义分块 / sandwich / HyDE / 忠实度 |
| v3.3 | 管线精细化 | 批量忠实度 / 反馈闭环 / 查询路由 / Token 预算 / FAISS 预热 |
| v4.0 | 场景落地 | URL 自动入库 / 代码感知分块 / 多库命名空间 / 引用溯源 / 可观测 / 反馈闭环 |
| v4.1 | 算法深化 | 双语查询分类 / 代码子索引 / Agentic 多跳检索 |

## 测试

```bash
cd backend
pytest tests/ -v
```
