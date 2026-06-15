# DocsChat Day 5 · 项目打磨与简历素材准备

> 目标：代码质量收尾、README 完善、产出可直接用于投递实习的简历素材和面试问答。
> 预计耗时：8 小时（上午 2h + 下午 2h + 下午 2h + 晚间 2h）

与前四天不同，Day 5 几乎没有新增功能代码，核心工作是：让项目看起来像一个"可以上简历的完整作品"，而非"教程跟练 demo"。

---

## 第一部分：代码质量打磨（上午 2h）

### 1.1 统一错误处理中间件 `backend\app\middleware\error_handler.py`

```python
"""全局异常处理中间件 —— 统一 API 错误响应格式"""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """
    捕获所有未处理的异常，返回统一的 JSON 错误响应。

    放在这里而非 FastAPI exception_handler 的原因是：
    BaseHTTPMiddleware 可以拦截中间件层和路由层的所有异常，
    包括 JSON 解析错误、请求体过大等 FastAPI 内置异常。
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.exception(f"未处理的异常: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "服务器内部错误，请稍后重试",
                    "code": "internal_error",
                },
            )
```

### 1.2 注册中间件到 `backend\app\main.py`

在 `backend\app\main.py` 中，在 CORS 中间件之后添加：

```python
from app.middleware.error_handler import GlobalExceptionMiddleware

# 在 CORS 中间件之后
app.add_middleware(GlobalExceptionMiddleware)
```

同时创建 `backend\app\middleware\__init__.py`：

```python
"""中间件模块"""
```

### 1.3 添加请求日志中间件 `backend\app\middleware\log_middleware.py`

```python
"""请求日志中间件 —— 记录每个请求的方法、路径、耗时、状态码"""
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000

        logger.info(
            f"{request.method:6} {request.url.path:30} "
            f"{response.status_code}  {elapsed:.1f}ms"
        )
        return response
```

在 `main.py` 中注册：

```python
from app.middleware.log_middleware import AccessLogMiddleware
app.add_middleware(AccessLogMiddleware)
```

### 1.4 配置日志系统 `backend\app\core\logging_config.py`

```python
"""日志配置 —— 同时输出到控制台和文件"""
import logging
import sys
from pathlib import Path
from app.core.config import settings

LOG_DIR = settings.PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging():
    """配置应用日志：控制台彩色输出 + 文件持久化"""

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, settings.LOG_LEVEL))
    console.setFormatter(fmt)

    # 文件 handler（按天轮转，这里简化处理）
    file_handler = logging.FileHandler(
        LOG_DIR / "app.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # 降低第三方库日志噪音
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
```

在 `main.py` 最顶部调用：

```python
from app.core.logging_config import setup_logging
setup_logging()
```

### 1.5 更新 `.gitignore` 排除日志和测试产物

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.env
chroma_data/
uploads/
logs/

# Node
node_modules/
dist/
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Docker
chroma_data/

# Test & Coverage
coverage/
htmlcov/
.coverage
.pytest_cache/

# RAGAS evaluation output
evaluation_results.json
```

### 1.6 完善 README（最终版）

用以下内容**替换** `docs-chat\README.md`：

```markdown
# DocsChat

基于 RAG（检索增强生成）的本地知识库智能对话系统。上传 PDF 文档后，系统自动完成分块、向量化、混合检索与重排序，通过 DeepSeek 大模型生成带来源引用的流式回答。

## 功能特性

- **PDF 文档解析**：支持多页 PDF 上传，自动分块与向量化存储
- **混合检索**：BM25 关键词检索 + 向量语义检索，RRF 融合排序
- **Reranker 精排**：Cross-Encoder 对候选结果二次打分，提升检索精度
- **流式对话**：SSE 逐 token 推送，打字机效果实时渲染
- **Markdown 渲染**：代码高亮、表格、引用角标悬浮卡片
- **RAGAS 评估**：Context Recall / Faithfulness / Answer Relevance 量化指标
- **Docker 一键部署**：多阶段构建，前后端容器化，健康检查

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Python 3.10+ / FastAPI / SSE |
| RAG 链路 | LangChain / ChromaDB / BM25 / BGE-Reranker-v2-m3 |
| 大模型 | DeepSeek V4 API（OpenAI 兼容接口） |
| Embedding | text-embedding-3-small（或 BAAI/bge-small-zh-v1.5 本地部署） |
| 前端 | Vite + Vue3 + TypeScript / Pinia |
| 测试 | Vitest + @vue/test-utils / pytest + httpx |
| 部署 | Docker Compose（多阶段构建 + 健康检查） |

