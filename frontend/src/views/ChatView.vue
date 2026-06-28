<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useConversationStore } from '@/stores/conversation'
import { useMessageStore } from '@/stores/message'
import { useSSE } from '@/composables/useSSE'
import api from '@/utils/api'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import MessageInput from '@/components/MessageInput.vue'
import DocumentUploader from '@/components/DocumentUploader.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import type { Message, DocumentMeta } from '@/types'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useLibraryStore } from '@/stores/libraryStore'  // v4.0
import { useHistory } from '@/composables/useHistory'  // v4.4

// v4.4: replay prop（从历史侧边栏触发的重放）
const props = defineProps<{
  replay?: { query: string; library: string | null } | null
}>()

const emit = defineEmits<{
  (e: 'replay-consumed'): void
}>()

const sidebarOpen = ref(false)

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  // 通过事件通知侧边栏组件
  // 或使用 provide/inject
}
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const conversationStore = useConversationStore()
const messageStore = useMessageStore()
const libraryStore = useLibraryStore()  // v4.0

const { content, sources, isStreaming, error, connect, abort, stage, stageLabel, faithfulnessWarning, cacheHit } = useSSE({
  maxRetries: 2,
  retryBaseMs: 1000,
  heartbeatTimeoutMs: 30_000,
})

const isSending = ref(false)
const assistantMsgId = ref<string | null>(null)
const messageContainer = ref<HTMLElement | null>(null)
const virtualScroller = ref<{ scrollToBottom?: () => void } | null>(null)
const uploadedDocs = ref<DocumentMeta[]>([])

// 当前会话的消息列表
const currentMessages = ref<Message[]>([])

const hasDocuments = computed(() => uploadedDocs.value.length > 0)
const readyDocCount = computed(() => uploadedDocs.value.filter((doc) => doc.status === 'ready').length)
const runningDocCount = computed(() =>
  uploadedDocs.value.filter((doc) => doc.status === 'queued' || doc.status === 'running').length,
)

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

  // v4.4: 写入查询历史
  const { add: addHistory } = useHistory()
  addHistory(text, libraryStore.selectedLibrary)

  assistantMsgId.value = await messageStore.sendMessage(convId, text)
  currentMessages.value = messageStore.getMessages(convId)

  await nextTick()
  scrollToBottom()

  // v4.1: 构建多轮对话历史（最近6条消息）
  const allMsgs = messageStore.getMessages(convId)
  const history = allMsgs
    .filter((m) => m.id !== assistantMsgId.value)
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content }))

  await connect(`${API_BASE}/chat/stream`, {
    conversation_id: convId,
    content: text,
    library: libraryStore.selectedLibrary,  // v4.0
    history,  // v4.1: 多轮对话历史
  })

  isSending.value = false
  assistantMsgId.value = null
}

// v4.4: 监听 replay prop，自动重发查询
watch(
  () => props.replay,
  (newReplay) => {
    if (newReplay) {
      if (newReplay.library) {
        libraryStore.setSelectedLibrary(newReplay.library)
      }
      handleSend(newReplay.query)
      emit('replay-consumed')
    }
  },
)

function handleAbort() {
  abort()
  isSending.value = false
}

function handleDocumentUploaded(doc: DocumentMeta) {
  const index = uploadedDocs.value.findIndex((item) => item.id === doc.id || item.filename === doc.filename)
  if (index >= 0) {
    uploadedDocs.value[index] = doc
  } else {
    uploadedDocs.value.push(doc)
  }
}

