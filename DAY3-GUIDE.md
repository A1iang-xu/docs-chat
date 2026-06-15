# DocsChat Day 3 · 前端交互打磨 + RAG 质量评估

> 目标：完成 Markdown 渲染与代码高亮、引用来源完整交互、错误边界与虚拟滚动优化，并引入 RAGAS 评估框架产出量化指标。
> 预计耗时：8 小时（上午 3h + 下午 3h + 晚间 2h）

---

## 第一部分：Markdown 渲染与代码高亮（上午 3h）

### 1.1 安装前端依赖

```powershell
cd E:\docs-chat\frontend
npm install marked highlight.js @vueuse/core
npm install -D @types/marked
```

### 1.2 创建 Markdown 渲染 Composable `frontend\src\composables\useMarkdown.ts`

```typescript
/**
 * useMarkdown — 将 Markdown 文本渲染为 HTML
 * 支持代码高亮、表格、GFM 语法
 */
import { marked, type Tokens } from 'marked'
import hljs from 'highlight.js'

// ── 配置 marked 渲染器 ──
const renderer = new marked.Renderer()

// 代码块高亮
renderer.code = function ({ text, lang }: Tokens.Code): string {
  const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
  const highlighted = hljs.highlight(text, { language: validLang }).value
  return `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`
}

// 行内代码
renderer.codespan = function ({ text }: Tokens.Codespan): string {
  return `<code class="inline-code">${text}</code>`
}

// 引用来源角标替换：[1] → <sup class="citation">[1]</sup>
// 注意：renderer 在 marked 新版本中 token 类型已变化，改用 post-processing
renderer.text = function (token: Tokens.Text | Tokens.Escape | Tokens.Tag): string {
  const text = 'text' in token ? token.text : token.raw
  // 将 Markdown 外的 [N] 替换为带样式的角标（保留已有 HTML）
  return text.replace(/(?<!<sup class="citation">)\[(\d+)\](?!<\/sup>)/g, '<sup class="citation">[$1]</sup>')
}

marked.setOptions({
  renderer,
  gfm: true,
  breaks: true,
})

export function useMarkdown() {
  function render(markdown: string): string {
    if (!markdown) return ''
    try {
      return marked.parse(markdown) as string
    } catch {
      return markdown
    }
  }

  return { render }
}
```

### 1.3 更新消息组件 `frontend\src\components\ChatMessage.vue`

用以下内容**替换** `frontend\src\components\ChatMessage.vue`：

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMarkdown } from '@/composables/useMarkdown'
import type { Message } from '@/types'

const props = defineProps<{
  message: Message
}>()

const { render } = useMarkdown()

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')

const renderedContent = computed(() => {
  return isAssistant.value ? render(props.message.content) : props.message.content
})

// 流式打字时禁用 Markdown 渲染（避免每帧都重新解析）
// 只在流式结束后做一次渲染
const displayContent = computed(() => {
  if (isAssistant.value) {
    return renderedContent.value
  }
  // 用户消息纯文本，转义 HTML
  return escapeHtml(props.message.content)
})

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
</script>

<template>
  <div class="message" :class="{ user: isUser, assistant: isAssistant }">
    <div class="role-label">{{ isUser ? '你' : 'DocsChat' }}</div>
    <div class="content">
      <!-- 用户消息：纯文本 -->
      <div v-if="isUser" class="text" v-text="displayContent"></div>

      <!-- AI 消息：Markdown 渲染 -->
      <div
        v-else
        class="text markdown-body"
        v-html="displayContent"
      ></div>

      <!-- 引用来源 -->
      <div v-if="message.sources.length > 0" class="sources">
        <span class="sources-label">参考来源：</span>
        <span
          v-for="source in message.sources"
          :key="source.index"
          class="source-badge"
        >
          [{{ source.index }}]
          <span class="source-tooltip">
            <div class="tooltip-header">
              {{ source.documentName || '未知文档' }}
              <span v-if="source.page">· 第 {{ source.page }} 页</span>
            </div>
            <div class="tooltip-body">{{ source.content }}</div>
            <div class="tooltip-score">相关度: {{ (source.relevanceScore * 100).toFixed(1) }}%</div>
          </span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  flex-direction: column;
  padding: 1rem 1.5rem;
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
  margin-bottom: 0.4rem;
}