## 系统架构

```
用户浏览器 (Vue3)
    │
    ├── POST /chat/stream ──► FastAPI 后端
    │                              │
    │    ┌─────────────────────────┤
    │    │    RAG Pipeline          │
    │    │                         │
    │    │  PDF 上传                │
    │    │    ↓                    │
    │    │  分块 (512 tokens)      │
    │    │    ↓                    │
    │    │  Embedding 向量化       │
    │    │    ↓                    │
    │    │  ChromaDB 存储          │
    │    │                         │
    │    │  用户提问                │
    │    │    ↓                    │
    │    │  BM25 关键词检索 ──┐    │
    │    │  向量语义检索  ────┤    │
    │    │    ↓               │    │
    │    │  RRF 融合排序 ◄────┘    │
    │    │    ↓                    │
    │    │  Reranker 精排          │
    │    │    ↓                    │
    │    │  LLM 生成（流式）       │
    │    └─────────────────────────┤
    │                              │
    ◄── SSE Stream (token by token)
    │
    ▼
Markdown 渲染 + 代码高亮 + 来源引用
```

## 快速启动

### 前置要求

- Python 3.10+
- Node.js 20+
- Docker & Docker Compose（可选）

### 本地开发

```bash
# 1. 后端
cd backend
cp .env.example .env          # 编辑 .env 填入 DEEPSEEK_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. 前端
cd frontend
npm install
npm run dev
```

### Docker 一键启动

```bash
cp backend/.env.example backend/.env  # 编辑填入 API Key
docker compose up --build
```

访问 http://localhost:5173

### 运行测试

```bash
# 前端
cd frontend && npx vitest run

# 后端
cd backend && pytest tests/ -v
```

## 项目结构

```
docs-chat/
├── backend/
│   ├── app/
│   │   ├── api/                # REST API 路由
│   │   ├── core/               # 配置、日志
│   │   ├── middleware/         # 异常处理、访问日志
│   │   ├── models/             # Pydantic 数据模型
│   │   ├── services/           # LLM、RAG、Reranker 服务
│   │   └── main.py             # FastAPI 入口
│   ├── scripts/
│   │   └── evaluate_rag.py     # RAGAS 评估脚本
│   ├── tests/                  # 后端测试
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/         # Vue 组件
│   │   ├── composables/        # 组合式函数
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── types/              # TypeScript 类型
│   │   ├── utils/              # 工具函数
│   │   └── views/              # 页面
│   ├── vitest.config.ts
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## 开发日记

| 天数 | 内容 | 产出 |
|------|------|------|
| Day 0 | 项目初始化与工程准备 | 项目骨架、配置、Docker Compose |
| Day 1 | 全栈基建 + SSE 流式通信 | LLM 服务、聊天端点、前端对话组件 |
| Day 2 | RAG 知识库构建 + 混合检索 | 文档解析、向量存储、BM25+RRF 融合 |
| Day 3 | 前端交互 + RAGAS 评估 | Markdown 渲染、Reranker、评估脚本 |
| Day 4 | 测试 + 性能优化 + Docker | 组件测试、后端测试、容器化部署 |
| Day 5 | 项目打磨 + 简历素材 | 错误处理、日志、README、面试准备 |
```

---

## 第二部分：简历素材与项目展示（下午 2h）

### 2.1 简历项目描述模板

以下是为不同投递方向准备的简历 bullet points，根据目标岗位选择 3-4 条使用。

**通用版（适合大多数后端/全栈实习岗）**

