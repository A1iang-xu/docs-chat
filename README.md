# DocsChat

基于 RAG（检索增强生成）的本地知识库智能对话系统。支持 PDF 文档上传、语义检索、混合检索重排序，以及流式对话交互。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Python 3.10+ / FastAPI / SSE |
| RAG 链路 | LangChain / ChromaDB / BM25 / BGE-Reranker |
| 大模型 | DeepSeek V4 API（OpenAI 兼容） |
| 前端 | Vite + Vue3 + TypeScript / Pinia |
| 部署 | Docker Compose |

## 快速启动

### 前置要求

- Python 3.10+
- Node.js 20+
- Docker & Docker Compose（可选）

### 1. 后端

\`\`\`bash
cd backend
cp .env.example .env          # 编辑 .env 填入 DEEPSEEK_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
\`\`\`

### 2. 前端

\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

### 3. Docker 一键启动

\`\`\`bash
cp backend/.env.example backend/.env  # 编辑填入 API Key
docker compose up --build
\`\`\`

## 项目结构

\`\`\`
docs-chat/
├── backend/
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── core/         # 配置、依赖注入
│   │   ├── models/       # Pydantic 数据模型
│   │   ├── services/     # RAG 业务逻辑
│   │   └── main.py       # FastAPI 入口
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/   # Vue 组件
│   │   ├── composables/  # 组合式函数 (useSSE)
│   │   ├── stores/       # Pinia 状态管理
│   │   ├── types/        # TypeScript 类型定义
│   │   ├── utils/        # 工具函数 (Axios)
│   │   └── views/        # 页面
│   └── Dockerfile
├── docker-compose.yml
└── README.md
\`\`\`

## 开发路线

- [x] Day 0: 项目初始化与工程准备
- [ ] Day 1: 全栈基建 + LLM 流式通信
- [ ] Day 2: RAG 知识库构建 + 混合检索
- [ ] Day 3: 前端交互 + RAGAS 评估
- [ ] Day 4: 前端深水区 + 测试 + Docker
- [ ] Day 5: 优化打磨 + 简历素材