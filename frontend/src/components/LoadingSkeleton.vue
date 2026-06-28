<script setup lang="ts">
/**
 * LoadingSkeleton —— 对话加载中的骨架屏
 * 在消息流式生成时提供视觉反馈，提升感知性能
 */
defineProps<{
  lines?: number
}>()
</script>

<template>
  <div class="skeleton-message">
    <div class="skeleton-avatar"></div>
    <div class="skeleton-lines">
      <div
        v-for="i in (lines || 3)"
        :key="i"
        class="skeleton-line"
        :style="{ width: `${80 - i * 10}%`, animationDelay: `${i * 0.15}s` }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.skeleton-message {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: var(--muted);
}

.skeleton-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--border);
  animation: shimmer 1.5s infinite;
  flex-shrink: 0;
}

.skeleton-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.skeleton-line {
  height: 14px;
  border-radius: var(--radius-sm);
  background: var(--border);
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { opacity: 0.4; }
  50% { opacity: 0.8; }
  100% { opacity: 0.4; }
}
</style>