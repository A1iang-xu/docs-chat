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

  function updateConversation(id: string, partial: Partial<Conversation>) {
    const index = conversations.value.findIndex((c) => c.id === id)
    if (index !== -1) {
      conversations.value[index] = { ...conversations.value[index], ...partial }
    }
  }

  return {
    conversations,
    activeId,
    activeConversation,
    loading,
    fetchConversations,
    createConversation,
    setActive,
    updateConversation,
  }
})