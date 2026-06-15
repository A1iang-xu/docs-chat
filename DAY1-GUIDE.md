# DocsChat Day 1 · 全栈基建与 SSE 流式通信

> 目标：打通 DeepSeek API → FastAPI SSE → 前端打字机渲染的完整链路。
> 预计耗时：8 小时（上午 3h + 下午 3h + 晚间 2h）

---

## 第一部分：后端 — DeepSeek API 封装与流式端点（上午 3h）

### 1.1 创建 LLM 服务层 `backend\app\services\llm_service.py`

```python
"""DeepSeek API 封装 —— 支持流式调用、指数退避重试、Token 用量记录"""
import logging
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """封装 DeepSeek API（OpenAI 兼容接口），提供流式和非流式调用"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self.model = settings.DEEPSEEK_MODEL
        self.max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self.temperature = settings.DEEPSEEK_TEMPERATURE
        self.max_retries = 3
        self.retry_base_ms = 1000

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式调用 DeepSeek Chat API，逐 token 返回。
        支持指数退避重试（最多 3 次）。

        Args:
            messages: 对话历史，格式 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（可选）

        Yields:
            每个 delta token 的文本内容
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    stream=True,
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content

                return  # 成功完成

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.retry_base_ms * (2 ** attempt)
                    logger.warning(
                        f"DeepSeek API 调用失败 (attempt {attempt + 1}/{self.max_retries + 1})，"
                        f"{delay}ms 后重试: {e}"
                    )
                    await self._async_sleep(delay / 1000)
                else:
                    logger.error(f"DeepSeek API 调用最终失败: {e}")

        raise last_exception or RuntimeError("DeepSeek API 调用失败")

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        非流式调用 DeepSeek Chat API，返回完整回答。

        Args:
            messages: 对话历史
            system_prompt: 系统提示词（可选）

        Returns:
            完整回答文本
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )

        return response.choices[0].message.content or ""

    @staticmethod
    async def _async_sleep(seconds: float):
        """异步 sleep，兼容不同事件循环"""
        import asyncio
        await asyncio.sleep(seconds)


# 全局单例
llm_service = LLMService()
```

### 1.2 创建 Chat API 路由 `backend\app\api\chat.py`