.content {
  line-height: 1.75;
}

.text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Markdown 渲染样式 ── */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 1rem 0 0.5rem;
  font-weight: 700;
  color: var(--ink);
}

.markdown-body :deep(h1) { font-size: 1.3rem; }
.markdown-body :deep(h2) { font-size: 1.15rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.25rem; }
.markdown-body :deep(h3) { font-size: 1.05rem; }

.markdown-body :deep(p) {
  margin: 0.5rem 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.5rem 0;
}

.markdown-body :deep(li) {
  margin: 0.25rem 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding: 0.25rem 1rem;
  margin: 0.75rem 0;
  color: var(--muted);
  background: rgba(88, 166, 255, 0.05);
  border-radius: 0 4px 4px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.85rem;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--rule);
  padding: 0.4rem 0.75rem;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--bg);
  font-weight: 600;
}

.markdown-body :deep(strong) {
  font-weight: 700;
  color: var(--ink);
}

.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* ── 行内代码 ── */
:deep(.inline-code) {
  background: rgba(88, 166, 255, 0.1);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Consolas', 'Courier New', monospace;
}

/* ── 代码块（highlight.js） ── */
:deep(pre) {
  background: #0d1117;
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 0;
  margin: 0.75rem 0 1rem;
  overflow-x: auto;
  position: relative;
}

:deep(pre::before) {
  content: attr(data-lang);
  position: absolute;
  top: 0;
  right: 0;
  padding: 2px 10px;
  font-size: 0.7rem;
  color: var(--muted);
  background: var(--bg2);
  border-radius: 0 8px 0 4px;
}

:deep(pre code) {
  display: block;
  padding: 1rem 1.25rem;
  font-size: 0.85rem;
  line-height: 1.6;
  font-family: 'Consolas', 'Courier New', monospace;
  overflow-x: auto;
}

:deep(pre code.hljs) {
  background: transparent;
  color: #e6edf3;
}

/* ── 引用角标 ── */
:deep(sup.citation) {
  color: var(--accent);
  font-weight: 700;
  font-size: 0.78em;
  cursor: pointer;
  margin: 0 1px;
  vertical-align: super;
  transition: background 0.15s;
  padding: 0 2px;
  border-radius: 2px;
}

:deep(sup.citation:hover) {
  background: rgba(88, 166, 255, 0.15);
}

/* ── 来源引用悬浮卡片 ── */
.sources {
  margin-top: 1rem;
  padding-top: 0.65rem;
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
  bottom: 130%;
  left: 50%;
  transform: translateX(-50%);
  width: 320px;
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--ink);
  white-space: normal;
  word-break: break-word;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.source-badge:hover .source-tooltip {
  display: block;
}

.tooltip-header {
  padding: 0.5rem 0.75rem;
  background: var(--bg2);
  border-bottom: 1px solid var(--rule);
  font-weight: 600;
  font-size: 0.78rem;
  color: var(--accent);
}

.tooltip-body {
  padding: 0.65rem 0.75rem;
  line-height: 1.6;
  max-height: 180px;
  overflow-y: auto;
}

.tooltip-score {
  padding: 0.35rem 0.75rem;
  background: var(--bg2);
  border-top: 1px solid var(--rule);
  font-size: 0.72rem;
  color: var(--accent2);
}
</style>
```

### 1.4 创建虚拟滚动 Hook `frontend\src\composables\useVirtualScroll.ts`

```typescript
/**
 * useVirtualScroll — 虚拟滚动管理
 * 在消息列表过长时只渲染可视区域，避免 DOM 节点过多导致卡顿
 */
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

