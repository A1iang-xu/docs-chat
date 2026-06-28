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
  background: var(--destructive-subtle);
  color: var(--destructive);
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
  color: var(--muted-foreground);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
  max-width: 400px;
}

.error-boundary button {
  padding: 0.5rem 1.5rem;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
</style>