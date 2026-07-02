<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useLibraryStore } from '@/stores/libraryStore'
import { useConversationStore } from '@/stores/conversation'
import { useSSE } from '@/composables/useSSE'
import { api } from '@/utils/api'
import type { ChatMessage } from '@/types'

import ConversationSidebar from '@/components/ConversationSidebar.vue'
import ChatMessageComponent from '@/components/ChatMessage.vue'
import MessageInput from '@/components/MessageInput.vue'

const route = useRoute()
const libraryStore = useLibraryStore()
const conversationStore = useConversationStore()

const messages = ref<ChatMessage[]>([])
const isSending = ref(false)
const sidebarOpen = ref(false)
const sourcesPanelOpen = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const isMobile = ref(false)

const activeConversation = computed(() => {
  return conversationStore.conversations.find(c => c.id === conversationStore.activeId)
})

const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}

const toggleSourcesPanel = () => {
  sourcesPanelOpen.value = !sourcesPanelOpen.value
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  if (route.query.new && !conversationStore.activeId) {
    conversationStore.createConversation('新对话')
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// 切换对话时加载历史消息
watch(() => conversationStore.activeId, (newId) => {
  if (newId) {
    const conv = conversationStore.conversations.find(c => c.id === newId)
    if (conv) {
      messages.value = conv.messages || []
      scrollToBottom()
    }
  } else {
    messages.value = []
  }
}, { immediate: true })

// 选中库变更时自动存入当前对话标记
watch(() => libraryStore.selected, (lib) => {
  if (conversationStore.activeId && lib) {
    const conv = conversationStore.conversations.find(c => c.id === conversationStore.activeId)
    if (conv && conv.library !== lib) {
      conversationStore.updateConversation(conversationStore.activeId, { library: lib })
    }
  }
})

const { content, sources, isStreaming, error, connect, abort } = useSSE()

// Watch streaming content
watch(content, (val) => {
  if (!val) return
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.content = val
  }
  scrollToBottom()
})

// Watch streaming done
watch(isStreaming, (val, oldVal) => {
  if (oldVal && !val) {
    isSending.value = false
    if (conversationStore.activeId) {
      conversationStore.updateConversation(conversationStore.activeId, {
        messages: [...messages.value],
        updatedAt: Date.now(),
      })
    }
  }
})

// Watch error
watch(error, (err) => {
  if (!err) return
  isSending.value = false
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.content = err || '抱歉，请求出错了，请稍后重试。'
  } else {
    messages.value = [...messages.value, { role: 'assistant', content: err || '抱歉，请求出错了，请稍后重试。' }]
  }
})

const handleSend = async (question: string) => {
  if (!question.trim() || isSending.value) return

  const isNewConversation = !conversationStore.activeId
  if (isNewConversation) {
    conversationStore.createConversation('新对话')
  }

  isSending.value = true

  const userMsg: ChatMessage = { role: 'user', content: question.trim() }
  messages.value = [...messages.value, userMsg]
  messages.value = [...messages.value, { role: 'assistant', content: '' }]
  scrollToBottom()

  try {
    const body: Record<string, unknown> = {
      content: question.trim(),
      conversation_id: conversationStore.activeId,
    }
    if (libraryStore.selected) {
      body.library = libraryStore.selected
    }
    await connect('/api/chat/stream', body)

    // 新对话的第一条消息，以问题内容作为对话标题
    if (isNewConversation && conversationStore.activeId) {
      conversationStore.updateConversation(conversationStore.activeId, {
        title: question.trim().slice(0, 50),
      })
    }
  } catch (e: any) {
    isSending.value = false
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = e?.response?.data?.detail || e.message || '请求失败'
    }
  }
}

const handleCancelStream = () => {
  if (isStreaming.value) {
    abort()
  }
}

const handleNewChat = () => {
  conversationStore.createConversation('新对话')
  if (isMobile.value) {
    sidebarOpen.value = false
  }
}
</script>