export interface VirtualScrollOptions {
  /** 每项估计高度 (px) */
  itemHeight: number
  /** 缓冲区项数（渲染区外的额外项） */
  overscan: number
}

export function useVirtualScroll(
  containerRef: Ref<HTMLElement | null>,
  totalItems: Ref<number>,
  options: VirtualScrollOptions = { itemHeight: 80, overscan: 5 },
) {
  const { itemHeight, overscan } = options

  const scrollTop = ref(0)
  const containerHeight = ref(0)

  // 可视区域能容纳的项数
  const visibleCount = computed(() => Math.ceil(containerHeight.value / itemHeight) + overscan * 2)

  // 起始索引
  const startIndex = computed(() => {
    const raw = Math.floor(scrollTop.value / itemHeight) - overscan
    return Math.max(0, raw)
  })

  // 结束索引
  const endIndex = computed(() => {
    const raw = startIndex.value + visibleCount.value
    return Math.min(totalItems.value, raw)
  })

  // 可见项索引范围
  const visibleRange = computed(() => ({
    start: startIndex.value,
    end: endIndex.value,
  }))

  // 总高度偏移（上方隐藏项的高度）
  const offsetY = computed(() => startIndex.value * itemHeight)

  function onScroll(event: Event) {
    scrollTop.value = (event.target as HTMLElement).scrollTop
  }

  function updateContainerHeight() {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
    }
  }

  onMounted(() => {
    updateContainerHeight()
    window.addEventListener('resize', updateContainerHeight)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', updateContainerHeight)
  })

  return {
    scrollTop,
    containerHeight,
    visibleRange,
    offsetY,
    totalHeight: computed(() => totalItems.value * itemHeight),
    onScroll,
  }
}
```

### 1.5 验证 Markdown 渲染

启动前端后发送包含以下内容的消息：

```
帮我写一个 Python 快速排序

```python
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
```
```

应看到代码高亮效果（Python 关键字彩色，背景深色终端风格）。

---

## 第二部分：文档上传前端 + 错误边界（下午 3h）

### 2.1 创建文件上传组件 `frontend\src\components\DocumentUploader.vue`

```vue
<script setup lang="ts">
import { ref } from 'vue'
import api from '@/utils/api'
import type { DocumentMeta } from '@/types'

const emit = defineEmits<{
  uploaded: [doc: DocumentMeta]
}>()

const isUploading = ref(false)
const error = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    error.value = '仅支持 PDF 文件'
    return
  }

  isUploading.value = true
  error.value = null

  try {
    const formData = new FormData()
    formData.append('file', file)

    const { data } = await api.post<DocumentMeta>('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000, // 大文件上传可能需要较长时间
    })

    emit('uploaded', data)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || (e as Error).message
      || '上传失败'
    error.value = msg
  } finally {
    isUploading.value = false
    // 重置 input 以支持重复上传同一文件
    if (fileInput.value) fileInput.value.value = ''
  }
}

function triggerUpload() {
  fileInput.value?.click()
}
</script>

<template>
  <div class="uploader">
    <input
      ref="fileInput"
      type="file"
      accept=".pdf"
      style="display:none"
      @change="handleFileChange"
    />

    <button
      class="upload-btn"
      :disabled="isUploading"
      @click="triggerUpload"
    >
      {{ isUploading ? '上传中...' : '上传 PDF' }}
    </button>

    <div v-if="error" class="upload-error">
      {{ error }}
      <button class="dismiss-btn" @click="error = null">关闭</button>
    </div>
  </div>
</template>

