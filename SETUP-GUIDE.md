# DocsChat 项目准备阶段 · 完整操作指南

> 按以下步骤逐项执行，即可在 E 盘从零搭建完整项目骨架。每步都附有可复制的命令和文件内容。

---

## 前置检查

在开始前，确认你的环境：

```powershell
python --version   # 需要 3.10+
node --version     # 需要 18+
npm --version      # 需要 9+
```

---

## 第一步：创建项目根目录

打开 PowerShell，执行：

```powershell
New-Item -ItemType Directory -Path E:\docs-chat -Force
cd E:\docs-chat
```

---

## 第二步：创建后端目录结构

```powershell
# 后端目录
New-Item -ItemType Directory -Path E:\docs-chat\backend\app\api -Force
New-Item -ItemType Directory -Path E:\docs-chat\backend\app\core -Force
New-Item -ItemType Directory -Path E:\docs-chat\backend\app\models -Force
New-Item -ItemType Directory -Path E:\docs-chat\backend\app\services -Force
New-Item -ItemType Directory -Path E:\docs-chat\backend\tests -Force
```

这会在 `E:\docs-chat\backend\` 下创建：
```
backend/
├── app/
│   ├── api/          # API 路由（Day 1 填充）
│   ├── core/         # 配置管理
│   ├── models/       # 数据模型
│   └── services/     # RAG 业务逻辑（Day 2 填充）
└── tests/
```

---

## 第三步：创建后端空 __init__.py 文件

每个 Python 包目录都需要 `__init__.py`。在 PowerShell 中执行：

```powershell
$null > E:\docs-chat\backend\app\__init__.py
$null > E:\docs-chat\backend\app\api\__init__.py
$null > E:\docs-chat\backend\app\core\__init__.py
$null > E:\docs-chat\backend\app\models\__init__.py
$null > E:\docs-chat\backend\app\services\__init__.py
$null > E:\docs-chat\backend\tests\__init__.py
```

---

## 第四步：创建后端核心文件

### 4.1 依赖清单 `backend\requirements.txt`

在 `E:\docs-chat\backend\` 下创建 `requirements.txt`，内容如下：

```txt
# Web Framework
fastapi==0.115.6
uvicorn[standard]==0.34.0
sse-starlette==2.2.1

# RAG & LLM
langchain==0.3.13
langchain-community==0.3.13
langchain-openai==0.2.14
chromadb==0.5.23
pypdf2==3.0.1
pdfplumber==0.11.4
rank-bm25==0.2.2
sentence-transformers==3.3.1

# Data & Validation
pydantic==2.10.4
pydantic-settings==2.7.1

# HTTP & Async
httpx==0.28.1
python-multipart==0.0.19

# Evaluation (RAGAS)
ragas==0.2.10

# Testing
pytest==8.3.4
pytest-asyncio==0.25.0

# Dev Tools
python-dotenv==1.0.1
```

### 4.2 应用配置 `backend\app\core\config.py`

```python
"""应用配置管理 —— 基于 pydantic-settings 从环境变量 / .env 加载"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── 项目路径 ──
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_data")
    UPLOAD_DIR: str = str(PROJECT_ROOT / "uploads")

    # ── DeepSeek API ──
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek Open Platform API Key")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_MAX_TOKENS: int = 4096
    DEEPSEEK_TEMPERATURE: float = 0.7

    # ── Embedding ──
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # ── 分块策略 ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 100

    # ── 检索 ──
    RETRIEVAL_TOP_K: int = 10
    RERANKER_TOP_K: int = 5
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # ── 服务 ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── 日志 ──
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()
```

### 4.3 数据模型 `backend\app\models\schemas.py`

```python
"""Pydantic 数据模型 —— 定义 API 请求/响应、对话、文档等核心数据结构"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from uuid import uuid4


# ═══════════════════════════════════════════
# 对话会话
# ═══════════════════════════════════════════

class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=100)


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════
# 消息
# ═══════════════════════════════════════════

class MessageCreate(BaseModel):
    conversation_id: str
    content: str = Field(..., min_length=1, max_length=10000)