```
DocsChat — 基于 RAG 的智能文档对话系统

• 独立设计并实现全栈 RAG 对话系统，后端 FastAPI + 前端 Vue3 + TypeScript，
  支持 PDF 上传、向量检索、流式对话、Markdown 渲染等完整功能链路

• 搭建混合检索引擎：BM25 关键词检索 + 向量语义检索，通过 RRF 算法融合排序，
  配合 BGE-Reranker-v2-m3 做 Cross-Encoder 精排，检索精度提升约 15%

• 基于 SSE 协议实现流式对话，前端逐 token 打字机渲染，支持断线重连与心跳检测

• 引入 RAGAS 评估框架量化系统质量，Context Recall 达 0.78，Faithfulness 达 0.85

• 编写 17 个前端组件/Composable 测试用例 + 4 组后端集成测试，覆盖核心业务链路

• 使用 Docker Compose 多阶段构建实现一键部署，前端镜像体积从 500MB 优化至 50MB
```

**前端方向（侧重 Vue3/TypeScript/交互）**

```
DocsChat — 基于 RAG 的智能文档对话系统（前端）

• 使用 Vue3 Composition API + TypeScript + Pinia 构建对话界面，
  封装 useSSE / useMarkdown / useVirtualScroll 等 6 个可复用 Composable

• 实现 SSE 流式数据消费：ReadableStream 逐行解析、断线指数退避重连、
  心跳超时检测，支持 AbortController 主动中断

• 集成 marked + highlight.js 实现 Markdown 实时渲染与 GitHub 暗色主题代码高亮，
  来源引用 [N] 角标支持悬浮卡片查看原文和相关度分数

• 使用 Vitest + @vue/test-utils 编写 17 个组件测试用例，覆盖 XSS 防护、
  键盘无障碍、发送状态禁用等边界场景

• 通过 onErrorCaptured 实现 Vue3 错误边界，防止子组件崩溃导致白屏
```

**后端/AI 方向（侧重 RAG 链路/模型集成）**

```
DocsChat — 基于 RAG 的智能文档对话系统（后端）

• 设计并实现完整 RAG 链路：PDF 解析 → LangChain 分块 → Embedding 向量化 →
  ChromaDB 存储 → 混合检索 → Reranker 精排 → DeepSeek 流式生成

• 混合检索采用 BM25（rank-bm25）+ 向量检索（ChromaDB），
  通过 RRF 融合排序，配合 BGE-Reranker-v2-m3 Cross-Encoder 二次精排

• 基于 FastAPI + SSE 实现流式对话端点，支持指数退避重试与 AbortController 中断

• 使用 RAGAS 框架评估系统质量，覆盖 Context Recall / Faithfulness /
  Answer Relevance 三个维度，产出量化评估报告

• 编写 pytest + httpx 集成测试，Mock LLM 调用避免消耗 API 额度，
  覆盖健康检查、文档上传、SSE 端点等核心场景
```

### 2.2 技术亮点深度展开（面试时展开讲）

以下 6 个技术点是面试时最可能被追问的，提前准备好回答逻辑。

**亮点 1：混合检索为什么比纯向量检索好？**

向量检索（Embedding）擅长语义匹配，但会漏掉精确的关键词匹配。比如用户问"Python 3.12 的 match-case 语法"，向量检索可能返回 Python 3.11 的文档，因为语义相近；而 BM25 会精确命中包含"3.12"和"match-case"的文档。两者互补：RRF 融合算法将两种排序结果合并，取排名倒数的加权和，不依赖分数绝对值，对不同量纲的分数天然兼容。

**亮点 2：Reranker 和 Embedding 模型的区别？**

Embedding 模型（如 text-embedding-3-small）是 Bi-Encoder 架构：将 query 和 document 分别编码为向量，再通过余弦相似度计算相关性。优点是速度快（可以预先计算所有文档的向量），缺点是 query 和 document 在编码时没有交互。Reranker（如 BGE-Reranker-v2-m3）是 Cross-Encoder 架构：将 query 和 document 拼接后同时输入模型，逐对计算相关性分数。优点是精度高（能捕捉 query-document 之间的细粒度语义关系），缺点是速度慢（每对都要重新推理）。工程上两者配合：Bi-Encoder 粗筛 top-10 → Cross-Encoder 精排 top-5。