<template>
  <div class="chat-layout">
    <!-- Sidebar -->
    <ConversationSidebar
      v-model:mobile-open="sidebarOpen"
    />

    <!-- Main chat area -->
    <div class="chat-main">
      <!-- Header -->
      <header class="chat-header">
        <div class="chat-header-left">
          <button
            v-if="isMobile"
            class="hamburger-btn"
            aria-label="切换侧边栏"
            @click="toggleSidebar"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <h1 class="chat-title">
            {{ activeConversation?.title || 'DocsChat' }}
          </h1>
        </div>
        <div class="chat-header-right">
          <!-- Library selector -->
          <div class="library-selector">
            <svg class="lib-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <select
              class="lib-select"
              :value="libraryStore.selected"
              @change="libraryStore.setSelected(($event.target as HTMLSelectElement).value)"
            >
              <option value="">全部知识库</option>
              <option
                v-for="lib in libraryStore.libraries"
                :key="lib.library"
                :value="lib.library"
              >
                {{ lib.library }}
              </option>
            </select>
          </div>
          <!-- Sources toggle -->
          <button
            v-if="sources.length > 0"
            class="header-btn"
            :class="{ active: sourcesPanelOpen }"
            @click="toggleSourcesPanel"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <span>{{ sources.length }} 来源</span>
          </button>
          <!-- New chat -->
          <button class="header-btn" @click="handleNewChat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>
      </header>

      <!-- Messages area -->
      <div class="chat-body" :class="{ 'with-sources': sourcesPanelOpen && sources.length > 0 }">
        <div ref="messagesContainer" class="messages-container">
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h2>开始对话</h2>
            <p>选择知识库，输入你的问题，DocsChat 将为你检索文档并生成回答。</p>
          </div>

          <div v-else class="messages-list">
            <ChatMessageComponent
              v-for="(msg, idx) in messages"
              :key="idx"
              :message="msg"
              :is-streaming="isStreaming && idx === messages.length - 1 && msg.role === 'assistant'"
            />
          </div>
        </div>

        <!-- Sources panel -->
        <aside v-if="sourcesPanelOpen && sources.length > 0" class="sources-panel">
          <div class="sources-panel-header">
            <h3>参考来源</h3>
            <button class="sources-close-btn" @click="sourcesPanelOpen = false">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="sources-list">
            <div v-for="(src, idx) in sources" :key="idx" class="source-card">
              <div class="source-index">{{ src.index || idx + 1 }}</div>
              <div class="source-info">
                <div class="source-name">{{ src.documentName || src.sourceUrl?.split('/').pop() || '未知文档' }}</div>
                <div class="source-page" v-if="src.page">第 {{ src.page }} 页</div>
                <div class="source-excerpt">{{ src.content?.slice(0, 200) }}{{ src.content?.length > 200 ? '...' : '' }}</div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <!-- Input area -->
      <div class="chat-footer">
        <div class="input-wrapper">
          <MessageInput
            v-model:is-sending="isSending"
            @send="handleSend"
          />
          <button
            v-if="isStreaming"
            class="stop-btn"
            @click="handleCancelStream"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <rect x="4" y="4" width="16" height="16" rx="2"/>
            </svg>
            停止
          </button>
        </div>
      </div>
    </div>
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
  height: 100vh;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: var(--background);
  flex-shrink: 0;
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.hamburger-btn {
  display: none;
  width: 36px;
  height: 36px;
  border: none;
  background: none;
  color: var(--foreground);
  cursor: pointer;
  border-radius: var(--radius-sm);
  align-items: center;
  justify-content: center;
}

.hamburger-btn:hover {
  background: var(--muted);
}

.hamburger-btn svg {
  width: 20px;
  height: 20px;
}

.chat-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.library-selector {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.35rem 0.6rem;
}

.lib-icon {
  width: 15px;
  height: 15px;
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.lib-select {
  background: none;
  border: none;
  color: var(--foreground);
  font-size: 0.82rem;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  max-width: 140px;
}

.header-btn {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.35rem 0.6rem;
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted-foreground);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.header-btn:hover {
  background: var(--muted);
  color: var(--foreground);
}

.header-btn.active {
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
}

.header-btn svg {
  width: 15px;
  height: 15px;
}

/* Body */
.chat-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.5rem;
  scroll-behavior: smooth;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 2rem;
}

.empty-icon {
  width: 64px;
  height: 64px;
  color: var(--muted-foreground);
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-icon svg {
  width: 100%;
  height: 100%;
}

.empty-state h2 {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--foreground);
  margin: 0 0 0.5rem;
}

.empty-state p {
  font-size: 0.9rem;
  color: var(--muted-foreground);
  max-width: 420px;
  line-height: 1.5;
}

/* Messages list */
.messages-list {
  max-width: 768px;
  margin: 0 auto;
}

/* Sources panel */
.sources-panel {
  width: 300px;
  min-width: 300px;
  border-left: 1px solid var(--border);
  background: var(--muted);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sources-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}

.sources-panel-header h3 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--foreground);
  margin: 0;
}

.sources-close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--muted-foreground);
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.sources-close-btn:hover {
  background: var(--border);
  color: var(--foreground);
}

.sources-close-btn svg {
  width: 14px;
  height: 14px;
}

.sources-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.source-card {
  display: flex;
  gap: 0.6rem;
  padding: 0.6rem;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 0.5rem;
}

.source-index {
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 0.72rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.source-info {
  min-width: 0;
  flex: 1;
}

.source-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 0.15rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-page {
  font-size: 0.72rem;
  color: var(--muted-foreground);
  margin-bottom: 0.3rem;
}

.source-excerpt {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  line-height: 1.4;
  word-break: break-word;
}

/* Footer */
.chat-footer {
  padding: 0.75rem 1.25rem;
  border-top: 1px solid var(--border);
  background: var(--background);
  flex-shrink: 0;
}

.input-wrapper {
  max-width: 768px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
}

.input-wrapper :deep(.input-area) {
  flex: 1;
  padding: 0;
  border: none;
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
}

.input-wrapper :deep(.input-box) {
  flex: 1;
  padding: 0.6rem 0.85rem;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--foreground);
  font-size: 0.9rem;
  font-family: inherit;
  resize: none;
  max-height: 200px;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.2s;
}

.input-wrapper :deep(.input-box:focus) {
  border-color: var(--primary);
}

.input-wrapper :deep(.input-box:disabled) {
  opacity: 0.5;
}

.input-wrapper :deep(.send-btn) {
  padding: 0.6rem 0.85rem;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.input-wrapper :deep(.send-btn:hover:not(:disabled)) {
  opacity: 0.85;
}

.input-wrapper :deep(.send-btn:disabled) {
  opacity: 0.4;
  cursor: not-allowed;
}

.stop-btn {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.6rem 0.85rem;
  background: var(--destructive);
  color: var(--destructive-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.stop-btn:hover {
  opacity: 0.85;
}

.stop-btn svg {
  width: 12px;
  height: 12px;
}

/* Mobile */
@media (max-width: 767px) {
  .hamburger-btn {
    display: flex;
  }

  .chat-header {
    padding: 0.6rem 0.75rem;
  }

  .messages-container {
    padding: 0.75rem 1rem;
  }

  .chat-footer {
    padding: 0.6rem 0.75rem;
  }

  .sources-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    width: 300px;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.5);
  }
}
</style>