async function fetchDocuments() {
  /** 页面加载时从后端同步已上传的文档列表，恢复状态 */
  try {
    const { data } = await api.get('/documents/')
    // 后端返回 { filename, chunk_count, page_count } 列表
    if (Array.isArray(data)) {
      uploadedDocs.value = data.map((item: Record<string, unknown>) => ({
        id: crypto.randomUUID(),
        filename: item.filename as string,
        pageCount: item.page_count as number || 0,
        chunkCount: item.chunk_count as number || 0,
        uploadedAt: new Date().toISOString(),
        status: 'ready' as const,
      }))
    }
  } catch {
    // 后端不可用时静默失败，不影响基本聊天功能
    console.warn('[ChatView] 无法获取文档列表')
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (virtualScroller.value?.scrollToBottom) {
      virtualScroller.value.scrollToBottom()
      return
    }
    if (messageContainer.value) {
      messageContainer.value.scrollTop = messageContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  if (!conversationStore.activeId) {
    conversationStore.createConversation('新对话')
  }
  fetchDocuments()
  libraryStore.restore()   // v4.0: restore last library selection
  libraryStore.fetchLibraries()  // v4.0: fetch available libraries
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
            <!-- v4.0: 库选择器 -->
            <select
              v-if="libraryStore.libraries.length > 0"
              :value="libraryStore.selectedLibrary"
              @change="libraryStore.setSelected(($event.target as HTMLSelectElement).value || null)"
              class="library-select"
            >
              <option value="">全部库</option>
              <option
                v-for="lib in libraryStore.libraries"
                :key="lib.library + '@' + lib.version"
                :value="lib.library"
              >
                {{ lib.library }}{{ lib.version !== 'latest' ? '@' + lib.version : '' }}
                ({{ lib.chunk_count }})
              </option>
            </select>
            <span v-if="hasDocuments" class="doc-badge">
              知识库: {{ readyDocCount }}/{{ uploadedDocs.length }} 就绪
              <span v-if="runningDocCount">，{{ runningDocCount }} 处理中</span>
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
          <button class="hamburger-btn" @click="toggleSidebar" aria-label="切换侧边栏">
            <span></span>
            <span></span>
            <span></span>
          </button>
        </header>

        <!-- 消息列表 -->
        <div ref="messageContainer" class="message-list">
          <DynamicScroller
            v-if="currentMessages.length > 0"
            ref="virtualScroller"
            :items="currentMessages"
            :min-item-size="96"
            key-field="id"
            class="virtual-message-list"
          >
            <template #default="{ item, index, active }">
              <DynamicScrollerItem
                :item="item"
                :active="active"
                :size-dependencies="[item.content, item.sources.length]"
                :data-index="index"
              >
                <ChatMessage :message="item" />
              </DynamicScrollerItem>
            </template>
          </DynamicScroller>

          <!-- 错误提示 -->
          <div v-if="error" class="error-banner">
            请求失败：{{ error }}
            <button @click="error = null">关闭</button>
          </div>
          <!-- v4.4: 阶段指示器 -->
          <div v-if="isStreaming && stageLabel" class="stage-indicator">
            <span class="stage-dot"></span>
            <span class="stage-text">{{ stageLabel }}</span>
          </div>
          <!-- v4.4: 缓存命中提示 -->
          <div v-if="cacheHit && isStreaming" class="cache-hit-badge">
            ⚡ 缓存命中
          </div>
          <!-- v4.4: 忠实度警告提示条 -->
          <div v-if="faithfulnessWarning" class="faithfulness-warning">
            {{ faithfulnessWarning }}
          </div>
          <!-- 骨架屏：流式生成中 -->
          <LoadingSkeleton v-if="isStreaming && currentMessages.length > 0" :lines="4" />
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
  background: var(--background);
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
  border-bottom: 1px solid var(--border);
  background: var(--background);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.header-left h2 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--foreground);
}
.doc-badge {
  font-size: 0.75rem;
  color: var(--success-text);
  background: var(--success-subtle);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.abort-btn {
  padding: 0.45rem 1rem;
  background: var(--destructive-subtle);
  color: var(--destructive);
  border: 1px solid var(--destructive-border);
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.2s;
}
.abort-btn:hover {
  background: var(--destructive-border);
}

.message-list {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.virtual-message-list {
  height: 100%;
}

.error-banner {
  margin: 1rem 1.5rem;
  padding: 0.75rem 1rem;
  background: var(--destructive-subtle);
  border: 1px solid var(--destructive-border);
  border-radius: var(--radius-sm);
  color: var(--destructive-text);
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.error-banner button {
  background: none;
  border: none;
  color: var(--destructive-text);
  font-weight: 600;
  cursor: pointer;
}

/* v4.4: 阶段指示器 */
.stage-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: var(--brand-subtle);
  border-radius: var(--radius-sm);
  margin: 8px 0;
  font-size: 0.8rem;
  color: var(--primary);
}
.stage-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  animation: stage-pulse 1.2s infinite;
}
@keyframes stage-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* v4.4: 忠实度警告 */
.faithfulness-warning {
  padding: 6px 16px;
  background: var(--warning-subtle);
  border-left: 3px solid var(--warning);
  border-radius: var(--radius-sm);
  margin: 8px 0;
  font-size: 0.8rem;
  color: var(--warning-text);
}

/* v4.4: 缓存命中提示 */
.cache-hit-badge {
  display: inline-block;
  padding: 4px 12px;
  background: var(--success-subtle);
  border: 1px solid var(--success-border);
  border-radius: 12px;
  margin: 8px 0;
  font-size: 0.78rem;
  color: var(--success-text);
  font-weight: 600;
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
  color: var(--primary);
  margin-bottom: 0.75rem;
}
.empty-state p {
  color: var(--muted-foreground);
  font-size: 0.95rem;
}
.empty-hint {
  margin-top: 0.5rem;
  font-size: 0.85rem !important;
}
.hamburger-btn {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.4rem;
  flex-direction: column;
  gap: 4px;
}

/* v4.0: 库选择器 */
.library-select {
  padding: 0.3rem 0.6rem;
  background: var(--muted);
  color: var(--foreground);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.78rem;
  cursor: pointer;
  max-width: 220px;
}
.library-select:focus {
  outline: none;
  border-color: var(--primary);
}

.hamburger-btn span {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--foreground);
  border-radius: 1px;
  transition: transform 0.2s;
}

@media (max-width: 767px) {
  .hamburger-btn {
    display: flex;
  }
}
</style>