<style scoped>
.uploader {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.upload-btn {
  padding: 0.45rem 1rem;
  background: var(--bg2);
  color: var(--accent);
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.2s;
}

.upload-btn:hover:not(:disabled) {
  background: var(--rule);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.65rem;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid var(--danger);
  border-radius: 6px;
  color: var(--danger);
  font-size: 0.8rem;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--danger);
  font-weight: 600;
  cursor: pointer;
  font-size: 0.8rem;
}
</style>
```

### 2.2 创建错误边界组件 `frontend\src\components\ErrorBoundary.vue`

```vue
<script setup lang="ts">
/**
 * ErrorBoundary — 捕获子组件渲染错误，防止整个应用崩溃
 *
 * 面试要点: Vue 中 errorBoundary 通过 onErrorCaptured 实现，
 * 这是 Vue3 的新增功能，体现对框架深入理解。
 */
import { ref, onErrorCaptured } from 'vue'

const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err: Error, instance, info) => {
  console.error('[ErrorBoundary]', err, info)
  hasError.value = true
  errorMessage.value = err.message || '未知错误'
  return false // 阻止错误继续向上冒泡
})

function retry() {
  hasError.value = false
  errorMessage.value = ''
}
</script>

<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-icon">!</div>
    <h3>页面出错了</h3>
    <p>{{ errorMessage }}</p>
    <button @click="retry">重试</button>
  </div>
  <slot v-else />
</template>

<style scoped>
.error-boundary {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  text-align: center;
  padding: 2rem;
}

.error-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(248, 81, 73, 0.15);
  color: var(--danger);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  font-weight: 800;
  margin-bottom: 1rem;
}

.error-boundary h3 {
  font-size: 1.2rem;
  margin-bottom: 0.5rem;
}

.error-boundary p {
  color: var(--muted);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
  max-width: 400px;
}