```python
"""对话 API —— SSE 流式端点"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import MessageCreate, SSEEvent
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(body: MessageCreate):
    """
    SSE 流式对话端点。

    前端通过 EventSource 或 fetch + ReadableStream 消费此端点。
    事件格式：
        data: {"event":"token","data":"你"}
        data: {"event":"token","data":"好"}
        data: {"event":"source","data":"[{\"index\":1,\"content\":\"...\"}]"}
        data: {"event":"done","data":""}
        data: {"event":"error","data":"错误信息"}
    """
    try:
        messages = [{"role": "user", "content": body.content}]

        async def event_generator():
            try:
                async for token in llm_service.chat_stream(messages):
                    event = SSEEvent(event="token", data=token)
                    yield f"data: {event.model_dump_json()}\n\n"

                # 发送完成信号
                done_event = SSEEvent(event="done", data="")
                yield f"data: {done_event.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"流式对话异常: {e}")
                error_event = SSEEvent(event="error", data=str(e))
                yield f"data: {error_event.model_dump_json()}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )

    except Exception as e:
        logger.error(f"对话请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 1.3 更新后端路由注册 `backend\app\main.py`

用以下内容**替换** `backend\app\main.py`：

```python
"""FastAPI 应用入口 —— 挂载路由、配置 CORS、启动服务"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router

# ── 日志配置 ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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

# ── 路由注册 ──
app.include_router(chat_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocsChat API"}


# ── 启动入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
```

### 1.4 后端验证

```powershell
cd E:\docs-chat\backend

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 确保 .env 已配置 DEEPSEEK_API_KEY

# 启动后端
uvicorn app.main:app --reload --port 8000
```

打开另一个终端，测试流式端点：

```powershell
cd E:\docs-chat\backend
.\.venv\Scripts\Activate.ps1

# 测试流式对话（PowerShell 中使用 curl.exe）
curl.exe -s -N -X POST http://localhost:8000/chat/stream `
  -H "Content-Type: application/json" `
  -d "{\"conversation_id\":\"test\",\"content\":\"你好，请用三句话介绍你自己\"}"
```

> **注意**：PowerShell 的 `Invoke-WebRequest` 无法正确处理 SSE 流式响应，
> 请使用 `curl.exe`（Windows 10 1803+ 自带）测试。如果看到逐 token 返回的 SSE 事件流，第一部分完成。

---

## 第二部分：前端 — 对话界面组件（下午 3h）

### 2.1 侧边栏组件 `frontend\src\components\ConversationSidebar.vue`

```vue
<script setup lang="ts">
import { useConversationStore } from '@/stores/conversation'
import type { Conversation } from '@/types'

const conversationStore = useConversationStore()

function handleNewChat() {
  conversationStore.createConversation('新对话')
}

function handleSelect(id: string) {
  conversationStore.setActive(id)
}
</script>

<template>
  <aside class="sidebar">
    <button class="new-chat-btn" @click="handleNewChat">
      + 新建对话
    </button>

    <div class="conversation-list">
      <div
        v-for="conv in conversationStore.conversations"
        :key="conv.id"
        class="conv-item"
        :class="{ active: conv.id === conversationStore.activeId }"
        @click="handleSelect(conv.id)"
      >
        <span class="conv-title">{{ conv.title }}</span>
        <span class="conv-date">{{ new Date(conv.updatedAt).toLocaleDateString() }}</span>
      </div>

      <div v-if="conversationStore.conversations.length === 0" class="empty-hint">
        暂无对话，点击上方按钮新建
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  background: var(--bg2);
  border-right: 1px solid var(--rule);
  display: flex;
  flex-direction: column;
  padding: 1rem;
}

.new-chat-btn {
  width: 100%;
  padding: 0.65rem;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 1rem;
  transition: opacity 0.2s;
}
.new-chat-btn:hover {
  opacity: 0.85;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
}

.conv-item {
  padding: 0.65rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 0.25rem;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.conv-item:hover {
  background: var(--rule);
}
.conv-item.active {
  background: var(--rule);
}

.conv-title {
  font-size: 0.9rem;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-date {
  font-size: 0.75rem;
  color: var(--muted);
}

.empty-hint {
  color: var(--muted);
  font-size: 0.85rem;
  text-align: center;
  margin-top: 2rem;
}
</style>
```

### 2.2 消息组件 `frontend\src\components\ChatMessage.vue`

```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/types'

const props = defineProps<{
  message: Message
}>()

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')
</script>

<template>
  <div class="message" :class="{ user: isUser, assistant: isAssistant }">
    <div class="role-label">{{ isUser ? '你' : 'DocsChat' }}</div>
    <div class="content">
      <div class="text" v-text="message.content"></div>

      <!-- 引用来源 -->
      <div v-if="message.sources.length > 0" class="sources">
        <span class="sources-label">参考来源：</span>
        <span
          v-for="source in message.sources"
          :key="source.index"
          class="source-badge"
          :title="source.content"
        >
          [{{ source.index }}]
          <span class="source-tooltip">{{ source.content }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  flex-direction: column;
  padding: 0.75rem 1.5rem;
  max-width: 100%;
}

.message.user {
  background: var(--bg);
}

.message.assistant {
  background: var(--bg2);
}

.role-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--muted);
  margin-bottom: 0.3rem;
}

.content {
  line-height: 1.7;
}

.text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 来源引用 */
.sources {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--rule);
  font-size: 0.8rem;
  color: var(--muted);
}

.sources-label {
  margin-right: 0.25rem;
}

.source-badge {
  display: inline-block;
  position: relative;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
  margin-right: 0.35rem;
}

.source-badge .source-tooltip {
  display: none;
  position: absolute;
  bottom: 120%;
  left: 50%;
  transform: translateX(-50%);
  width: 280px;
  padding: 0.5rem 0.75rem;
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 400;
  color: var(--ink);
  white-space: normal;
  word-break: break-word;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.source-badge:hover .source-tooltip {
  display: block;
}
</style>
```

### 2.3 输入组件 `frontend\src\components\MessageInput.vue`

```vue
<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  send: [content: string]
}>()

const input = ref('')
const isSending = defineModel<boolean>('isSending', { default: false })

function handleSend() {
  const content = input.value.trim()
  if (!content || isSending.value) return
  emit('send', content)
  input.value = ''
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="input-area">
    <textarea
      v-model="input"
      class="input-box"
      :disabled="isSending"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      rows="1"
      @keydown="handleKeydown"
      @input="(e) => {
        const el = e.target as HTMLTextAreaElement
        el.style.height = 'auto'
        el.style.height = el.scrollHeight + 'px'
      }"
    ></textarea>
    <button
      class="send-btn"
      :disabled="!input.trim() || isSending"
      @click="handleSend"
    >
      {{ isSending ? '发送中...' : '发送' }}
    </button>
  </div>
</template>

<style scoped>
.input-area {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--rule);
  background: var(--bg);
}

.input-box {
  flex: 1;
  padding: 0.7rem 0.85rem;
  background: var(--bg2);
  border: 1px solid var(--rule);
  border-radius: 8px;
  color: var(--ink);
  font-size: 0.9rem;
  font-family: inherit;
  resize: none;
  max-height: 200px;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.2s;
}

.input-box:focus {
  border-color: var(--accent);
}

.input-box:disabled {
  opacity: 0.5;
}

.send-btn {
  padding: 0.7rem 1.25rem;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
```

### 2.4 对话页面 `frontend\src\views\ChatView.vue`

这是 Day 1 的核心页面，整合了 SSE 流式调用、消息渲染、多会话管理。

```vue
<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useConversationStore } from '@/stores/conversation'
import { useMessageStore } from '@/stores/message'
import { useSSE } from '@/composables/useSSE'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import MessageInput from '@/components/MessageInput.vue'
import type { Message } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const conversationStore = useConversationStore()
const messageStore = useMessageStore()

const { content, sources, isStreaming, error, connect, abort } = useSSE({
  maxRetries: 2,
  retryBaseMs: 1000,
  heartbeatTimeoutMs: 30_000,
})

const isSending = ref(false)
const assistantMsgId = ref<string | null>(null)
const messageContainer = ref<HTMLElement | null>(null)

// 当前会话的消息列表
const currentMessages = ref<Message[]>([])

watch(
  () => conversationStore.activeId,
  (newId) => {
    if (newId) {
      currentMessages.value = messageStore.getMessages(newId)
    } else {
      currentMessages.value = []
    }
  },
  { immediate: true },
)

// 流式内容更新时，实时写入 assistant 消息
watch(content, (newContent) => {
  if (assistantMsgId.value && conversationStore.activeId) {
    messageStore.updateAssistantMessage(
      conversationStore.activeId,
      assistantMsgId.value,
      newContent,
      sources.value,
    )
    currentMessages.value = messageStore.getMessages(conversationStore.activeId!)
    scrollToBottom()
  }
})

watch(sources, (newSources) => {
  if (assistantMsgId.value && conversationStore.activeId) {
    messageStore.updateAssistantMessage(
      conversationStore.activeId!,
      assistantMsgId.value,
      content.value,
      newSources,
    )
    currentMessages.value = messageStore.getMessages(conversationStore.activeId!)
  }
})

async function handleSend(text: string) {
  // 确保有活跃会话
  if (!conversationStore.activeId) {
    await conversationStore.createConversation('新对话')
  }

  const convId = conversationStore.activeId!
  isSending.value = true

  // 添加用户消息 + 创建空的 assistant 消息
  assistantMsgId.value = await messageStore.sendMessage(convId, text)
  currentMessages.value = messageStore.getMessages(convId)

  await nextTick()
  scrollToBottom()

  // 发起 SSE 流式请求
  await connect(`${API_BASE}/chat/stream`, {
    conversation_id: convId,
    content: text,
  })

  isSending.value = false
  assistantMsgId.value = null
}

function handleAbort() {
  abort()
  isSending.value = false
}

function scrollToBottom() {
  nextTick(() => {
    if (messageContainer.value) {
      messageContainer.value.scrollTop = messageContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  // 如果没有会话，创建一个
  if (!conversationStore.activeId) {
    conversationStore.createConversation('新对话')
  }
})
</script>

<template>
  <div class="chat-layout">
    <ConversationSidebar />

    <main class="chat-main">
      <!-- 顶部栏 -->
      <header class="chat-header">
        <h2>{{ conversationStore.activeConversation?.title || 'DocsChat' }}</h2>
        <button
          v-if="isStreaming"
          class="abort-btn"
          @click="handleAbort"
        >
          停止生成
        </button>
      </header>

      <!-- 消息列表 -->
      <div ref="messageContainer" class="message-list">
        <ChatMessage
          v-for="msg in currentMessages"
          :key="msg.id"
          :message="msg"
        />

        <!-- 错误提示 -->
        <div v-if="error" class="error-banner">
          请求失败：{{ error }}
          <button @click="error = null">关闭</button>
        </div>
      </div>

      <!-- 输入区域 -->
      <MessageInput
        v-model:is-sending="isSending"
        @send="handleSend"
      />
    </main>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--rule);
  background: var(--bg);
}

.chat-header h2 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--ink);
}

.abort-btn {
  padding: 0.35rem 0.85rem;
  background: var(--bg2);
  color: var(--danger);
  border: 1px solid var(--danger);
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.2s;
}

.abort-btn:hover {
  background: rgba(248, 81, 73, 0.1);
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 0;
}

.error-banner {
  margin: 1rem 1.5rem;
  padding: 0.75rem 1rem;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid var(--danger);
  border-radius: 8px;
  color: var(--danger);
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.error-banner button {
  background: none;
  border: none;
  color: var(--danger);
  cursor: pointer;
  font-weight: 600;
}
</style>
```

### 2.5 更新根组件 `frontend\src\App.vue`

用以下内容**替换** `frontend\src\App.vue`：

```vue
<script setup lang="ts">
import ChatView from '@/views/ChatView.vue'
</script>

<template>
  <ChatView />
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
  --danger: #f85149;
}

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
  overflow: hidden;
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--rule);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}
</style>
```

---

## 第三部分：联调验证（晚间 2h）

### 3.1 启动后端

```powershell
cd E:\docs-chat\backend
uvicorn app.main:app --reload --port 8000
```

### 3.2 启动前端

```powershell
cd E:\docs-chat\frontend
npm run dev
```

浏览器打开 `http://localhost:5173`

### 3.3 验收清单

逐项测试以下功能，全部通过即 Day 1 完成：

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | 后端健康检查 | 浏览器打开 `http://localhost:8000/health` | 返回 `{"status":"ok","service":"DocsChat API"}` |
| 2 | 后端流式端点 | Postman / curl 测试 `POST /chat/stream` | 返回 SSE 事件流，逐 token 推送 |
| 3 | 前端页面加载 | 浏览器打开 `http://localhost:5173` | 显示左侧栏 + 对话区域 + 输入框 |
| 4 | 新建会话 | 点击 "+ 新建对话" | 左侧列表新增一项，自动选中 |
| 5 | 发送消息 | 输入文字，按 Enter | 消息出现在对话区，显示"发送中..." |
| 6 | 打字机效果 | 发送后观察 | assistant 回复逐字出现，无卡顿 |
| 7 | 停止生成 | 生成过程中点击"停止生成" | 流式传输立即中断，按钮恢复 |
| 8 | 断线重连 | 生成过程中停止后端服务 | 前端显示错误提示，不崩溃 |

### 3.4 常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 后端启动报 `DEEPSEEK_API_KEY` 错误 | 未配置 `.env` | `cp .env.example .env`，编辑填入真实 Key |
| 前端 `@/stores/conversation` 找不到 | 路径别名未生效 | 检查 `vite.config.ts` 和 `tsconfig.app.json` 是否正确配置 |
| SSE 连不上 | CORS 问题 | 确认 `settings.CORS_ORIGINS` 包含 `http://localhost:5173` |
| 打字机卡顿 | 网络或 API 限流 | 检查 DeepSeek 账户余额和 API Key 是否有效 |
| 输入框自动增高不生效 | textarea 高度计算问题 | 确认 `@input` 事件中的 `scrollHeight` 逻辑正确 |

---

## Day 1 完成标志

- 前后端同时运行
- 输入任意问题，能看到 DeepSeek 逐字流式回复
- 可以新建/切换会话，不同会话消息互相隔离
- 点击"停止生成"能立即中断

完成后，项目结构变为：

```
docs-chat/
├── backend/
│   └── app/
│       ├── api/
│       │   ├── __init__.py
│       │   └── chat.py          ← 新增
│       ├── services/
│       │   ├── __init__.py
│       │   └── llm_service.py   ← 新增
│       └── main.py              ← 更新
├── frontend/
│   └── src/
│       ├── App.vue              ← 更新
│       ├── components/
│       │   ├── ChatMessage.vue      ← 新增
│       │   ├── ConversationSidebar.vue ← 新增
│       │   └── MessageInput.vue     ← 新增
│       └── views/
│           └── ChatView.vue         ← 新增
```

完成后告诉我，进入 Day 2：RAG 知识库构建与混合检索。