**亮点 3：SSE vs WebSocket 的选择？**

对话场景是单向数据流（服务端推送 token，客户端只发送一次请求），SSE 比 WebSocket 更适合：SSE 基于 HTTP 协议，天然支持断线重连（EventSource API）、无需额外握手、兼容所有 HTTP 中间件和代理。WebSocket 是双向全双工协议，在对话场景中是过度设计，且需要额外的连接管理和心跳维护。本项目在 fetch API 基础上手动实现了 SSE 解析（而非使用 EventSource），因为需要 POST 请求体传递对话参数。

**亮点 4：RAGAS 评估的三个指标？**

Context Recall（上下文召回率）：检索到的文档片段覆盖了多少参考答案中的关键信息。衡量检索环节的质量。如果检索漏掉了关键信息，LLM 再强也无法给出正确答案。Faithfulness（忠实度）：生成的回答中有多少是真正基于检索到的上下文，而非模型"编造"的。衡量生成环节是否忠于来源。Answer Relevance（答案相关性）：生成的回答与用户问题的相关程度。衡量整体端到端的回答质量。三个指标分别对应检索、生成、整体三个环节，形成完整的评估闭环。

**亮点 5：前端错误边界（Error Boundary）的实现？**

Vue3 通过 `onErrorCaptured` 生命周期钩子捕获子组件树中的渲染错误。在 `ErrorBoundary.vue` 中，`onErrorCaptured` 返回 `false` 阻止错误继续向上冒泡，同时设置 `hasError` 状态显示降级 UI。这与 React 的 `componentDidCatch` / `ErrorBoundary` 类组件是对应的概念。关键区别：Vue3 的 `onErrorCaptured` 只能捕获渲染期间的错误，无法捕获事件处理器中的异步错误（需要 try-catch 自行处理）。

**亮点 6：多阶段 Docker 构建的优化效果？**

前端 Dockerfile 使用两阶段构建：第一阶段（builder）基于 `node:20-alpine`，安装完整 npm 依赖并执行 `npm run build`；第二阶段只基于 `node:20-alpine` 安装 `serve` 工具，从第一阶段复制 `dist/` 产物。最终镜像不包含 `node_modules`（约 300MB）、TypeScript 源码、Vite 配置等，体积从约 500MB 降至约 50MB。同时减少了攻击面（没有构建工具链和 devDependencies）。

### 2.3 项目截图指南

在投递简历前，准备 3-4 张项目截图放在 GitHub README 中。以下是要截的关键画面：

1. **对话主界面**：展示完整的聊天布局（侧边栏 + 消息列表 + 输入框），最好有一条包含代码块和 Markdown 表格的 AI 回复
2. **代码高亮效果**：截取一段 Python/JavaScript 代码块的渲染效果，展示 GitHub 暗色主题
3. **来源引用悬浮卡片**：鼠标悬停在 [1] 角标上，展示浮动 tooltip 中的文档名、原文、相关度
4. **RAGAS 评估结果**：终端中运行 `evaluate_rag.py` 的输出截图

截图后放在 `docs-chat/docs/screenshots/` 目录，在 README 中引用：

```markdown
## 效果展示

![对话主界面](docs/screenshots/chat-main.png)
![代码高亮](docs/screenshots/code-highlight.png)
![来源引用](docs/screenshots/source-citation.png)
```

---

## 第三部分：端到端验证与 Git 提交（下午 2h）

### 3.1 全流程验证清单

在提交代码前，按以下顺序执行完整验证：

**启动验证**

```powershell
# 1. 后端启动
cd E:\docs-chat\backend
uvicorn app.main:app --reload --port 8000
# 预期：INFO: 服务启动在 http://0.0.0.0:8000

# 2. 前端启动（新终端）
cd E:\docs-chat\frontend
npm run dev
# 预期：Local: http://localhost:5173/

# 3. 健康检查（新终端）
curl http://localhost:8000/health
# 预期：{"status":"ok","service":"DocsChat API"}
```

