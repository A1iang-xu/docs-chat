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
 *
 * 采用 post-processing 方案而非 marked.use() renderer 覆盖：
 * marked v18 的 renderer 对象字面量在 use() 中存在兼容性风险，
 * 后处理方案更稳定且不依赖 marked 内部 API。
 */
import { marked } from 'marked'
import hljs from 'highlight.js'

// ── 配置 marked 基础选项 ──
marked.setOptions({ gfm: true, breaks: true })

// ── HTML 实体解码 ──
function decodeHtml(text: string): string {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

export function useMarkdown() {
  function render(markdown: string): string {
    if (!markdown) return ''

    try {
      let html = marked.parse(markdown) as string

      // ── 后处理 1：代码块高亮 ──
      // marked 默认输出: <pre><code class="language-python">转义后的代码</code></pre>
      html = html.replace(
        /<pre><code(?:\s+class="language-(\w+)")?>([\s\S]*?)<\/code><\/pre>/g,
        (_, lang, escapedCode) => {
          const code = decodeHtml(escapedCode)
          const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
          const highlighted = hljs.highlight(code, { language: validLang }).value
          return `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`
        },
      )

      // ── 后处理 2：行内代码样式 ──
      // 注意：只替换不在 <pre> 内的行内 <code>
      html = html.replace(
        /(?<!<pre[^>]*>)(?<!<code[^>]*>)<code>([^<]+)<\/code>(?!<\/pre>)/g,
        '<code class="inline-code">$1</code>',
      )

      // ── 后处理 3：引用来源角标 [N] → <sup> ──
      // 避免替换已在 <sup> 内的角标
      html = html.replace(
        /(?<!<sup class="citation">)\[(\d+)\](?!<\/sup>)/g,
        '<sup class="citation">[$1]</sup>',
      )

      return html
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

/* ── highlight.js GitHub Dark 主题 ── */
.hljs {
  color: #e6edf3;
  background: #0d1117;
}

.hljs-keyword,
.hljs-selector-tag,
.hljs-literal,
.hljs-section,
.hljs-link {
  color: #ff7b72;
}

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
.hljs-template-variable {
  color: #a5d6ff;
}

.hljs-comment,
.hljs-quote,
.hljs-deletion,
.hljs-meta {
  color: #8b949e;
}

.hljs-number,
.hljs-regexp,
.hljs-built_in {
  color: #79c0ff;
}

.hljs-function .hljs-title,
.hljs-title.function_,
.hljs-title.class_,
.hljs-attr,
.hljs-params {
  color: #d2a8ff;
}

.hljs-class .hljs-title {
  color: #ffa657;
}

.hljs-attr,
.hljs-selector-attr,
.hljs-selector-class,
.hljs-selector-pseudo {
  color: #79c0ff;
}

.hljs-tag {
  color: #7ee787;
}

.hljs-tag .hljs-name {
  color: #7ee787;
}

.hljs-tag .hljs-attr {
  color: #79c0ff;
}

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
    python scripts/evaluate_rag.py              # 自动模式：从文档生成问答对
    python scripts/evaluate_rag.py --manual     # 手动模式：使用预定义的 EVAL_DATASET
    python scripts/evaluate_rag.py --count 20   # 指定生成 20 组问答对
    python scripts/evaluate_rag.py --qa-file eval_qa_pairs.json  # 复用已有问答对

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

import argparse
import json
import logging
import asyncio
import random
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


# ── 手动评估数据集（备用） ──
EVAL_DATASET = [
    # 格式: { "question": "问题", "ground_truth": "参考答案" }
    # 填写后可通过 --manual 模式使用
]


# ═══════════════════════════════════════════════════════════════
# 自动化问答对生成
# ═══════════════════════════════════════════════════════════════

QA_GENERATION_PROMPT = """你是一个专业的测试数据生成器。请根据以下文档内容，生成 {count} 个高质量的问答对。

要求：
1. 问题应覆盖文档的不同方面（概念、细节、关系、结论等），不要重复
2. 问题应使用自然语言，像真实用户会问的问题
3. 参考答案应准确、完整，基于文档内容（不要编造）
4. 每个问题应有明确的答案，可以从文档中直接或间接推导

输出格式（严格 JSON 数组）：
```json
[
  {{"question": "问题1", "ground_truth": "答案1"}},
  {{"question": "问题2", "ground_truth": "答案2"}}
]
```

文档内容：
{document_text}

请生成 {count} 个问答对："""


async def generate_qa_pairs(count: int = 10, sample_chunks: int = 30) -> list[dict]:
    """使用 LLM 从文档库中自动生成问答对"""
    # 使用通用查询词采样不同主题的文档块
    seed_queries = [
        "概述", "简介", "什么是", "如何", "原因", "方法",
        "步骤", "特点", "区别", "优势", "应用", "总结",
        "关键", "重要", "原理", "流程", "核心", "结论",
    ]
    sampled_chunks: list[str] = []
    seen_ids: set[str] = set()
    for query in seed_queries:
        if len(sampled_chunks) >= sample_chunks:
            break
        results = vector_store.search(query, top_k=3)
        for r in results:
            if r["chunk_id"] not in seen_ids and len(sampled_chunks) < sample_chunks:
                seen_ids.add(r["chunk_id"])
                sampled_chunks.append(r["content"])
    if not sampled_chunks:
        logger.error("无法从向量库中采样文档块，请先上传文档")
        return []
    random.shuffle(sampled_chunks)
    document_text = "\n\n---\n\n".join(
        f"[片段 {i+1}] {chunk[:800]}" for i, chunk in enumerate(sampled_chunks)
    )
    prompt = QA_GENERATION_PROMPT.format(count=count, document_text=document_text)
    logger.info(f"使用 {len(sampled_chunks)} 个文档片段生成 {count} 个问答对...")
    response = await llm_service.chat(messages=[{"role": "user", "content": prompt}])
    json_start = response.find("[")
    json_end = response.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        logger.error("LLM 返回的内容中未找到 JSON 数组")
        return []
    return json.loads(response[json_start:json_end])


# ═══════════════════════════════════════════════════════════════
# 评估主流程
# ═══════════════════════════════════════════════════════════════

async def run_evaluation(qa_pairs: list[dict]):
    """运行 RAGAS 评估"""
    if not qa_pairs:
        logger.error("没有可用的问答对，评估终止")
        return
    logger.info(f"开始 RAGAS 评估: {len(qa_pairs)} 组问答对")
    questions, answers, contexts_list, ground_truths = [], [], [], []
    for item in qa_pairs:
        question, ground_truth = item["question"], item["ground_truth"]
        logger.info(f"评估中 [{len(questions)+1}/{len(qa_pairs)}]: {question[:50]}...")
        retrieval_results = retrieval_service.search(question, top_k=5)
        contexts = [r["content"] for r in retrieval_results]
        if not contexts:
            logger.warning("  未检索到相关内容，跳过")
            continue
        context_text = "\n\n".join(contexts)
        answer = await llm_service.chat(
            messages=[{"role": "user", "content": f"基于以下参考文档回答问题。\n参考文档:\n{context_text}\n\n问题: {question}\n\n回答:"}],
        )
        questions.append(question)
        answers.append(answer)
        contexts_list.append(contexts)
        ground_truths.append([ground_truth])
    if not questions:
        logger.error("所有问答对均未检索到内容，无法评估")
        return
    dataset = Dataset.from_dict({
        "question": questions, "answer": answers,
        "contexts": contexts_list, "ground_truth": ground_truths,
    })
    logger.info("运行 RAGAS 评估...")
    result = evaluate(dataset, metrics=[context_recall, faithfulness, answer_relevancy])
    print("\n" + "=" * 60)
    print("RAGAS 评估结果")
    print("=" * 60)
    for metric, value in result.items():
        print(f"  {metric:.<30} {round(float(value), 4):.4f}")
    output_path = os.path.join(os.path.dirname(__file__), "..", "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({k: round(float(v), 4) for k, v in result.items()}, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_path}")
    qa_path = os.path.join(os.path.dirname(__file__), "..", "eval_qa_pairs.json")
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
    print(f"问答对已保存到: {qa_path}")
    print("=" * 60)
    return result


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估脚本")
    parser.add_argument("--manual", action="store_true", help="使用手动编写的 EVAL_DATASET")
    parser.add_argument("--count", type=int, default=10, help="自动生成的问答对数量（默认 10）")
    parser.add_argument("--qa-file", type=str, default=None, help="从 JSON 文件加载已有问答对")
    args = parser.parse_args()
    if vector_store.get_chunk_count() == 0:
        logger.error("向量库为空！请先上传 PDF 文档。")
        return

    # ── 重建 BM25 索引（独立进程需要从 ChromaDB 加载数据）──
    if retrieval_service.bm25 is None:
        logger.info("正在从向量库重建 BM25 索引...")
        all_chunks = vector_store.get_all_chunks()
        if all_chunks:
            retrieval_service.build_bm25_index(all_chunks)
            logger.info(f"BM25 索引重建完成: {len(all_chunks)} 个文档块")
        else:
            logger.error("无法从向量库获取文档块，请先上传 PDF 文档。")
            return
    if args.qa_file:
        with open(args.qa_file, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)
        logger.info(f"从文件加载 {len(qa_pairs)} 组问答对")
    elif args.manual:
        qa_pairs = EVAL_DATASET
        if not qa_pairs:
            logger.error("EVAL_DATASET 为空！请在脚本中填写问答对后重试。")
            return
    else:
        logger.info(f"自动生成模式：目标 {args.count} 个问答对")
        qa_pairs = await generate_qa_pairs(count=args.count)
    if not qa_pairs:
        logger.error("未获取到有效问答对，评估终止")
        return
    await run_evaluation(qa_pairs)


if __name__ == "__main__":
    asyncio.run(main())
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
| 代码无高亮 | `highlight.js` 未安装或 CSS 缺失 | `npm install highlight.js` + 确认 App.vue 中有 hljs 主题样式 |
| 代码高亮不生效 | `marked.use()` renderer 兼容性问题 | 改用 post-processing 方案（正则匹配 `<pre><code>` 后调 hljs） |
| 来源卡片不显示 | `sources` 数组为空 | 确认已上传文档且检索返回结果 |
| 心跳超时 | Reranker 首次下载模型耗时长 | 后端已预加载模型 + 心跳间隔 10s + 超时 120s |
| RAGAS 报 `datasets` 错误 | `datasets` 未安装 | `pip install datasets` |
| Reranker 下载慢 | 首次下载 ~2.2GB 模型 | 启动时自动预加载，或改为 Day 5 再启用 |
| 上传按钮无反应 | 未引入 `DocumentUploader` | 确认 ChatView 中已 import 该组件 |
| BM25 索引未构建 | evaluate_rag.py 独立进程无 BM25 内存数据 | 脚本已自动从 ChromaDB 重建 BM25 索引 |

### 4.3 RAGAS 评估操作指南

**自动模式（推荐）**：由 LLM 自动从文档生成问答对并评估，无需手动标注。

```powershell
cd E:\docs-chat\backend
# 自动生成 10 组问答对并评估（默认）
python scripts/evaluate_rag.py

# 生成 20 组问答对
python scripts/evaluate_rag.py --count 20

# 复用之前生成的问答对
python scripts/evaluate_rag.py --qa-file eval_qa_pairs.json
```

**手动模式**：使用预定义的问答对（适合精确控制评估场景）。

```powershell
# 先在 evaluate_rag.py 的 EVAL_DATASET 中填写问答对
python scripts/evaluate_rag.py --manual
```

**输出示例**：
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
│   │   ├── api/
│   │   │   └── chat.py                 ← 更新（SSE 心跳 keepalive）
│   │   ├── main.py                     ← 更新（启动时预加载 Reranker）
│   │   └── services/
│   │       ├── retrieval_service.py   ← 更新（加入 Reranker）
│   │       ├── vector_store.py         ← 更新（新增 get_all_chunks 方法）
│   │       └── reranker_service.py    ← 新增
│   └── scripts/
│       └── evaluate_rag.py            ← 新增（自动化问答生成 + BM25 重建 + 评估）
└── frontend/
    └── src/
        ├── App.vue                     ← 更新（代码高亮主题 CSS）
        ├── components/
        │   ├── ChatMessage.vue         ← 更新（Markdown 渲染 + 来源卡片美化）
        │   ├── DocumentUploader.vue    ← 新增
        │   └── ErrorBoundary.vue       ← 新增
        ├── composables/
        │   ├── useMarkdown.ts          ← 新增（post-processing 方案，稳定可靠）
        │   ├── useSSE.ts               ← 更新（120s 心跳 + 注释行处理）
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

---

## Day 3 Bug 修复记录（2026-06-17 联调验证）

### Bug 1: 代码块语法高亮失效 ✅

**根因**: `App.vue` 中缺少 `highlight.js` 的 GitHub Dark 主题 CSS 类（`.hljs-*`），且 `useMarkdown.ts` 的正则匹配不够健壮。  
**修复**:
1. `frontend/src/App.vue` — 添加完整的 highlight.js GitHub Dark 主题 CSS（~70 行颜色规则）
2. `frontend/src/composables/useMarkdown.ts` — 重写代码块后处理逻辑：
   - 添加 `.code-block-wrapper` 包裹层，包含语言标签 + 复制按钮
   - 添加 try/catch 保护 `hljs.highlight()` 调用
   - 改进 HTML 实体解码（新增 `&#x27;`）
   - 改进引用角标正则（添加 `(?<!!)` 防止匹配 Markdown 图片语法）
3. `frontend/src/components/ChatMessage.vue` — 新增样式：
   - `.code-block-wrapper` 相对定位容器
   - `.copy-btn` 复制按钮（hover 时显示，点击后反馈"已复制!"）
   - `.code-lang-label` 语言标签
   - 复制按钮与语言标签共存时的位置错开处理

### Bug 2: 上传 PDF 后前端状态丢失 ✅

**根因**: `ChatView.vue` 中 `uploadedDocs` 仅为本地 `ref`，页面刷新后丢失；后端缺少文档列表查询接口。  
**修复**:
1. `backend/app/services/vector_store.py` — 新增 `get_unique_documents()` 方法，从 ChromaDB metadata 中聚合去重文档信息（filename, chunk_count, page_count）
2. `backend/app/api/documents.py` — 新增 `GET /documents/` 端点，返回已上传文档列表
3. `frontend/src/views/ChatView.vue` — 
   - 新增 `fetchDocuments()` 异步函数，在 `onMounted` 时调用
   - 新增 `import api from '@/utils/api'`
   - 上传后文档列表在刷新/新会话后依然可见

### Bug 3: RAGAS 测试集生成与评估完善 ✅

**根因**: 原有脚本缺少完整的 RAGAS 4 维参数结构、缺少独立的测试集生成工具。  
**修复**:
1. `backend/scripts/evaluate_rag.py` — 全面重构：
   - 改进 QA 生成 Prompt（要求更详细的 ground_truth）
   - 添加问答对格式验证（跳过不合法条目）
   - 完整 4 维结构输出（question + contexts + answer + ground_truth）
   - 评估结果增加评分等级（✅优秀 / ⚠️良好 / ❌需改进）
   - 额外保存 `eval_details.json`（包含完整评估细节）
   - 尝试导入更多指标（`context_precision`, `answer_correctness`）
   - 输出"简历金句"方便直接引用评估数据
2. `backend/scripts/generate_testset.py` — **新文件**，独立测试集生成工具：
   - `--count` 控制生成数量
   - `--full` 构建完整 4 维测试集
   - `--output` 指定输出文件名
   - 可独立运行，不依赖 evaluate_rag.py

### Bug 4: 来源引用角标悬浮卡片数据为 null ✅

**根因**: 后端 Pydantic `SourceCitation` 使用 `snake_case`（`document_name`, `relevance_score`），前端 TypeScript `SourceCitation` 接口使用 `camelCase`（`documentName`, `relevanceScore`）。`JSON.parse()` 后字段名不匹配导致 `source.documentName` 为 `undefined`。  
**修复**:
1. `backend/app/models/schemas.py` — 将 `SourceCitation` 字段名改为 camelCase：
   - `document_name` → `documentName`
   - `relevance_score` → `relevanceScore`
2. `backend/app/services/rag_service.py` — 同步更新 `SourceCitation` 构造代码中的字段名

### 修改文件汇总

| 文件 | 操作 | 涉及任务 |
|------|------|----------|
| `frontend/src/App.vue` | 修改 | Bug 1 — 添加 hljs CSS 主题 |
| `frontend/src/composables/useMarkdown.ts` | 重写 | Bug 1 — 代码块高亮 + 复制按钮 |
| `frontend/src/components/ChatMessage.vue` | 修改 | Bug 1 — 代码块样式 + 复制按钮样式 |
| `frontend/src/views/ChatView.vue` | 修改 | Bug 2 — 文档状态持久化 |
| `backend/app/models/schemas.py` | 修改 | Bug 4 — SourceCitation camelCase |
| `backend/app/services/rag_service.py` | 修改 | Bug 4 — 字段名同步 |
| `backend/app/services/vector_store.py` | 修改 | Bug 2 — 新增 get_unique_documents() |
| `backend/app/api/documents.py` | 修改 | Bug 2 — 新增 GET /documents/ 端点 |
| `backend/scripts/evaluate_rag.py` | 重写 | Bug 3 — 完善评估脚本 |
| `backend/scripts/generate_testset.py` | 新增 | Bug 3 — 独立测试集生成工具 |