<script setup lang="ts">
/**
 * v4.3: 系统监控面板 —— 实时展示 RAG 管线指标
 * v4.5: 增强 —— RAGAS 评估面板 + 反馈统计 + 完整指标展示
 *
 * 数据来源: GET /stats/（metrics_service）
 *           GET /feedback/stats（feedback_service）
 *           POST /evaluation/run + GET /evaluation/latest（evaluation_service）
 * 自动刷新: 每 5 秒（仅监控指标，评估数据手动触发）
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import api from '@/utils/api'

interface LibraryInfo {
  library: string
  version?: string
  chunk_count: number
  source_url?: string
}

interface Stats {
  total_queries?: number
  cache_hit_rate?: number
  cache_hits?: number
  cache_misses?: number
  faithfulness_warning_rate?: number
  faithfulness_warnings?: number
  latency_p50?: Record<string, number> | number
  latency_p95?: Record<string, number> | number
  libraries?: LibraryInfo[]
  avg_retrieval_count?: number
  avg_retrieve_ms?: number
  avg_generate_ms?: number
}

interface FeedbackStats {
  total: number
  positive: number
  negative: number
  positive_rate: number
}

interface EvaluationResult {
  faithfulness?: number
  context_precision?: number
  context_recall?: number
  answer_relevancy?: number
  keyword_coverage?: number
  created_at?: string
}

const stats = ref<Stats | null>(null)
const feedbackStats = ref<FeedbackStats | null>(null)
const evaluationResult = ref<EvaluationResult | null>(null)
const evaluationHistory = ref<EvaluationResult[]>([])
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(true)
const isRunningEvaluation = ref(false)
const evalError = ref('')
let timer: ReturnType<typeof setInterval> | null = null

// 从 dict 或 number 中提取 pipeline 阶段的延迟值
function extractLatency(val: Record<string, number> | number | undefined): number | undefined {
  if (val === undefined || val === null) return undefined
  if (typeof val === 'number') return val
  return val['pipeline'] ?? Object.values(val)[0]
}

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

// v4.5: 获取反馈统计
const fetchFeedbackStats = async () => {
  try {
    const res = await api.get('/feedback/stats')
    feedbackStats.value = res.data
  } catch {
    // 静默失败
  }
}

// v4.5: 获取最新评估结果
const fetchLatestEvaluation = async () => {
  try {
    const res = await api.get('/evaluation/latest')
    if (res.data) {
      evaluationResult.value = res.data
    }
  } catch {
    // 尚无评估记录时静默
  }
}

// v4.5: 触发 RAGAS 评估
const runEvaluation = async () => {
  isRunningEvaluation.value = true
  evalError.value = ''
  try {
    const res = await api.post('/evaluation/run', {}, { timeout: 120_000 })
    evaluationResult.value = res.data
    // 刷新历史
    fetchEvaluationHistory()
  } catch (e: any) {
    evalError.value = e.response?.data?.detail || e.message || '评估执行失败'
  } finally {
    isRunningEvaluation.value = false
  }
}

// v4.5: 获取评估历史
const fetchEvaluationHistory = async () => {
  try {
    const res = await api.get('/evaluation/history')
    evaluationHistory.value = Array.isArray(res.data) ? res.data : []
  } catch {
    // 静默
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

const formatScore = (val?: number) => {
  if (val === undefined || val === null) return '--'
  return val.toFixed(3)
}

const barWidth = (ms?: number) => {
  if (!ms) return '0%'
  return `${Math.min((ms / 10000) * 100, 100)}%`
}

const scoreBarWidth = (score?: number) => {
  if (score === undefined || score === null) return '0%'
  return `${Math.min(score * 100, 100)}%`
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
  fetchFeedbackStats()
  fetchLatestEvaluation()
  fetchEvaluationHistory()
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
        <div class="card-value">{{ formatMs(extractLatency(stats.latency_p50)) }}</div>
      </div>
      <div class="card">
        <div class="card-label">P95 延迟</div>
        <div class="card-value" :class="{ danger: (extractLatency(stats.latency_p95) ?? 0) > 5000 }">
          {{ formatMs(extractLatency(stats.latency_p95)) }}
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
            <div class="bar-fill" :style="{ width: barWidth(extractLatency(stats.latency_p50)) }"></div>
          </div>
          <span class="bar-value">{{ formatMs(extractLatency(stats.latency_p50)) }}</span>
        </div>
        <div class="bar-item">
          <span class="bar-label">P95</span>
          <div class="bar-track">
            <div class="bar-fill warn" :style="{ width: barWidth(extractLatency(stats.latency_p95)) }"></div>
          </div>
          <span class="bar-value">{{ formatMs(extractLatency(stats.latency_p95)) }}</span>
        </div>
      </div>
      <!-- v4.5: 详细延迟指标 -->
      <div class="detail-metrics" v-if="stats.avg_retrieve_ms || stats.avg_generate_ms">
        <div class="metric-item">
          <span class="metric-label">平均检索耗时</span>
          <span class="metric-value">{{ formatMs(stats.avg_retrieve_ms) }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">平均生成耗时</span>
          <span class="metric-value">{{ formatMs(stats.avg_generate_ms) }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">平均检索文档数</span>
          <span class="metric-value">{{ stats.avg_retrieval_count?.toFixed(1) ?? '--' }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">忠实度警告次数</span>
          <span class="metric-value">{{ stats.faithfulness_warnings ?? 0 }}</span>
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

    <!-- v4.5: 反馈统计 -->
    <div class="chart-section" v-if="feedbackStats && feedbackStats.total > 0">
      <h3>用户反馈统计</h3>
      <div class="feedback-stats">
        <div class="feedback-item">
          <span class="feedback-label">总反馈数</span>
          <span class="feedback-value">{{ feedbackStats.total }}</span>
        </div>
        <div class="feedback-item">
          <span class="feedback-label">正面反馈</span>
          <span class="feedback-value accent">{{ feedbackStats.positive }}</span>
        </div>
        <div class="feedback-item">
          <span class="feedback-label">负面反馈</span>
          <span class="feedback-value danger">{{ feedbackStats.negative }}</span>
        </div>
        <div class="feedback-item">
          <span class="feedback-label">好评率</span>
          <span class="feedback-value accent">{{ formatPercent(feedbackStats.positive_rate) }}</span>
        </div>
      </div>
    </div>

    <!-- v4.5: RAGAS 评估面板 -->
    <div class="chart-section evaluation-panel">
      <div class="eval-header">
        <h3>RAGAS 质量评估</h3>
        <button
          class="eval-btn"
          :disabled="isRunningEvaluation"
          @click="runEvaluation"
        >
          {{ isRunningEvaluation ? '评估中...' : '运行评估' }}
        </button>
      </div>
      <div v-if="evalError" class="eval-error">{{ evalError }}</div>

      <div v-if="evaluationResult" class="eval-results">
        <div class="eval-score-item">
          <div class="eval-score-header">
            <span class="eval-score-label">忠实度 (Faithfulness)</span>
            <span class="eval-score-value">{{ formatScore(evaluationResult.faithfulness) }}</span>
          </div>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" :style="{ width: scoreBarWidth(evaluationResult.faithfulness) }"></div>
          </div>
        </div>
        <div class="eval-score-item">
          <div class="eval-score-header">
            <span class="eval-score-label">上下文精确率</span>
            <span class="eval-score-value">{{ formatScore(evaluationResult.context_precision) }}</span>
          </div>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" :style="{ width: scoreBarWidth(evaluationResult.context_precision) }"></div>
          </div>
        </div>
        <div class="eval-score-item">
          <div class="eval-score-header">
            <span class="eval-score-label">上下文召回率</span>
            <span class="eval-score-value">{{ formatScore(evaluationResult.context_recall) }}</span>
          </div>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" :style="{ width: scoreBarWidth(evaluationResult.context_recall) }"></div>
          </div>
        </div>
        <div class="eval-score-item">
          <div class="eval-score-header">
            <span class="eval-score-label">答案相关性</span>
            <span class="eval-score-value">{{ formatScore(evaluationResult.answer_relevancy) }}</span>
          </div>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" :style="{ width: scoreBarWidth(evaluationResult.answer_relevancy) }"></div>
          </div>
        </div>
        <div class="eval-score-item">
          <div class="eval-score-header">
            <span class="eval-score-label">关键词覆盖率</span>
            <span class="eval-score-value">{{ formatScore(evaluationResult.keyword_coverage) }}</span>
          </div>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" :style="{ width: scoreBarWidth(evaluationResult.keyword_coverage) }"></div>
          </div>
        </div>
        <div class="eval-timestamp" v-if="evaluationResult.created_at">
          评估时间: {{ new Date(evaluationResult.created_at).toLocaleString('zh-CN') }}
        </div>
      </div>
      <div v-else-if="!isRunningEvaluation" class="eval-empty">
        暂无评估数据，点击"运行评估"开始
      </div>
    </div>

    <!-- 文档库概览 -->
    <div class="chart-section" v-if="stats && stats.libraries && stats.libraries.length > 0">
      <h3>文档库概览</h3>
      <div class="library-list">
        <div class="library-item" v-for="lib in stats.libraries" :key="lib.library">
          <div class="lib-info">
            <span class="lib-name">{{ lib.library }}</span>
            <span class="lib-version" v-if="lib.version && lib.version !== 'latest'">@{{ lib.version }}</span>
          </div>
          <div class="lib-meta">
            <span class="lib-count">{{ lib.chunk_count }} chunks</span>
            <a
              v-if="lib.source_url"
              :href="lib.source_url"
              target="_blank"
              rel="noopener"
              class="lib-link"
            >来源</a>
          </div>
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

/* v4.5: 详细指标 */
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--rule);
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-label {
  font-size: 0.75rem;
  color: var(--muted);
}