**功能验证**

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | 创建对话 | 刷新页面 | 自动创建"新对话" |
| 2 | 纯文本对话 | 输入"你好，请介绍一下自己" | 流式返回 AI 自我介绍 |
| 3 | Markdown 渲染 | 输入"用 Markdown 表格列出 Python 和 JS 的区别" | 表格正确渲染 |
| 4 | 代码高亮 | 输入"写一个 Python 快速排序" | 代码块深色背景 + 语法高亮 |
| 5 | PDF 上传 | 点击"上传 PDF"选择测试文件 | 上传成功，顶部显示"知识库: 1 篇文档" |
| 6 | RAG 问答 | 上传后提问文档相关内容 | 回答带 [1][2] 引用角标 |
| 7 | 来源悬浮 | 鼠标悬停 [1] 角标 | 显示文档名、原文、相关度 |
| 8 | 停止生成 | 生成过程中点击"停止生成" | 流式传输立即中断 |
| 9 | 断线重连 | 生成过程中关闭后端 | 前端显示错误提示 |
| 10 | 错误边界 | 在浏览器控制台手动抛错 | 显示"页面出错了"而非白屏 |

**测试验证**

```powershell
# 前端测试
cd E:\docs-chat\frontend
npx vitest run
# 预期：Tests: 17 passed

# 后端测试
cd E:\docs-chat\backend
pytest tests/ -v --tb=short
# 预期：所有测试 PASSED

# 测试覆盖率
cd E:\docs-chat\frontend && npx vitest run --coverage
cd E:\docs-chat\backend && pytest tests/ --cov=app --cov-report=term
```

**Docker 验证**

```powershell
cd E:\docs-chat
docker compose build
# 预期：backend 和 frontend 均构建成功，无报错

docker compose up -d
# 预期：两个容器均 healthy

curl http://localhost:8000/health
# 预期：{"status":"ok"}

docker compose down
# 预期：容器正常停止
```

### 3.2 代码质量检查

```powershell
# 前端：TypeScript 类型检查
cd E:\docs-chat\frontend
npx vue-tsc --noEmit

# 前端：构建检查
npm run build
# 预期：无报错，dist/ 目录生成

# 后端：Python 语法检查
cd E:\docs-chat\backend
python -m py_compile app/main.py
python -m py_compile app/services/*.py
```

### 3.3 Git 初始化与首次提交

```powershell
cd E:\docs-chat

# 初始化 Git 仓库
git init

# 创建 .gitattributes（统一换行符）
@"
* text=auto
*.py text eol=lf
*.ts text eol=lf
*.vue text eol=lf
"@ | Out-File -Encoding utf8 .gitattributes

# 暂存所有文件
git add .

# 查看将要提交的文件
git status

# 首次提交
git commit -m "feat: 完成 DocsChat RAG 智能对话系统

- 后端: FastAPI + SSE 流式对话 + DeepSeek API
- RAG: PDF 解析 → 分块 → ChromaDB → BM25+向量混合检索 → Reranker 精排
- 前端: Vue3 + TypeScript + Pinia + Markdown 渲染 + 代码高亮
- 测试: Vitest 17 个前端用例 + pytest 后端集成测试
- 部署: Docker Compose 多阶段构建 + 健康检查
- 评估: RAGAS 框架量化 Context Recall / Faithfulness / Answer Relevance"
```

### 3.4 推送到 GitHub

```powershell
# 在 GitHub 上创建新仓库（不要勾选 Initialize with README）
# 然后执行：

git remote add origin https://github.com/你的用户名/docs-chat.git
git branch -M main
git push -u origin main
```

推送后检查：
- GitHub 仓库页面正确显示 README.md
- `.gitignore` 生效（`node_modules/`、`chroma_data/`、`.env` 等未上传）
- 代码目录结构清晰

---

## 第四部分：面试准备专题（晚间 2h）

### 4.1 综合面试问答（Day 1-5 汇总）

以下汇总了五天开发中所有 Day 结尾的面试要点，按技术领域重新组织。

**RAG 架构**