.error-boundary button {
  padding: 0.5rem 1.5rem;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
</style>
```

### 2.3 更新 ChatView 加入上传和错误边界 `frontend\src\views\ChatView.vue`

用以下内容**替换** `frontend\src\views\ChatView.vue`：

```vue
<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { useConversationStore } from '@/stores/conversation'
import { useMessageStore } from '@/stores/message'
import { useSSE } from '@/composables/useSSE'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import MessageInput from '@/components/MessageInput.vue'
import DocumentUploader from '@/components/DocumentUploader.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import type { Message, DocumentMeta } from '@/types'

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
const uploadedDocs = ref<DocumentMeta[]>([])

// 当前会话的消息列表
const currentMessages = ref<Message[]>([])

const hasDocuments = computed(() => uploadedDocs.value.length > 0)

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

// 流式内容更新 → 实时写入 assistant 消息
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
  if (!conversationStore.activeId) {
    await conversationStore.createConversation('新对话')
  }

  const convId = conversationStore.activeId!
  isSending.value = true

  assistantMsgId.value = await messageStore.sendMessage(convId, text)
  currentMessages.value = messageStore.getMessages(convId)

  await nextTick()
  scrollToBottom()

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

function handleDocumentUploaded(doc: DocumentMeta) {
  uploadedDocs.value.push(doc)
}

function scrollToBottom() {
  nextTick(() => {
    if (messageContainer.value) {
      messageContainer.value.scrollTop = messageContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  if (!conversationStore.activeId) {
    conversationStore.createConversation('新对话')
  }
})
</script>

<template>
  <div class="chat-layout">
    <ConversationSidebar />

    <main class="chat-main">
      <ErrorBoundary>
        <!-- 顶部栏 -->
        <header class="chat-header">
          <div class="header-left">
            <h2>{{ conversationStore.activeConversation?.title || 'DocsChat' }}</h2>
            <span v-if="hasDocuments" class="doc-badge">
              知识库: {{ uploadedDocs.length }} 篇文档
            </span>
          </div>
          <div class="header-right">
            <DocumentUploader @uploaded="handleDocumentUploaded" />
            <button
              v-if="isStreaming"
              class="abort-btn"
              @click="handleAbort"
            >
              停止生成
            </button>
          </div>
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

          <!-- 空状态 -->
          <div v-if="currentMessages.length === 0 && !isStreaming" class="empty-state">
            <h3>DocsChat</h3>
            <p>上传 PDF 文档并开始提问，我会基于文档内容为你解答</p>
            <p class="empty-hint">
              支持 Markdown 格式回答、代码高亮、来源引用标注
            </p>
          </div>
        </div>

        <!-- 输入区域 -->
        <MessageInput
          v-model:is-sending="isSending"
          @send="handleSend"
        />
      </ErrorBoundary>
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
  padding: 0.65rem 1.5rem;
  border-bottom: 1px solid var(--rule);
  background: var(--bg);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.header-left h2 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--ink);
}
.doc-badge {
  font-size: 0.75rem;
  color: var(--accent2);
  background: rgba(63, 185, 80, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.abort-btn {
  padding: 0.45rem 1rem;
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
  padding: 0;
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
  font-weight: 600;
  cursor: pointer;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
  padding: 2rem;
}
.empty-state h3 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 0.75rem;
}
.empty-state p {
  color: var(--muted);
  font-size: 0.95rem;
}
.empty-hint {
  margin-top: 0.5rem;
  font-size: 0.85rem !important;
}
</style>
```

### 2.4 更新全局样式 `frontend\src\App.vue`

用以下内容**替换** `frontend\src\App.vue`（在原来基础上增加代码高亮主题样式）：

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

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }

/* ── highlight.js GitHub Dark 主题适配 ── */
.hljs { color: #e6edf3; background: #0d1117; }
.hljs-keyword,
.hljs-selector-tag,
.hljs-literal,
.hljs-section,
.hljs-link { color: #ff7b72; }

.hljs-string,
.hljs-title,
.hljs-name,
.hljs-type,
.hljs-attribute,
.hljs-symbol,
.hljs-bullet,
.hljs-addition,
.hljs-variable,
.hljs-template-tag,
.hljs-template-variable { color: #a5d6ff; }

.hljs-comment,
.hljs-quote,
.hljs-deletion,
.hljs-meta { color: #8b949e; }

.hljs-number,
.hljs-regexp,
.hljs-literal,
.hljs-built_in { color: #79c0ff; }

.hljs-function .hljs-title,
.hljs-title.function_,
.hljs-title.class_,
.hljs-attr,
.hljs-params { color: #d2a8ff; }

.hljs-class .hljs-title { color: #ffa657; }

.hljs-attr,
.hljs-selector-attr,
.hljs-selector-class,
.hljs-selector-pseudo { color: #79c0ff; }

.hljs-tag { color: #7ee787; }
.hljs-tag .hljs-name { color: #7ee787; }
.hljs-tag .hljs-attr { color: #79c0ff; }

/* ── 选择文字颜色 ── */
::selection {
  background: rgba(88, 166, 255, 0.25);
}
</style>
```

### 2.5 安装 highlight.js CSS

highlight.js 的主题样式已经内联在 App.vue 中了，无需额外引入 CSS 文件。如果你希望使用其他主题，可以从 `node_modules/highlight.js/styles/` 复制。

---

## 第三部分：RAGAS 评估 + Reranker 集成（晚间 2h）

### 3.1 创建 RAGAS 评估脚本 `backend\scripts\evaluate_rag.py`

```python
"""
RAGAS 评估脚本 —— 量化 RAG 系统的检索和生成质量

运行方式:
    cd backend
    python scripts/evaluate_rag.py

需要先上传文档并准备好评估数据集。

评估指标:
- Context Recall: 检索到的上下文覆盖了多少参考答案
- Faithfulness: 生成的回答是否忠于检索到的上下文
- Answer Relevance: 生成的回答与问题的相关度

面试要点: 能解释为什么需要 RAGAS ——
没有量化评估就无法知道"改了一个参数后是好还是坏"，
面试官看到你有评估意识会觉得你有工程思维。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
import asyncio
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    context_recall,
    faithfulness,
    answer_relevancy,
)

from app.services.retrieval_service import retrieval_service
from app.services.llm_service import llm_service
from app.services.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── 评估数据集 ──
# 格式: { "question": "问题", "ground_truth": "参考答案" }
# 手动构建 10-20 组问答对，用于评估检索和生成质量
EVAL_DATASET = [
    {
        "question": "这个文档主要讲了什么内容？",
        "ground_truth": "（手动填写正确答案，基于你的测试文档）",
    },
    {
        "question": "文档中提到了哪些关键概念？",
        "ground_truth": "（手动填写正确答案）",
    },
    # TODO: 补充更多问答对（建议 10-20 组）
]


async def run_evaluation():
    """运行 RAGAS 评估"""

    if vector_store.get_chunk_count() == 0:
        logger.error("向量库为空！请先上传 PDF 文档。")
        return

    if retrieval_service.bm25 is None:
        logger.error("BM25 索引未构建！请先上传 PDF 文档。")
        return

    logger.info(f"开始 RAGAS 评估: {len(EVAL_DATASET)} 组问答对")

    questions = []
    answers = []
    contexts_list = []
    ground_truths = []

    for item in EVAL_DATASET:
        question = item["question"]
        ground_truth = item["ground_truth"]

        logger.info(f"评估中: {question}")

        # ── 1. 检索上下文 ──
        retrieval_results = retrieval_service.search(question, top_k=5)
        contexts = [r["content"] for r in retrieval_results]

        # ── 2. 生成回答 ──
        context_text = "\n\n".join(contexts)
        prompt = f"""基于以下参考文档回答问题。
参考文档:
{context_text}

问题: {question}

回答:"""

        answer = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
        )

        questions.append(question)
        answers.append(answer)
        contexts_list.append(contexts)
        ground_truths.append([ground_truth])  # RAGAS 要求 list of list

    # ── 3. 构建 Dataset 并评估 ──
    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    })

    logger.info("运行 RAGAS 评估...")
    result = evaluate(
        dataset,
        metrics=[context_recall, faithfulness, answer_relevancy],
    )

    # ── 4. 输出结果 ──
    print("\n" + "=" * 60)
    print("RAGAS 评估结果")
    print("=" * 60)
    for metric, value in result.items():
        score = round(float(value), 4)
        print(f"  {metric:.<30} {score:.4f}")

    # 导出为 JSON（用于简历量化数据）
    output_path = os.path.join(os.path.dirname(__file__), "..", "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({k: round(float(v), 4) for k, v in result.items()}, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_path}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    asyncio.run(run_evaluation())
```

### 3.2 创建 Reranker 服务 `backend\app\services\reranker_service.py`

```python
"""Reranker 重排序服务 —— 在混合检索后对结果做精排

面试要点: 能解释 Reranker 为什么重要 ——
混合检索的 RRF 融合是无监督的，无法利用语义信息进行精细排序。
Reranker 使用 Cross-Encoder 结构，将 query 和 document 同时输入模型，
逐对计算相关性分数，精度远高于 Bi-Encoder（Embedding 模型）。

本实现使用 sentence-transformers 的 CrossEncoder。
"""
import logging
from typing import List
from sentence_transformers import CrossEncoder
from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """
    使用 BGE-Reranker-v2-m3 对检索结果做精排。

    模型规模:
    - BGE-Reranker-v2-m3: ~568M 参数，中文效果优秀
    - 推理速度: ~50 docs/s (CPU), ~500 docs/s (GPU)

    选型理由: 开源可本地部署、中文效果好、延迟可控。
    备选: Cohere Rerank API（商业方案，精度更高但需付费）。
    """

    def __init__(self):
        self.model: CrossEncoder | None = None
        self.model_name = settings.RERANKER_MODEL
        self._loaded = False

    def _lazy_load(self):
        """延迟加载模型（首次使用时下载，约 2.2GB）"""
        if not self._loaded:
            logger.info(f"加载 Reranker 模型: {self.model_name}")
            self.model = CrossEncoder(
                self.model_name,
                max_length=512,
            )
            self._loaded = True
            logger.info("Reranker 模型加载完成")

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: int | None = None,
    ) -> List[dict]:
        """
        对候选文档做精排。

        Args:
            query: 查询文本
            documents: 候选文档列表，每项需包含 content 字段
            top_k: 返回数量（默认从配置读取）

        Returns:
            重排序后的文档列表，score 更新为 Reranker 分数
        """
        self._lazy_load()
        top_k = top_k or settings.RERANKER_TOP_K

        if not documents:
            return []

        # ── 准备输入对 ──
        pairs = [[query, doc["content"]] for doc in documents]

        # ── 计算分数 ──
        scores = self.model.predict(pairs, show_progress_bar=False)

        # ── 按分数排序 ──
        for i, doc in enumerate(documents):
            doc["score"] = float(scores[i])

        ranked = sorted(documents, key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]


# 全局单例
reranker = RerankerService()
```

### 3.3 更新 retrieval_service.py 加入 Reranker

在 `backend\app\services\retrieval_service.py` 的 `search` 方法末尾加入 Reranker 调用。找到文件的最后部分，在 `search` 方法的 `return merged` 之前插入 Reranker 逻辑。

用以下内容**替换** `search` 方法（只替换方法，保留类的其余部分）：

```python
    def search(self, query: str, top_k: int | None = None, use_reranker: bool = True) -> List[dict]:
        """
        混合检索 —— 向量 + BM25 → RRF 融合 → (可选) Reranker 精排。

        Args:
            query: 查询文本
            top_k: 最终返回数量
            use_reranker: 是否使用 Reranker 精排（默认开启）

        Returns:
            排序后的检索结果
        """
        top_k = top_k or settings.RERANKER_TOP_K

        # ── 1. 向量语义检索 ──
        vector_results = vector_store.search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"向量检索: {len(vector_results)} 条结果")

        # ── 2. BM25 关键词检索 ──
        bm25_results = self._bm25_search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"BM25 检索: {len(bm25_results)} 条结果")

        # ── 3. RRF 融合 ──
        merged = self._rrf_fusion(vector_results, bm25_results, top_k=top_k * 2)
        logger.info(f"RRF 融合: {len(merged)} 条结果")

        # ── 4. Reranker 精排（可选） ──
        if use_reranker and merged:
            try:
                from app.services.reranker_service import reranker
                merged = reranker.rerank(query, merged, top_k=top_k)
                logger.info(f"Reranker 精排: {len(merged)} 条结果")
            except ImportError:
                logger.warning("Reranker 模型未安装，跳过精排")
                merged = merged[:top_k]
        else:
            merged = merged[:top_k]

        return merged
```

### 3.4 安装 Reranker 依赖（首次运行自动下载模型约 2.2GB）

```powershell
cd E:\docs-chat\backend
# sentence-transformers 已在 requirements.txt 中
# 检查是否已安装
python -c "from sentence_transformers import CrossEncoder; print('Reranker OK')"
```

---

## 第四部分：验收与验证

### 4.1 验收清单

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | Markdown 渲染 | 发送包含标题/列表/粗体的问题 | 渲染为格式化 HTML |
| 2 | 代码高亮 | 发送包含代码块的问题 | Python/JS 等代码彩色高亮 |
| 3 | 表格渲染 | 发送包含 Markdown 表格的问题 | 表格格式正确 |
| 4 | 文件上传 | 点击"上传 PDF"按钮选择文件 | 上传成功，顶部显示文档数 |
| 5 | 来源悬浮卡片 | 上传文档后提问，鼠标悬浮 [1] | 显示文档名、页码、原文、相关度 |
| 6 | 错误边界 | 故意在组件中制造错误 | 显示"页面出错了"而非白屏 |
| 7 | SSE 中断重试 | 生成过程中点击"停止生成" | 流式传输立即中断 |
| 8 | RAGAS 评估 | 运行 `scripts/evaluate_rag.py` | 输出 Context Recall 等指标 |
| 9 | Reranker 生效 | 发送问题，查看后端日志 | 日志显示 "Reranker 精排: N 条结果" |

### 4.2 常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| Markdown 不渲染 | `marked` 未安装 | `npm install marked && npm install -D @types/marked` |
| 代码无高亮 | `highlight.js` 未安装 | `npm install highlight.js` |
| 来源卡片不显示 | `sources` 数组为空 | 确认已上传文档且检索返回结果 |
| RAGAS 报 `datasets` 错误 | `datasets` 未安装 | `pip install datasets` |
| Reranker 下载慢 | 首次下载 ~2.2GB 模型 | 等待完成，或改为 Day 5 再启用 |
| 上传按钮无反应 | 未引入 `DocumentUploader` | 确认 ChatView 中已 import 该组件 |

### 4.3 RAGAS 评估前置准备

在运行评估脚本前，需要手动标注 10-20 组问答对。建议：

1. 先上传你的测试 PDF 文档
2. 手动提出 10-20 个问题
3. 根据文档内容写出正确答案（ground_truth）
4. 填入 `evaluate_rag.py` 的 `EVAL_DATASET` 列表
5. 运行 `python scripts/evaluate_rag.py`

输出示例：
```
============================================================
RAGAS 评估结果
============================================================
  context_recall............... 0.7820
  faithfulness................. 0.8540
  answer_relevancy............. 0.8010

结果已保存到: evaluation_results.json
============================================================
```

这份数据可以直接写进简历：**"通过 RAGAS 评估框架量化检索与生成质量，Context Recall 达到 0.78，Faithfulness 达到 0.85。"**

---

## Day 3 完成标志

- 对话中 Markdown 代码块有语法高亮
- 上传 PDF 后提问，回答中 [1][2] 角标可悬浮查看原文
- 错误边界组件能捕获子组件崩溃
- RAGAS 评估脚本输出量化指标
- Reranker 在检索链路中生效（后端日志可见）

完成后，项目结构新增/更新：

```
docs-chat/
├── backend/
│   ├── app/
│   │   └── services/
│   │       ├── retrieval_service.py   ← 更新（加入 Reranker）
│   │       └── reranker_service.py    ← 新增
│   └── scripts/
│       └── evaluate_rag.py            ← 新增
└── frontend/
    └── src/
        ├── App.vue                     ← 更新（代码高亮主题）
        ├── components/
        │   ├── ChatMessage.vue         ← 更新（Markdown 渲染 + 来源卡片美化）
        │   ├── DocumentUploader.vue    ← 新增
        │   └── ErrorBoundary.vue       ← 新增
        ├── composables/
        │   ├── useMarkdown.ts          ← 新增
        │   └── useVirtualScroll.ts     ← 新增
        └── views/
            └── ChatView.vue            ← 更新（上传 + 错误边界）
```

### Day 3 面试准备要点

1. **为什么要在对话中做 Markdown 渲染？** 大模型经常返回包含代码、表格、列表的回答，纯文本展示可读性差。`marked` + `highlight.js` 是前端处理 AI 生成内容的标准方案。
2. **Error Boundary 的原理？** 使用 Vue3 的 `onErrorCaptured` 钩子捕获子组件渲染错误，返回 `false` 阻止冒泡。React 中有 `componentDidCatch`，Vue3 在这一点上是追赶对齐的。
3. **RAGAS 的三个指标分别衡量什么？** Context Recall 衡量检索环节是否找对了信息，Faithfulness 衡量生成内容是否忠于检索结果（不编造），Answer Relevance 衡量回答是否切题。三者分别对应检索质量、生成质量、整体相关性。
4. **Reranker 和 Embedding 模型的区别？** Embedding 是 Bi-Encoder（分别编码 query 和 doc），速度快但精度有限。Reranker 是 Cross-Encoder（同时编码 query 和 doc），精度高但速度慢。实际工程中两者配合：Bi-Encoder 粗筛 → Cross-Encoder 精排。

完成后告诉我，进入 Day 4：组件单元测试 + Docker 容器化 + 性能优化。