.metric-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--ink);
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

/* v4.5: 反馈统计 */
.feedback-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.feedback-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.feedback-label {
  font-size: 0.78rem;
  color: var(--muted);
}

.feedback-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--ink);
}

.feedback-value.accent {
  color: var(--accent2);
}

.feedback-value.danger {
  color: var(--danger);
}

/* v4.5: RAGAS 评估面板 */
.eval-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.eval-header h3 {
  margin: 0;
}

.eval-btn {
  padding: 6px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 4px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: opacity 0.2s;
}

.eval-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.eval-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.eval-error {
  padding: 8px 12px;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid var(--danger);
  border-radius: 4px;
  color: var(--danger);
  font-size: 0.85rem;
  margin-bottom: 12px;
}

.eval-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.eval-score-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.eval-score-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.eval-score-label {
  font-size: 0.85rem;
  color: var(--ink);
}

.eval-score-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--accent);
  font-family: 'SFMono-Regular', Consolas, monospace;
}

.eval-bar-track {
  height: 8px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
}

.eval-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.eval-timestamp {
  font-size: 0.78rem;
  color: var(--muted);
  margin-top: 4px;
}

.eval-empty {
  text-align: center;
  padding: 24px;
  color: var(--muted);
  font-size: 0.9rem;
}

.library-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg);
  border-radius: 6px;
}

.lib-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

.lib-name {
  font-weight: 600;
  color: var(--ink);
}

.lib-version {
  font-size: 0.8rem;
  color: var(--muted);
}

.lib-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.lib-count {
  color: var(--muted);
  font-size: 0.85rem;
}

.lib-link {
  color: var(--accent);
  font-size: 0.8rem;
  text-decoration: none;
}

.lib-link:hover {
  text-decoration: underline;
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