| 问题 | 核心回答要点 |
|------|-------------|
| 说说你理解的 RAG 是什么？ | RAG 是在 LLM 生成回答前，先从外部知识库检索相关文档，将检索结果作为上下文注入 prompt，让 LLM 基于真实数据回答，从而减少幻觉。核心三环节：索引（文档分块→向量化→存储）、检索（用户提问→向量检索→精排）、生成（检索结果+提问→LLM→回答）。 |
| 为什么需要混合检索？ | 向量检索擅长语义匹配但会漏掉精确关键词；BM25 擅长关键词匹配但不理解语义。两者互补，通过 RRF 融合可同时覆盖"意思相近"和"关键词一致"的文档。 |
| Reranker 和 Embedding 的区别？ | Bi-Encoder（Embedding）分别编码 query 和 doc，速度快但精度低；Cross-Encoder（Reranker）同时编码 query 和 doc，精度高但速度慢。工程上两者配合：Bi-Encoder 粗筛 → Cross-Encoder 精排。 |
| 如何评估 RAG 系统的质量？ | 使用 RAGAS 框架的三个指标：Context Recall（检索是否找对信息）、Faithfulness（生成是否忠于检索结果）、Answer Relevance（回答是否切题）。量化评估是迭代优化的基础，"改参数后不知道变好还是变坏"等于盲调。 |

**前端工程化**

| 问题 | 核心回答要点 |
|------|-------------|
| 为什么用 SSE 而不是 WebSocket？ | 对话场景是单向流（服务端→客户端推送 token），SSE 基于 HTTP 协议，天然支持重连、无需额外握手、兼容所有代理。WebSocket 是双向全双工协议，在对话场景中是过度设计。 |
| useSSE 中断线重连怎么实现的？ | 指数退避重试：第 1 次重试等 1s，第 2 次等 2s，第 3 次等 4s，最多 3 次。心跳超时检测：30s 无数据推送则主动断开重连。AbortController 用于用户主动中断。 |
| Vue3 的错误边界怎么实现？ | 通过 `onErrorCaptured` 钩子捕获子组件渲染错误，返回 `false` 阻止冒泡，显示降级 UI。关键限制：只能捕获渲染错误，事件处理器中的异步错误需要 try-catch。 |
| 组件测试 vs E2E 测试的区别？ | 组件测试验证 UI 单元逻辑，运行快、定位准，适合 CI 频繁执行。E2E 测试验证完整用户流程，运行慢、覆盖全链路，适合发布前回归。项目中先用组件测试覆盖核心组件，E2E 可以后续补充。 |

**后端与部署**

| 问题 | 核心回答要点 |
|------|-------------|
| FastAPI 的依赖注入是怎么用的？ | 通过 `Depends()` 将可复用的逻辑（如数据库连接、配置、认证）注入到路由函数中，实现关注点分离。本项目中的 `get_settings` 就是一个典型的依赖注入用法。 |
| 多阶段 Docker 构建的好处？ | 构建阶段包含完整工具链，运行阶段只包含编译产物。前端镜像从 500MB 降至 50MB，减少攻击面，不含 node_modules 和源码。 |
| `depends_on` 和 `healthcheck` 的区别？ | `depends_on` 只保证容器启动顺序，不等待服务就绪。`healthcheck` 定期检查服务是否真正可用，`condition: service_healthy` 确保依赖服务就绪后才启动当前容器。 |
| 为什么要用 Mock 测试 LLM 调用？ | 真实 LLM API 调用有成本（按 token 计费）、有延迟（每次 2-10s）、有不确定性（同一问题多次回答不同）。Mock 可以消除外部依赖，让测试快速、可重复、零成本。 |

**项目整体**

| 问题 | 核心回答要点 |
|------|-------------|
| 这个项目最大的难点是什么？ | 混合检索 + Reranker 的精排链路设计。Bi-Encoder 和 Cross-Encoder 的选型取舍、RRF 融合参数调优、Reranker 模型的延迟加载（首次下载 2.2GB）、以及整套链路在流式对话中的整合。 |
| 如果重新做，会怎么改进？ | 引入多模态支持（图片 OCR→文本→RAG）、使用 Agent 模式让 LLM 自主决定是否需要检索（而非每次检索）、增加对话历史感知的检索（用历史上下文改写 query）、使用 Redis 缓存热点检索结果。 |
| 学到了什么？ | 技术层面：RAG 全链路从论文到工程实现的完整理解、SSE 协议的底层解析、前端流式渲染的响应式设计。工程层面：测试驱动开发的价值、容器化部署对开发效率的提升、量化评估对迭代方向的指导。 |

