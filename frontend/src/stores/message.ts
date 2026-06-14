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