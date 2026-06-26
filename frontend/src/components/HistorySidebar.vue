<script setup lang="ts">
/**
 * v4.4: 查询历史侧边栏
 * 展示最近 20 条查询，点击可重新发起对话
 */
import { useHistory } from '@/composables/useHistory'

const emit = defineEmits<{
  (e: 'select', query: string, library: string | null): void
}>()

const { history, remove, clear } = useHistory()

function formatTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="history-sidebar">
    <div class="history-header">
      <span class="history-title">查询历史</span>
      <button v-if="history.length > 0" class="clear-btn" @click="clear">清空</button>
    </div>

    <div v-if="history.length === 0" class="empty">
      <span>暂无历史记录</span>
    </div>

    <div v-else class="history-list">
      <div
        v-for="item in history"
        :key="item.id"
        class="history-item"
        @click="emit('select', item.query, item.library)"
      >
        <div class="item-query">{{ item.query }}</div>
        <div class="item-meta">
          <span v-if="item.library" class="item-library">{{ item.library }}</span>
          <span class="item-time">{{ formatTime(item.timestamp) }}</span>
          <button
            class="item-remove"
            @click.stop="remove(item.id)"
            title="删除"
          >×</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-sidebar {
  width: 240px;
  height: 100%;
  background: var(--bg2);
  border-right: 1px solid var(--rule);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--rule);
}

.history-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
}

.clear-btn {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 0.75rem;
  cursor: pointer;
  transition: color 0.15s;
}

.clear-btn:hover {
  color: var(--danger);
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--muted);
  font-size: 0.8rem;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.history-item {
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid rgba(48, 54, 61, 0.3);
}

.history-item:hover {
  background: var(--bg);
}

.item-query {
  font-size: 0.82rem;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.7rem;
  color: var(--muted);
}

.item-library {
  padding: 1px 6px;
  background: rgba(88, 166, 255, 0.1);
  color: var(--accent);
  border-radius: 3px;
  font-size: 0.65rem;
}

.item-time {
  flex: 1;
}

.item-remove {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
  padding: 0 2px;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}

.history-item:hover .item-remove {
  opacity: 1;
}

.item-remove:hover {
  color: var(--danger);
}
</style>