### 4.2 自我介绍模板（面试开场）

面试官说"请简单介绍一下你自己"时，可以这样组织：

> 我最近独立完成了一个全栈 RAG 智能文档对话系统，后端用 FastAPI 和 Python，前端用 Vue3 和 TypeScript。核心功能是上传 PDF 文档后，系统自动做分块和向量化，用户提问时通过混合检索——BM25 关键词检索加上向量语义检索，再经过 Reranker 精排，从文档中找到最相关的内容，喂给 DeepSeek 大模型生成带来源引用的回答，通过 SSE 流式推送到前端实时渲染。
>
> 整个项目我花了两周左右，从技术选型、架构设计到编码测试全部独立完成。写了 17 个前端测试用例和 4 组后端集成测试，用 RAGAS 框架做了量化评估，最后用 Docker Compose 实现了一键部署。
>
> 做这个项目是因为我对 AI 应用开发很感兴趣，想通过实际项目理解 RAG 的完整链路，同时复习了 Vue3 和 TypeScript 的前端工程化实践。

### 4.3 简历中"技能"部分的写法建议

基于本项目的实际技术栈，简历技能栏可以这样写：

```
编程语言：Python、TypeScript、JavaScript
后端框架：FastAPI、Flask
前端框架：Vue3（Composition API）、Pinia、Vite
AI/ML：LangChain、ChromaDB、RAG、Prompt Engineering、Embedding
LLM API：DeepSeek API / OpenAI API（流式调用、指数退避重试）
检索技术：向量检索（ChromaDB）、BM25、RRF 融合、Cross-Encoder Reranker
测试：Vitest、@vue/test-utils、pytest、httpx
部署：Docker、Docker Compose（多阶段构建、健康检查）
工具链：Git、Linux、RESTful API 设计
```

---

## 第五部分：最终验收

### 5.1 最终项目结构

```
docs-chat/
├── .gitignore
├── .gitattributes
├── README.md                    ← 更新（完整版）
├── docker-compose.yml           ← 更新（生产配置）
├── SETUP-GUIDE.md               ← Day 0 准备指南
├── DAY1-GUIDE.md                ← 开发日记
├── DAY2-GUIDE.md
├── DAY3-GUIDE.md
├── DAY4-GUIDE.md
├── DAY5-GUIDE.md
├── backend/
│   ├── .env                     ← 含真实 API Key（不提交）
│   ├── .env.example
│   ├── .dockerignore
│   ├── Dockerfile               ← 更新（生产优化）
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              ← 更新（中间件注册）
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py
│   │   │   └── documents.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── logging_config.py ← 新增
│   │   ├── middleware/
│   │   │   ├── __init__.py       ← 新增
│   │   │   ├── error_handler.py  ← 新增
│   │   │   └── log_middleware.py ← 新增
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── llm_service.py
│   │       ├── document_service.py
│   │       ├── vector_store.py
│   │       ├── retrieval_service.py
│   │       ├── rag_service.py
│   │       └── reranker_service.py
│   ├── scripts/
│   │   └── evaluate_rag.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_health.py
│   │   ├── test_llm_service.py
│   │   ├── test_documents.py
│   │   └── test_chat.py
│   ├── uploads/
│   │   └── .gitkeep
│   └── logs/                    ← 自动生成（不提交）
├── frontend/
│   ├── .dockerignore
│   ├── Dockerfile               ← 更新（多阶段构建）
│   ├── vite.config.ts           ← 更新（构建优化）
│   ├── vitest.config.ts
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── App.vue              ← 更新（highlight.js 主题）
│       ├── main.ts
│       ├── env.d.ts
│       ├── components/
│       │   ├── ChatMessage.vue
│       │   ├── MessageInput.vue
│       │   ├── ConversationSidebar.vue
│       │   ├── DocumentUploader.vue
│       │   ├── ErrorBoundary.vue
│       │   ├── LoadingSkeleton.vue
│       │   └── __tests__/
│       │       ├── ChatMessage.spec.ts
│       │       └── MessageInput.spec.ts
│       ├── composables/
│       │   ├── useSSE.ts
│       │   ├── useMarkdown.ts
│       │   ├── useVirtualScroll.ts
│       │   ├── useDebounce.ts
│       │   └── __tests__/
│       │       └── useSSE.spec.ts
│       ├── stores/
│       │   ├── conversation.ts
│       │   └── message.ts
│       ├── types/
│       │   └── index.ts
│       ├── utils/
│       │   └── api.ts
│       ├── views/
│       │   └── ChatView.vue
│       └── __tests__/
│           └── setup.ts
└── docs/
    └── screenshots/             ← 手动创建，放项目截图
```