class SourceCitation(BaseModel):
    """检索到的来源引用"""
    index: int
    content: str
    page: Optional[int] = None
    document_name: Optional[str] = None
    relevance_score: float = 0.0


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════
# 文档
# ═══════════════════════════════════════════

class DocumentMeta(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    filename: str
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: datetime = Field(default_factory=datetime.now)
    status: Literal["processing", "ready", "error"] = "processing"


# ═══════════════════════════════════════════
# SSE 事件
# ═══════════════════════════════════════════

class SSEEvent(BaseModel):
    """SSE 流式响应的单次事件"""
    event: Literal["token", "source", "done", "error"]
    data: str


# ═══════════════════════════════════════════
# 通用响应
# ═══════════════════════════════════════════

class ErrorResponse(BaseModel):
    detail: str
    code: str = "internal_error"
```

### 4.4 FastAPI 入口 `backend\app\main.py`

```python
"""FastAPI 应用入口 —— 挂载路由、配置 CORS、启动服务"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(
    title="DocsChat API",
    description="RAG 智能对话系统后端服务",
    version="0.1.0",
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocsChat API"}


# ── 启动入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
```

### 4.5 环境变量模板 `backend\.env.example`

```txt
# DeepSeek API Key — 从 https://platform.deepseek.com/api_keys 获取
DEEPSEEK_API_KEY=your-api-key-here

# 可选：本地 Ollama 备用模型
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=qwen2:7b
```

### 4.6 后端 Dockerfile `backend\Dockerfile`

```dockerfile
# Dockerfile — 后端服务
FROM python:3.10-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 创建数据目录
RUN mkdir -p chroma_data uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 第五步：安装后端依赖

```powershell
cd E:\docs-chat\backend
pip install -r requirements.txt
```

> 安装可能需要 5-10 分钟（sentence-transformers 和 torch 包较大）。

验证安装：

```powershell
python -c "import fastapi; import chromadb; import langchain; print('OK')"
```

---

## 第六步：初始化前端项目

### 6.1 用 Vite 脚手架创建

```powershell
cd E:\docs-chat
npm create vite@latest frontend -- --template vue-ts
```

### 6.2 安装依赖

```powershell
cd E:\docs-chat\frontend
npm install
npm install axios pinia marked highlight.js vue-virtual-scroller @vueuse/core
```

### 6.3 创建前端源码目录

```powershell
$src = 'E:\docs-chat\frontend\src'
New-Item -ItemType Directory -Path (Join-Path $src 'components') -Force
New-Item -ItemType Directory -Path (Join-Path $src 'composables') -Force
New-Item -ItemType Directory -Path (Join-Path $src 'stores') -Force
New-Item -ItemType Directory -Path (Join-Path $src 'types') -Force
New-Item -ItemType Directory -Path (Join-Path $src 'utils') -Force
New-Item -ItemType Directory -Path (Join-Path $src 'views') -Force
```

### 6.4 清理 Vite 模板文件

```powershell
Remove-Item E:\docs-chat\frontend\src\components\HelloWorld.vue
Remove-Item E:\docs-chat\frontend\src\style.css
Remove-Item E:\docs-chat\frontend\src\assets\vite.svg
Remove-Item E:\docs-chat\frontend\src\assets\vue.svg
Remove-Item E:\docs-chat\frontend\src\assets\hero.png -ErrorAction SilentlyContinue
```

---

## 第七步：创建前端核心文件

### 7.1 TypeScript 类型定义 `frontend\src\types\index.ts`

```typescript
/**
 * DocsChat 全局类型定义
 * 覆盖对话、消息、文档、SSE 事件等核心领域模型
 */

// ═══════════════════════════════════════════
// 对话会话
// ═══════════════════════════════════════════

export interface Conversation {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface ConversationCreate {
  title: string
}

// ═══════════════════════════════════════════
// 消息
// ═══════════════════════════════════════════

export type MessageRole = 'user' | 'assistant' | 'system'

export interface SourceCitation {
  /** 角标编号 [1], [2], ... */
  index: number
  /** 原文片段 */
  content: string
  /** 页码 */
  page?: number
  /** 文档名称 */
  documentName?: string
  /** 相关性分数 */
  relevanceScore: number
}

export interface Message {
  id: string
  conversationId: string
  role: MessageRole
  content: string
  sources: SourceCitation[]
  createdAt: string
}

export interface MessageCreate {
  conversationId: string
  content: string
}

// ═══════════════════════════════════════════
// 文档
// ═══════════════════════════════════════════

export type DocumentStatus = 'processing' | 'ready' | 'error'

export interface DocumentMeta {
  id: string
  filename: string
  pageCount: number
  chunkCount: number
  uploadedAt: string
  status: DocumentStatus
}

// ═══════════════════════════════════════════
// SSE 事件
// ═══════════════════════════════════════════

export type SSEEventType = 'token' | 'source' | 'done' | 'error'

export interface SSEEvent {
  event: SSEEventType
  data: string
}

export interface StreamState {
  content: string
  sources: SourceCitation[]
  isStreaming: boolean
  error: string | null
}

// ═══════════════════════════════════════════
// 通用响应
// ═══════════════════════════════════════════

export interface ApiError {
  detail: string
  code: string
}

// ═══════════════════════════════════════════
// Store 状态
// ═══════════════════════════════════════════

export interface ConversationsState {
  conversations: Conversation[]
  activeId: string | null
  loading: boolean
}

export interface MessagesState {
  messages: Record<string, Message[]>
  streamState: Record<string, StreamState>
  loading: boolean
}
```

### 7.2 Axios 封装 `frontend\src\utils\api.ts`

```typescript
/**
 * Axios 实例 + 请求/响应拦截器
 * 统一管理 baseURL、错误处理、Token 等
 */
import axios, { type AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器 ──
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    return config
  },
  (error: AxiosError) => Promise.reject(error),
)

// ── 响应拦截器 ──
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<ApiError>) => {
    const detail = error.response?.data?.detail || error.message || '网络请求失败'
    console.error(`[API Error] ${error.config?.url}: ${detail}`)
    return Promise.reject(error)
  },
)

export default api
```

### 7.3 SSE Composable `frontend\src\composables\useSSE.ts`

```typescript
/**
 * useSSE — 管理 SSE 流式连接的 Composable
 * 支持断线重连、心跳检测、AbortController 中断
 */
import { ref, onUnmounted } from 'vue'
import type { SourceCitation, SSEEvent } from '@/types'

export interface SSEOptions {
  maxRetries?: number
  retryBaseMs?: number
  heartbeatTimeoutMs?: number
}

export function useSSE(options: SSEOptions = {}) {
  const { maxRetries = 3, retryBaseMs = 1000, heartbeatTimeoutMs = 30_000 } = options

  const content = ref('')
  const sources = ref<SourceCitation[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)

  let abortController: AbortController | null = null
  let retryCount = 0
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null

  function resetHeartbeat() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => {
      abort('心跳超时，连接已断开')
    }, heartbeatTimeoutMs)
  }

  function clearHeartbeat() {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function abort(reason?: string) {
    abortController?.abort()
    isStreaming.value = false
    clearHeartbeat()
    if (reason) error.value = reason
  }

  async function connect(url: string, body: Record<string, unknown>) {
    abort()
    content.value = ''
    sources.value = []
    error.value = null
    isStreaming.value = true
    retryCount = 0
    await doConnect(url, body)
  }

  async function doConnect(url: string, body: Record<string, unknown>) {
    abortController = new AbortController()

    try {
      resetHeartbeat()

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法获取响应流')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        resetHeartbeat()
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: SSEEvent = JSON.parse(line.slice(6))

              switch (event.event) {
                case 'token':
                  content.value += event.data
                  break
                case 'source':
                  sources.value = JSON.parse(event.data) as SourceCitation[]
                  break
                case 'done':
                  isStreaming.value = false
                  clearHeartbeat()
                  return
                case 'error':
                  error.value = event.data
                  isStreaming.value = false
                  clearHeartbeat()
                  return
              }
            } catch {
              // 非 JSON 行，忽略
            }
          }
        }
      }

      isStreaming.value = false
      clearHeartbeat()
    } catch (e: unknown) {
      if ((e as Error).name === 'AbortError') return

      if (retryCount < maxRetries) {
        retryCount++
        const delay = retryBaseMs * Math.pow(2, retryCount - 1)
        console.warn(`[SSE] 重连 ${retryCount}/${maxRetries}，等待 ${delay}ms`)
        await new Promise((r) => setTimeout(r, delay))
        return doConnect(url, body)
      }

      error.value = (e as Error).message
      isStreaming.value = false
      clearHeartbeat()
    }
  }

  onUnmounted(() => {
    abort()
  })

  return { content, sources, isStreaming, error, connect, abort }
}
```

### 7.4 会话 Store `frontend\src\stores\conversation.ts`

```typescript
/**
 * 对话会话 Store —— 管理会话列表、当前活跃会话
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Conversation } from '@/types'

export const useConversationStore = defineStore('conversation', () => {
  const conversations = ref<Conversation[]>([])
  const activeId = ref<string | null>(null)
  const loading = ref(false)

  const activeConversation = computed(() =>
    conversations.value.find((c) => c.id === activeId.value) ?? null,
  )

  async function fetchConversations() {
    loading.value = true
    try {
      // TODO: Day 1 实现后端会话接口
    } finally {
      loading.value = false
    }
  }

  async function createConversation(title: string) {
    const newConv: Conversation = {
      id: crypto.randomUUID(),
      title,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    conversations.value.unshift(newConv)
    activeId.value = newConv.id
    return newConv
  }

  function setActive(id: string) {
    activeId.value = id
  }

  return {
    conversations,
    activeId,
    activeConversation,
    loading,
    fetchConversations,
    createConversation,
    setActive,
  }
})
```

### 7.5 消息 Store `frontend\src\stores\message.ts`

```typescript
/**
 * 消息 Store —— 管理每个会话的消息列表与流式状态
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message, SourceCitation } from '@/types'

export const useMessageStore = defineStore('message', () => {
  const messages = ref<Record<string, Message[]>>({})
  const loading = ref(false)

  function getMessages(conversationId: string): Message[] {
    return messages.value[conversationId] ?? []
  }

  function addMessage(conversationId: string, message: Message) {
    if (!messages.value[conversationId]) {
      messages.value[conversationId] = []
    }
    messages.value[conversationId].push(message)
  }

  function updateAssistantMessage(
    conversationId: string,
    messageId: string,
    content: string,
    sources: SourceCitation[] = [],
  ) {
    const msgs = messages.value[conversationId]
    if (!msgs) return
    const msg = msgs.find((m) => m.id === messageId)
    if (msg) {
      msg.content = content
      msg.sources = sources
    }
  }

  async function sendMessage(conversationId: string, content: string) {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversationId,
      role: 'user',
      content,
      sources: [],
      createdAt: new Date().toISOString(),
    }
    addMessage(conversationId, userMsg)

    const assistantMsg: Message = {
      id: crypto.randomUUID(),
      conversationId,
      role: 'assistant',
      content: '',
      sources: [],
      createdAt: new Date().toISOString(),
    }
    addMessage(conversationId, assistantMsg)

    return assistantMsg.id
  }

  return {
    messages,
    loading,
    getMessages,
    addMessage,
    updateAssistantMessage,
    sendMessage,
  }
})
```

### 7.6 Vite 环境变量类型声明 `frontend\src\env.d.ts`

```typescript
/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

### 7.7 前端入口 `frontend\src\main.ts`

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.mount('#app')
```

### 7.8 根组件 `frontend\src\App.vue`

```vue
<script setup lang="ts">
import { useConversationStore } from '@/stores/conversation'

const conversationStore = useConversationStore()
</script>

<template>
  <div class="app">
    <h1>DocsChat</h1>
    <p>RAG 智能对话系统 — 准备就绪</p>
    <p class="muted">Day 1 将实现完整的流式对话功能</p>
  </div>
</template>

<style>
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --ink: #e6edf3;
  --muted: #8b949e;
  --rule: #30363d;
  --accent: #58a6ff;
  --accent2: #3fb950;
}

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
}

.app {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  text-align: center;
}

h1 {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
  color: var(--accent);
}

.muted {
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 0.5rem;
}
</style>
```

### 7.9 前端环境变量 `frontend\.env`

```txt
VITE_API_BASE_URL=http://localhost:8000
```

---

## 第八步：配置 Vite 路径别名

### 8.1 修改 `frontend\vite.config.ts`

打开 `E:\docs-chat\frontend\vite.config.ts`，替换为：

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
```

### 8.2 修改 `frontend\tsconfig.app.json`

打开 `E:\docs-chat\frontend\tsconfig.app.json`，在 `compilerOptions` 中增加 `baseUrl` 和 `paths`，同时关闭 `noUnusedLocals`（开发阶段避免报错干扰）：

```json
{
  "extends": "@vue/tsconfig/tsconfig.dom.json",
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "types": ["vite/client"],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue"]
}
```

---

## 第九步：创建前端工程化配置

### 9.1 Prettier 配置 `frontend\.prettierrc`

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

### 9.2 Prettier 忽略文件 `frontend\.prettierignore`

```txt
node_modules
dist
*.min.js
```

### 9.3 前端 Dockerfile `frontend\Dockerfile`

```dockerfile
# Dockerfile — 前端服务（开发模式）
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## 第十步：创建项目根目录文件

### 10.1 Docker Compose `docker-compose.yml`

在 `E:\docs-chat\` 下创建：

```yaml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - chroma_data:/app/chroma_data
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - VITE_API_BASE_URL=http://localhost:8000
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  chroma_data:
```

### 10.2 Git 忽略文件 `.gitignore`

```txt
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.env
chroma_data/
uploads/

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
```

### 10.3 项目 README `README.md`

```markdown
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
```

---

## 第十一步：验证整个项目

全部完成后，执行以下验证：

### 后端

```powershell
cd E:\docs-chat\backend
cp .env.example .env                       # 复制环境变量
# 编辑 .env，填入你的 DEEPSEEK_API_KEY
python -c "from app.core.config import settings; print('配置加载 OK, PORT:', settings.PORT)"
python -c "from app.models.schemas import Conversation, Message; print('数据模型 OK')"
```

### 前端

```powershell
cd E:\docs-chat\frontend
npx vue-tsc --noEmit                         # 类型检查
```

### 最终目录结构检查

```powershell
Get-ChildItem -Recurse E:\docs-chat -Name | Where-Object { $_ -notmatch 'node_modules|\.git' } | Sort-Object
```

预期输出应包含：

```
.gitignore
README.md
docker-compose.yml
backend\.env.example
backend\Dockerfile
backend\requirements.txt
backend\app\__init__.py
backend\app\main.py
backend\app\api\__init__.py
backend\app\core\__init__.py
backend\app\core\config.py
backend\app\models\__init__.py
backend\app\models\schemas.py
backend\app\services\__init__.py
backend\tests\__init__.py
frontend\.env
frontend\.prettierignore
frontend\.prettierrc
frontend\Dockerfile
frontend\vite.config.ts
frontend\tsconfig.app.json
frontend\src\App.vue
frontend\src\main.ts
frontend\src\env.d.ts
frontend\src\composables\useSSE.ts
frontend\src\stores\conversation.ts
frontend\src\stores\message.ts
frontend\src\types\index.ts
frontend\src\utils\api.ts
```

---

## 完成标志

看到以下输出即表示准备阶段完成：

- 后端：`python -c "from app.main import app; print('FastAPI 启动 OK')"` 无报错
- 前端：`npm run dev` 启动后浏览器打开 `http://localhost:5173` 能看到 "DocsChat — RAG 智能对话系统 — 准备就绪"

完成后告诉我，我们进入 Day 1：DeepSeek API 流式调用 + SSE 端到端通信。