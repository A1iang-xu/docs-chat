<script setup lang="ts">
/**
 * v4.3: 系统监控面板 —— 实时展示 RAG 管线指标
 *
 * 数据来源: GET /stats/（metrics_service）
 * 自动刷新: 每 5 秒
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import api from '@/utils/api'

interface LibraryInfo {
  name: string
  chunk_count: number
}

interface Stats {
  total_queries?: number
  cache_hit_rate?: number
  cache_hits?: number
  cache_misses?: number
  faithfulness_warning_rate?: number
  faithfulness_warnings?: number
  latency_p50?: number
  latency_p95?: number
  libraries?: LibraryInfo[]
}

const stats = ref<Stats | null>(null)
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(true)
let timer: ReturnType<typeof setInterval> | null = null

const fetchStats = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/stats/')
    stats.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '获取统计数据失败'
  } finally {
    loading.value = false
  }
}

const formatMs = (ms?: number) => {
  if (!ms && ms !== 0) return '--'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)} ms`
}

const formatPercent = (val?: number) => {
  if (val === undefined || val === null) return '--'
  return `${(val * 100).toFixed(1)}%`
}

const barWidth = (ms?: number) => {
  if (!ms) return '0%'
  return `${Math.min((ms / 10000) * 100, 100)}%`
}

watch(autoRefresh, (val) => {
  if (val) {
    timer = setInterval(fetchStats, 5000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
})

onMounted(() => {
  fetchStats()
  if (autoRefresh.value) {
    timer = setInterval(fetchStats, 5000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="stats-view">
    <div class="stats-header">
      <h2>系统监控面板</h2>
      <div class="auto-refresh">
        <span :class="['refresh-dot', { active: autoRefresh }]"></span>
        <span class="refresh-text">{{ autoRefresh ? '自动刷新 (5s)' : '已暂停' }}</span>
        <button @click="autoRefresh = !autoRefresh" class="toggle-btn">
          {{ autoRefresh ? '暂停' : '恢复' }}
        </button>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-cards" v-if="stats">
      <div class="card">
        <div class="card-label">总查询数</div>
        <div class="card-value">{{ stats.total_queries ?? 0 }}</div>
      </div>
      <div class="card">
        <div class="card-label">缓存命中率</div>
        <div class="card-value accent">{{ formatPercent(stats.cache_hit_rate) }}</div>
      </div>
      <div class="card">
        <div class="card-label">忠实度警告率</div>
        <div class="card-value" :class="{ danger: (stats.faithfulness_warning_rate ?? 0) > 0.1 }">
          {{ formatPercent(stats.faithfulness_warning_rate) }}
        </div>
      </div>
      <div class="card">
        <div class="card-label">P50 延迟</div>
        <div class="card-value">{{ formatMs(stats.latency_p50) }}</div>
      </div>
      <div class="card">
        <div class="card-label">P95 延迟</div>
        <div class="card-value" :class="{ danger: (stats.latency_p95 ?? 0) > 5000 }">
          {{ formatMs(stats.latency_p95) }}
        </div>
      </div>
    </div>

    <!-- 延迟分布 -->
    <div class="chart-section" v-if="stats">
      <h3>延迟分布</h3>
      <div class="latency-bars">
        <div class="bar-item">
          <span class="bar-label">P50</span>
          <div class="bar-track">
            <div class="bar-fill" :style="{ width: barWidth(stats.latency_p50) }"></div>
          </div>
          <span class="bar-value">{{ formatMs(stats.latency_p50) }}</span>
        </div>
        <div class="bar-item">
          <span class="bar-label">P95</span>
          <div class="bar-track">
            <div class="bar-fill warn" :style="{ width: barWidth(stats.latency_p95) }"></div>
          </div>
          <span class="bar-value">{{ formatMs(stats.latency_p95) }}</span>
        </div>
      </div>
    </div>

    <!-- 缓存统计 -->
    <div class="chart-section" v-if="stats && (stats.cache_hits !== undefined || stats.cache_misses !== undefined)">
      <h3>缓存统计</h3>
      <div class="cache-stats">
        <div class="cache-item">
          <span class="cache-label">命中</span>
          <span class="cache-value accent">{{ stats.cache_hits ?? 0 }}</span>
        </div>
        <div class="cache-item">
          <span class="cache-label">未命中</span>
          <span class="cache-value">{{ stats.cache_misses ?? 0 }}</span>
        </div>
      </div>
    </div>

    <!-- 文档库概览 -->
    <div class="chart-section" v-if="stats && stats.libraries && stats.libraries.length > 0">
      <h3>文档库概览</h3>
      <div class="library-list">
        <div class="library-item" v-for="lib in stats.libraries" :key="lib.name">
          <span class="lib-name">{{ lib.name }}</span>
          <span class="lib-count">{{ lib.chunk_count }} chunks</span>
        </div>
      </div>
    </div>

    <!-- 状态提示 -->
    <div class="loading" v-if="loading && !stats">
      <p>加载中...</p>
    </div>
    <div class="error-box" v-if="error">
      <p>{{ error }}</p>
      <button @click="fetchStats">重试</button>
    </div>
    <div class="empty" v-if="!loading && !error && !stats">
      <p>暂无数据</p>
    </div>
  </div>
</template>

<style scoped>
.stats-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
  height: 100vh;
  overflow-y: auto;
}

.stats-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.stats-header h2 {
  font-size: 1.4rem;
  color: var(--ink);
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--muted);
}

.refresh-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--rule);
}

.refresh-dot.active {
  background: var(--accent2);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.toggle-btn {
  padding: 4px 12px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: var(--bg2);
  color: var(--ink);
  cursor: pointer;
  font-size: 0.8rem;
  transition: border-color 0.2s;
}

.toggle-btn:hover {
  border-color: var(--accent);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.card {
  background: var(--bg2);
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 18px;
  text-align: center;
  transition: border-color 0.2s;
}

.card:hover {
  border-color: var(--accent);
}

.card-label {
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 8px;
}

.card-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--ink);
}

.card-value.accent {
  color: var(--accent2);
}

.card-value.danger {
  color: var(--danger);
}

.chart-section {
  background: var(--bg2);
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}

.chart-section h3 {
  margin: 0 0 16px 0;
  font-size: 1.05rem;
  color: var(--ink);
}

.latency-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bar-label {
  width: 36px;
  font-weight: 600;
  color: var(--muted);
  font-size: 0.85rem;
}

.bar-track {
  flex: 1;
  height: 22px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--accent2);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.bar-fill.warn {
  background: #d29922;
}

.bar-value {
  width: 70px;
  text-align: right;
  font-size: 0.85rem;
  color: var(--muted);
  font-family: 'SFMono-Regular', Consolas, monospace;
}

.cache-stats {
  display: flex;
  gap: 24px;
}

.cache-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cache-label {
  font-size: 0.8rem;
  color: var(--muted);
}

.cache-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--ink);
}

.cache-value.accent {
  color: var(--accent2);
}

.library-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg);
  border-radius: 6px;
}

.lib-name {
  font-weight: 600;
  color: var(--ink);
}

.lib-count {
  color: var(--muted);
  font-size: 0.85rem;
}

.loading,
.error-box,
.empty {
  text-align: center;
  padding: 40px;
  color: var(--muted);
}

.error-box p {
  color: var(--danger);
  margin-bottom: 12px;
}

.error-box button {
  padding: 6px 16px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: var(--bg2);
  color: var(--ink);
  cursor: pointer;
}
</style>
