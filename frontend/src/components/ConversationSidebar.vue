<script setup lang="ts">
import { useConversationStore } from '@/stores/conversation'
import type { Conversation } from '@/types'
import { ref, onMounted, onUnmounted } from 'vue'
const conversationStore = useConversationStore()
const isMobileOpen = ref(false)
const isMobile = ref(false)

function handleNewChat() {
  conversationStore.createConversation('新对话')
}

function handleSelect(id: string) {
  conversationStore.setActive(id)
}
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

function toggleSidebar() {
  isMobileOpen.value = !isMobileOpen.value
}
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<template>
  <aside class="sidebar" :class="{ 'mobile-open': isMobileOpen, 'mobile-hidden': isMobile && !isMobileOpen }">
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
/* 移动端：侧边栏默认隐藏，通过汉堡菜单切换 */
@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    left: -280px;
    top: 0;
    bottom: 0;
    z-index: 1000;
    width: 280px;
    transition: left 0.25s ease;
    box-shadow: none;
  }

  .sidebar.mobile-open {
    left: 0;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.5);
  }

  .sidebar.mobile-hidden {
    left: -280px;
  }

  /* 移动端遮罩层 */
  .sidebar.mobile-open::after {
    content: '';
    position: fixed;
    inset: 0;
    left: 280px;
    background: rgba(0, 0, 0, 0.4);
    z-index: -1;
  }
}
</style>