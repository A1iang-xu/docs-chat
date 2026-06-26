# DocsChat v3.1 完整运行指南

**项目**：docs-chat | **版本**：v3.1 | **日期**：2026-06-20  
**环境**：Windows 11 / Python 3.13.5 / Node v24.11.1 / npm 11.6.2

---

## 目录

1. [环境要求](#1-环境要求)
2. [快速启动（3 分钟）](#2-快速启动3-分钟)
3. [详细步骤](#3-详细步骤)
4. [端到端验证](#4-端到端验证)
5. [常见问题排查](#5-常见问题排查)
6. [本次运行实测记录](#6-本次运行实测记录)

---

## 1. 环境要求

| 组件 | 最低版本 | 本次实测版本 | 用途 |
|------|----------|-------------|------|
| Python | 3.10+ | 3.13.5 | 后端运行时 |
| pip | 23.0+ | 25.1.1 | Python 包管理 |
| Node.js | 18+ | 24.11.1 | 前端运行时 |
| npm | 9+ | 11.6.2 | 前端包管理 |
| 磁盘空间 | 2GB+ | — | ChromaDB 持久化 + 模型缓存 |

**可选外部服务**（高性能模式，非必需）：

| 服务 | 最低要求 | 用途 |
|------|----------|------|
| Docker | 24+ | MinerU / BGE-M3 / Qwen3-Reranker 容器化部署 |
| NVIDIA GPU | 6GB+ VRAM | MinerU hybrid-auto-engine / BGE-M3 / Qwen3-Reranker 推理 |
| DeepSeek API Key | — | LLM 对话生成（必需，否则对话功能不可用） |

---

## 2. 快速启动（3 分钟）

> 以下命令在项目根目录 `e:\docs-chat` 下执行。

```powershell
# ── 第 1 步：安装后端依赖 ──
cd backend
pip install -r requirements.txt

# ── 第 2 步：配置 API Key ──
# 编辑 backend/.env，将 DEEPSEEK_API_KEY 改为真实 key
# 如果复制 .env.example：copy .env.example .env

# ── 第 3 步：启动后端（终端 1） ──
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# ── 第 4 步：启动前端（终端 2） ──
cd frontend
npm install
npm run dev

# ── 第 5 步：打开浏览器 ──
# http://localhost:5173
```

---

## 3. 详细步骤

### 3.1 克隆项目 / 进入项目目录

```powershell
cd e:\docs-chat
```

### 3.2 安装后端 Python 依赖

```powershell
cd backend
pip install -r requirements.txt
```

**`requirements.txt` 完整内容**：

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-multipart>=0.0.9
langchain>=0.3.0
langchain-community>=0.3.0
langchain-text-splitters>=0.3.0
chromadb>=0.5.0
pypdf>=4.0.0
pdfplumber>=0.10.0
openai>=1.0.0
httpx>=0.27.0
sentence-transformers>=3.0.0
rank-bm25>=0.2.2
python-dotenv>=1.0.0
ragas>=0.2.0
sse-starlette>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**本次实际安装版本**（pip install 自动解析最新兼容版本）：

| 包名 | 安装版本 | 说明 |
|------|---------|------|
| fastapi | 0.127.0 | Web 框架 |
| uvicorn | 0.40.0 | ASGI 服务器 |
| pydantic | 2.12.7 | 数据校验 |
| pydantic-settings | 2.12.0 | 配置管理 |
| python-multipart | 0.0.20 | 文件上传解析 |
| langchain | 1.3.10 | LangChain 框架 |
| langchain-community | 0.4.1 | 社区集成 |
| langchain-text-splitters | 1.1.0 | 文本分块 |
| chromadb | 1.5.9 | 向量数据库 |
| pypdf | 6.6.0 | PDF 解析（兜底） |
| pdfplumber | 0.4.2 | PDF 表格提取 |
| openai | 2.11.0 | OpenAI SDK（兼容 DeepSeek） |
| httpx | 0.28.1 | HTTP 客户端 |
| sentence-transformers | 5.2.0 | 句子嵌入 |
| rank-bm25 | 0.2.2 | BM25 关键词检索 |
| python-dotenv | 1.2.1 | .env 加载 |
| ragas | 0.4.3 | RAG 评估 |
| sse-starlette | 3.1.0 | SSE 支持 |
| pytest | 9.0.2 | 测试框架 |
| pytest-asyncio | 1.3.0 | 异步测试 |

### 3.3 配置环境变量

编辑 `backend/.env`：

```bash
# ═══════════════════════════════════════════════
# DocsChat v3.1 环境配置
# ═══════════════════════════════════════════════

# ── DeepSeek LLM（必需：对话功能依赖此项） ──
DEEPSEEK_API_KEY=sk-your-actual-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=4096
DEEPSEEK_TEMPERATURE=0.7

# ── 文档解析器（默认 pypdf 兜底，无需额外配置） ──
# PARSER_TYPE=mineru  # 切换到 MinerU 时取消注释
# MINERU_URL=http://localhost:8080
PARSER_TYPE=pypdf

# ── Embedding（默认 chromadb_default，384 维） ──
# ENABLE_BGE_M3=true  # 切换到 BGE-M3 时取消注释
# EMBEDDING_PROVIDER=remote
# EMBEDDING_DIM=1024
# EMBEDDING_API_BASE=http://localhost:8001/v1

# ── Reranker（默认无，检索后不做精排） ──
# RERANKER_TYPE=qwen
# RERANKER_API_URL=http://localhost:8002/v1

# ── CRAG 防幻觉 ──
CRAG_ENABLED=true
CRAG_CORRECT_THRESHOLD=0.8
CRAG_INCORRECT_THRESHOLD=0.3
CRAG_RETRY_INCORRECT_RATIO=0.6

# ── 语义缓存 ──
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.92
SEMANTIC_CACHE_TTL_SECONDS=86400

# ── 质量门禁 ──
QG_ENABLED=true
QG_MIN_CHARS=100
QG_MIN_HEADINGS=0
QG_MIN_TABLES=0
QG_MIN_PAGES=1

# ── 在线 RAG ──
RAG_FUSION_VARIANTS=3
RAG_MAX_HISTORY_MESSAGES=6
CHAT_MAX_CONCURRENT_LLM=8
INGESTION_MAX_CONCURRENT_JOBS=2

# ── 安全与限流 ──
AUTH_REQUIRED=false
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW_SECONDS=60

# ── 服务 ──
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
LOG_LEVEL=INFO
```

**关键配置项说明**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEEPSEEK_API_KEY` | 占位符 | **必须替换为真实 Key**，否则对话功能返回 401 |
| `PARSER_TYPE` | `pypdf` | 不设置时默认 PyPDF 兜底，无需 GPU |
| `CRAG_ENABLED` | `true` | 防幻觉评估，依赖 DeepSeek API |
| `SEMANTIC_CACHE_ENABLED` | `true` | 语义缓存，依赖 ChromaDB |
| `QG_ENABLED` | `true` | 质量门禁，字符数不足 100 的文档将被拒绝 |
| `AUTH_REQUIRED` | `false` | 本地开发无需鉴权 |

### 3.4 启动后端

```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**启动日志示例**：

```
INFO:     Started server process [544]
INFO:     Waiting for application startup.
2026-06-20 20:24:04,384 [INFO] app.main: DocsChat 启动中...
2026-06-20 20:24:04,468 [INFO] app.services.retrieval_service: BM25 索引构建完成: 138 个文档
2026-06-20 20:24:04,468 [INFO] app.main: BM25 索引恢复完成: 138 chunks
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**启动时自动完成**：
1. 加载 `.env` 配置
2. 连接 ChromaDB（自动创建 `backend/chroma_data/` 目录）
3. 从已有 Chunks 重建 BM25 关键词索引
4. 初始化 Token Bucket 限流器
5. 注册所有 API 路由

**开发模式**（热重载）：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> ⚠️ 注意：`--reload` 会监控文件变更，任何 `.py` 文件修改都会触发重启。生产环境请勿使用。

### 3.5 启动前端

```powershell
cd frontend
npm install    # 首次运行需要
npm run dev
```

**启动日志示例**：

```
VITE v8.0.16  ready in 5285 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### 3.6 打开浏览器

访问 **http://localhost:5173/**

前端 Vite 开发服务器会自动将 `/api/` 请求代理到后端 `http://localhost:8000/`（配置在 `frontend/vite.config.ts`）。

---

## 4. 端到端验证

### 4.1 运行自动验证脚本

```powershell
cd backend
python scripts/test_e2e.py
```

### 4.2 手动验证步骤

#### 4.2.1 健康检查

```powershell
python -c "import urllib.request, json; r = urllib.request.urlopen('http://127.0.0.1:8000/health'); print(json.loads(r.read()))"
```

**预期输出**：

```json
{"status": "ok", "service": "DocsChat API"}
```

#### 4.2.2 服务诊断

```powershell
python -c "import urllib.request, json; r = urllib.request.urlopen('http://127.0.0.1:8000/health/services'); print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))"
```

**预期输出**（默认 PyPDF 模式）：

```json
{
  "version": "0.1.0",
  "chunk_count": 138,
  "mineru": {
    "parser_type": "pypdf",
    "mineru_url": "http://mineru:8080",
    "mode": "fallback",
    "available": false,
    "status_code": null
  },
  "embedding": {
    "provider": "chromadb_default",
    "model": "all-MiniLM-L6-v2",
    "dim": 384,
    "bge_m3_enabled": false,
    "api_base": "",
    "available": true
  },
  "reranker": {
    "mode": "none",
    "model": "Qwen/Qwen3-Reranker-0.6B",
    "remote_url": "http://localhost:8002/v1",
    "reranker_type": "qwen",
    "local_loaded": false
  },
  "deepseek": {
    "configured": false,
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "available": false
  },
  "quality_gate": {
    "enabled": true,
    "min_chars": 100,
    "min_headings": 0,
    "min_tables": 0,
    "min_pages": 1,
    "available": true
  },
  "all_healthy": false
}
```

> `all_healthy: false` 是正常的 —— 因为 DeepSeek API Key 未配置。配置正确 Key 后此项会变为 `true`。

#### 4.2.3 文档上传（异步）

**Step 1：准备 PDF 文件**

将 PDF 文件放入 `backend/uploads/` 目录，或通过 API 上传。

**Step 2：通过 API 上传**

```python
import http.client
import json
import urllib.request

boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
with open("your_document.pdf", "rb") as f:
    file_content = f.read()

body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="your_document.pdf"\r\n'
    f"Content-Type: application/pdf\r\n\r\n"
).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request("http://127.0.0.1:8000/documents/upload", data=body)
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Job ID: {data['job_id']}, Status: {data['status']}")
```

**预期输出**：

```
Job ID: 7c6dd1ab46da4b018a4b6bfdbb09e497, Status: queued
```

**Step 3：轮询任务状态**

```python
import time, json, urllib.request

job_id = "your-job-id-from-step-2"
while True:
    resp = urllib.request.urlopen(f"http://127.0.0.1:8000/documents/jobs/{job_id}")
    data = json.loads(resp.read())
    print(f"Status: {data['status']}, Pages: {data['page_count']}, Chunks: {data['chunk_count']}")
    if data["status"] in ("ready", "failed"):
        break
    time.sleep(1.5)
```

**预期状态流转**：

```
queued → running → ready     # 成功
queued → running → failed    # 失败（如内容不足、文件损坏）
```

#### 4.2.4 SSE 流式对话

**RAG 模式**（基于已上传文档回答）：

```python
import json, urllib.request

body = json.dumps({
    "conversation_id": "test_001",
    "content": "请总结文档的核心内容"
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8000/chat/stream?rag=true",
    data=body,
    method="POST"
)
req.add_header("Content-Type", "application/json")

resp = urllib.request.urlopen(req, timeout=30)
for line in resp:
    line = line.decode("utf-8").strip()
    if line.startswith("data: "):
        event = json.loads(line[6:])
        if event["event"] == "token":
            print(event["data"], end="", flush=True)
        elif event["event"] == "done":
            print("\n[DONE]")
            break
        elif event["event"] == "error":
            print(f"\n[ERROR] {event['data']}")
            break
```

**SSE 事件类型**：

| event | 含义 | 触发时机 |
|-------|------|----------|
| `cache` | 语义缓存命中 | 相似问题命中缓存时 |
| `source` | 检索来源引用 | 检索完成后 |
| `token` | LLM 生成 token | 逐个 token 推送 |
| `done` | 流结束 | 正常结束 |
| `error` | 错误 | 异常发生时 |

**非 RAG 模式**（直接对话，不检索文档）：

```python
# 将 URL 改为 ?rag=false 即可
req = urllib.request.Request(
    "http://127.0.0.1:8000/chat/stream?rag=false",
    data=body,
    method="POST"
)
```

#### 4.2.5 文档列表

```python
import json, urllib.request
resp = urllib.request.urlopen("http://127.0.0.1:8000/documents/")
data = json.loads(resp.read())
for doc in data:
    print(f"{doc['filename']} ({doc['chunk_count']} chunks)")
```

---

## 5. 常见问题排查

### 5.1 对话返回 401

```
Error code: 401 - Authentication Fails, Your api key: ****here is invalid
```

**原因**：`.env` 中的 `DEEPSEEK_API_KEY` 为占位符。

**解决**：编辑 `backend/.env`，将 `DEEPSEEK_API_KEY` 替换为真实的 DeepSeek API Key。

```bash
# 获取 API Key：https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 5.2 文档上传后状态为 `failed`

**常见原因**：

| 错误信息 | 原因 | 解决 |
|----------|------|------|
| `文档解析完成，但未生成可入库的有效分块` | PDF 内容不足（< 100 字符、< 1 页） | 上传包含有效内容的 PDF |
| `仅支持 PDF 格式` | 上传了非 PDF 文件 | 转换为 PDF 后上传 |
| `保存上传文件失败` | uploads 目录权限不足 | 检查 `backend/uploads/` 目录权限 |

### 5.3 端口被占用

```
OSError: [WinError 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次
```

**解决**：

```powershell
# 查找占用 8000 端口的进程
netstat -ano | findstr :8000

# 终止进程（将 PID 替换为实际值）
taskkill /PID 12345 /F
```

### 5.4 ChromaDB 维度不匹配

```
chromadb.errors.InvalidDimensionException: Expected dimensionality 384, got 1024
```

**原因**：切换了 Embedding 模型（如从 MiniLM 384 维切换到 BGE-M3 1024 维），但未清理旧数据。

**解决**：

```powershell
# 删除旧 ChromaDB 数据
Remove-Item -Recurse -Force backend\chroma_data\

# 重新上传所有文档
```

### 5.5 前端无法连接后端

**检查清单**：

1. 后端是否已启动：访问 `http://127.0.0.1:8000/health`
2. 前端代理配置：`vite.config.ts` 中 `proxy` 指向 `http://localhost:8000`
3. CORS 配置：`.env` 中 `CORS_ORIGINS` 是否包含 `http://localhost:5173`
4. 防火墙：是否阻止了 8000 端口

### 5.6 pip install 权限错误

```
[WinError 5] 拒绝访问: 'C:\\Users\\xxx\\AppData\\Roaming\\Python'
```

**解决**：

```powershell
# 方案 A：使用 --user 安装
pip install --user -r requirements.txt

# 方案 B：以管理员身份运行终端
# 右键 PowerShell → 以管理员身份运行
```

---

## 6. 本次运行实测记录

### 6.1 测试环境

| 项目 | 值 |
|------|-----|
| 时间 | 2026-06-20 20:24 |
| 操作系统 | Windows 11 |
| Python | 3.13.5 |
| Node.js | 24.11.1 |
| npm | 11.6.2 |
| 后端 | FastAPI 0.127.0 + Uvicorn 0.40.0 |
| 前端 | Vite 8.0.16 + Vue 3 |

### 6.2 测试结果

| 测试项 | 状态 | 详情 |
|--------|------|------|
| 后端启动 | ✅ 通过 | 启动耗时 < 1s，138 chunks 恢复 + BM25 索引构建 |
| 健康检查 `GET /health` | ✅ 通过 | 200 OK |
| 服务诊断 `GET /health/services` | ⚠️ 部分通过 | MinerU/DeepSeek 未配置（预期），Embedding/QualityGate 正常 |
| 系统状态 `GET /documents/status` | ✅ 通过 | chunk_count=138, has_bm25_index=True |
| 异步上传 `POST /documents/upload` | ✅ 通过 | queued→running→failed（测试 PDF 内容不足，质量门禁正确拒绝） |
| 轮询 `GET /documents/jobs/{id}` | ✅ 通过 | 状态流转正常 |
| 文档列表 `GET /documents/` | ✅ 通过 | 返回已入库文档 |
| SSE 对话 `POST /chat/stream` | ⚠️ 需配置 | 返回 401（DeepSeek API Key 未配置） |
| 前端 Vite 开发服务器 | ✅ 通过 | http://localhost:5173/ 可访问 |

### 6.3 当前系统状态

```
┌─────────────────────────────────────────────────────┐
│  DocsChat v3.1 运行状态                              │
├─────────────────────────────────────────────────────┤
│  后端:  http://127.0.0.1:8000    ✅ Running          │
│  前端:  http://localhost:5173    ✅ Running          │
│  解析器: PyPDF (fallback)        ✅ Ready            │
│  向量库: ChromaDB (384d)         ✅ 138 chunks       │
│  BM25:   NLTK 关键词索引         ✅ 138 docs         │
│  缓存:   语义相似度缓存           ✅ Enabled          │
│  CRAG:   防幻觉评估              ✅ Enabled          │
│  限流:   Token Bucket 20req/60s  ✅ Active           │
│  ─────────────────────────────────────────────────  │
│  ⚠️  DeepSeek API Key: 未配置    ⚠️ 对话不可用       │
│  ⚠️  MinerU:            未配置    ⚠️ 使用 PyPDF 兜底 │
│  ⚠️  BGE-M3:            未配置    ⚠️ 使用 MiniLM 384d│
│  ⚠️  Reranker:          未配置    ⚠️ 无精排         │
└─────────────────────────────────────────────────────┘
```

### 6.4 下一步：激活完整功能

如需激活完整 v3.1 功能栈，按以下顺序配置：

```powershell
# 1. 配置 DeepSeek API Key（必需）
#    编辑 backend/.env，填入真实 API Key

# 2. （可选）配置 MinerU 3.3 GPU 文档解析
#    docker compose -f docker-compose.mineru.yml up -d
#    编辑 backend/.env：PARSER_TYPE=mineru

# 3. （可选）配置 BGE-M3 1024 维 Embedding
#    编辑 backend/.env：ENABLE_BGE_M3=true
#    ⚠️ 然后删除旧 ChromaDB 数据并重新上传文档

# 4. （可选）配置 Qwen3-Reranker
#    编辑 backend/.env：RERANKER_TYPE=qwen
```

---

## 附录：项目文件结构

```
e:\docs-chat\
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口，启动生命周期
│   │   ├── api/
│   │   │   ├── documents.py     # 文档上传/轮询/列表 API
│   │   │   └── chat.py          # SSE 流式对话 API
│   │   ├── core/
│   │   │   └── config.py        # pydantic-settings 配置
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic 数据模型
│   │   └── services/
│   │       ├── rag_orchestrator.py    # RAG 编排核心
│   │       ├── semantic_cache.py      # 语义缓存
│   │       ├── crag_service.py        # CRAG 防幻觉
│   │       ├── query_rewriter.py      # 查询改写
│   │       ├── retrieval_service.py   # 向量+BM25 混合检索
│   │       ├── reranker_service.py    # 重排序
│   │       ├── llm_service.py         # DeepSeek API 封装
│   │       ├── mineru_document_service.py  # MinerU 适配器
│   │       ├── vector_store.py        # ChromaDB 向量存储
│   │       ├── ingestion_service.py   # 异步摄取管道
│   │       ├── quality_gate.py        # 质量门禁
│   │       └── security_service.py    # 限流+鉴权
│   ├── scripts/
│   │   └── test_e2e.py          # 端到端验证脚本
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.ts
│   │   ├── views/
│   │   │   └── ChatView.vue     # 主对话页面
│   │   ├── components/
│   │   │   └── DocumentUploader.vue  # 文件上传组件
│   │   ├── composables/
│   │   │   └── useSSE.ts        # SSE 客户端封装
│   │   ├── utils/
│   │   │   └── api.ts           # API 封装
│   │   └── types/
│   │       └── index.ts         # TypeScript 类型定义
│   ├── vite.config.ts
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── V3.1_UPGRADE_SOP.md      # 生产级重构操作手册
│   └── RUN_GUIDE.md             # 本文档：完整运行指南
├── docker-compose.yml
└── docs-chat-rag-upgrade.md
```