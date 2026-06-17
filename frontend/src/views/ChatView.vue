<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue'
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
const sidebarOpen = ref(false)

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  // 通过事件通知侧边栏组件
  // 或使用 provide/inject
}
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
          <button class="hamburger-btn" @click="toggleSidebar" aria-label="切换侧边栏">
            <span></span>
            <span></span>
            <span></span>
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
.hamburger-btn {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.4rem;
  flex-direction: column;
  gap: 4px;
}

.hamburger-btn span {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--ink);
  border-radius: 1px;
  transition: transform 0.2s;
}

@media (max-width: 767px) {
  .hamburger-btn {
    display: flex;
  }
}
</style>