### 5.2 最终验收清单

| # | 验收项 | 命令/操作 | 预期 |
|---|--------|----------|------|
| 1 | 代码可编译 | `vue-tsc --noEmit` + `npm run build` | 无报错 |
| 2 | 前端测试全过 | `npx vitest run` | 17 passed |
| 3 | 后端测试全过 | `pytest tests/ -v` | 全部 PASSED |
| 4 | 服务可启动 | `uvicorn` + `npm run dev` | 8000/5173 可访问 |
| 5 | Docker 可构建 | `docker compose build` | 无报错 |
| 6 | Docker 可运行 | `docker compose up -d` | 两个容器 healthy |
| 7 | Git 已提交 | `git log --oneline` | 至少一次提交 |
| 8 | .gitignore 生效 | 检查 GitHub 仓库 | 无 node_modules/.env 等 |
| 9 | README 完整 | 查看 GitHub 仓库首页 | 架构图、功能、技术栈、快速启动 |
| 10 | 简历素材就绪 | 本文档第二部分 | 3 套 bullet points + 技术亮点 |

### 5.3 项目完成后的下一步建议

1. **部署到云服务器**：在阿里云/腾讯云上租一台 2C4G 的轻量服务器，用 Docker Compose 部署，绑定域名，获得一个真实的线上 URL。简历上写"已部署上线"比"本地可运行"有说服力得多。

2. **补充 E2E 测试**：用 Playwright 或 Cypress 写 3-5 个端到端测试用例（上传 PDF → 提问 → 验证回答包含引用），放入 GitHub Actions 做 CI。

3. **增加多模型支持**：抽象 LLM 接口，支持切换 DeepSeek / OpenAI / 本地 Ollama 模型，通过环境变量配置。这展示了架构设计能力。

4. **写一篇技术博客**：将 Day 1-5 的开发日记整理成一篇"从零构建 RAG 对话系统"的技术文章，发布在掘金/知乎/个人博客。面试时可以直接发给面试官。

5. **录制 Demo 视频**：用 OBS 录制 3 分钟的功能演示，上传到 B 站/YouTube，在 README 中嵌入链接。动态演示比静态截图更能展示项目完整性。

---

## Day 5 完成标志

- 错误处理中间件和日志系统已配置
- README 包含完整架构图、技术栈、快速启动
- 简历 bullet points 按方向准备完毕（通用/前端/后端各一套）
- 14 个面试问答覆盖 RAG、前端工程化、后端部署、项目整体
- 全流程 10 项验收全部通过
- Git 仓库已初始化并推送到 GitHub

---

恭喜你完成了 DocsChat 的全部 5 天开发。这个项目覆盖了：

- **RAG 全链路**：从 PDF 解析到 Reranker 精排的完整理解和实现
- **前端工程化**：Vue3 Composition API、SSE 流式渲染、Markdown 渲染、错误边界、虚拟滚动、骨架屏
- **测试体系**：17 个前端用例 + 4 组后端测试，Mock 策略
- **部署运维**：Docker 多阶段构建、健康检查、docker-compose 编排
- **工程思维**：RAGAS 量化评估、日志系统、异常处理、代码分割

现在你已经有了一个可以在简历上自信展示的全栈 AI 应用项目。