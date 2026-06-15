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