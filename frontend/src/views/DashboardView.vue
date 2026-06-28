<script setup lang="ts">
/**
 * DashboardView — 系统概览仪表盘
 *
 * 数据来源: GET /stats/ / GET /evaluation/latest / GET /evaluation/history
 * 自动刷新: 每 5 秒
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/api'

// ═══════════════════════════════════════════════════════════════
// Interfaces
// ═══════════════════════════════════════════════════════════════

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
  documents?: DocumentInfo[]
  avg_retrieval_count?: number
  avg_retrieve_ms?: number
  avg_generate_ms?: number
  daily_queries?: Record<string, number>
}

interface LibraryInfo {
  library: string
  version?: string
  chunk_count: number
  source_url?: string
}

interface DocumentInfo {
  filename: string
  chunk_count: number
  page_count: number
}

interface EvaluationResult {
  avg_faithfulness?: number
  avg_context_precision?: number
  avg_context_recall?: number
  avg_answer_relevancy?: number
  faithfulness?: number
  context_precision?: number
  context_recall?: number
  answer_relevancy?: number
  dataset_size?: number
  total_evaluated?: number
  created_at?: string
  timestamp?: string
}

// ═══════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════

const router = useRouter()

const stats = ref<Stats | null>(null)
const latestEval = ref<EvaluationResult | null>(null)
const evalHistory = ref<EvaluationResult[]>([])
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(true)

let timer: ReturnType<typeof setInterval> | null = null

// ═══════════════════════════════════════════════════════════════
// Helper functions
// ═══════════════════════════════════════════════════════════════

function extractLatency(val: Record<string, number> | number | undefined): number | undefined {
  if (val === undefined || val === null) return undefined
  if (typeof val === 'number') return val
  return val['pipeline'] ?? Object.values(val)[0]
}

function formatMs(ms?: number): string {
  if (!ms && ms !== 0) return '--'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)} ms`
}

function formatPercent(val?: number): string {
  if (val === undefined || val === null) return '--'
  return `${(val * 100).toFixed(1)}%`
}

function formatScore(val?: number): string {
  if (val === undefined || val === null) return '--'
  return val.toFixed(3)
}

function formatDate(val?: string): string {
  if (!val) return '--'
  try {
    const normalized = val.replace(/(\.\d{3})\d+/, '$1')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return val
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return val
  }
}

function evalCount(): number {
  return evalHistory.value.length
}

function overallScore(): string {
  if (!latestEval.value) return '--'
  const f = latestEval.value.avg_faithfulness ?? latestEval.value.faithfulness
  const p = latestEval.value.avg_context_precision ?? latestEval.value.context_precision
  const r = latestEval.value.avg_context_recall ?? latestEval.value.context_recall
  const a = latestEval.value.avg_answer_relevancy ?? latestEval.value.answer_relevancy
  const scores = [f, p, r, a].filter((v): v is number => v !== undefined && v !== null)
  if (scores.length === 0) return '--'
  const avg = scores.reduce((sum, v) => sum + v, 0) / scores.length
  return avg.toFixed(3)
}

// ═══════════════════════════════════════════════════════════════
// Chart helpers
// ═══════════════════════════════════════════════════════════════

const DAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const CHART_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-1)', 'var(--chart-2)']

interface DayBar {
  label: string
  value: number
  height: string
  color: string
}

function computeDayBars(): DayBar[] {
  const daily = stats.value?.daily_queries ?? {}
  const max = Math.max(...Object.values(daily), 1)
  return DAY_LABELS.map((label, i) => {
    const value = daily[label] ?? 0
    const height = `${(value / max) * 100}%`
    return { label, value, height, color: CHART_COLORS[i] }
  })
}

function latencyBarWidth(ms?: number): string {
  if (!ms) return '0%'
  return `${Math.min((ms / 10000) * 100, 100)}%`
}

function scoreBarWidth(score?: number): string {
  if (score === undefined || score === null) return '0%'
  return `${Math.min(score * 100, 100)}%`
}

// ═══════════════════════════════════════════════════════════════
// Data fetching
// ═══════════════════════════════════════════════════════════════

async function fetchAll() {
  loading.value = true
  error.value = ''
  try {
    const [statsRes, evalRes, historyRes] = await Promise.all([
      api.get('/stats/'),
      api.get('/evaluation/latest'),
      api.get('/evaluation/history'),
    ])
    stats.value = statsRes.data
    if (evalRes.data && evalRes.data.status !== 'empty') {
      latestEval.value = evalRes.data
    } else {
      latestEval.value = null
    }
    const list = historyRes.data.history ?? (Array.isArray(historyRes.data) ? historyRes.data : [])
    evalHistory.value = list
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '获取数据失败'
  } finally {
    loading.value = false
  }
}

// ═══════════════════════════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════════════════════════

watch(autoRefresh, (val) => {
  if (val) {
    timer = setInterval(fetchAll, 5000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
})

onMounted(() => {
  fetchAll()
  if (autoRefresh.value) {
    timer = setInterval(fetchAll, 5000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="dashboard">
    <!-- ===== Header ===== -->
    <header class="page-header">
      <div class="page-header-text">
        <h1>系统概览</h1>
        <p>RAG 管线运行指标</p>
      </div>
      <div class="auto-refresh">
        <span :class="['auto-refresh-dot', { active: autoRefresh }]"></span>
        <span>{{ autoRefresh ? '自动刷新 (5s)' : '已暂停' }}</span>
        <button
          class="auto-refresh-toggle"
          :title="autoRefresh ? '暂停自动刷新' : '恢复自动刷新'"
          :aria-label="autoRefresh ? '暂停自动刷新' : '恢复自动刷新'"
          @click="autoRefresh = !autoRefresh"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="1 4 1 10 7 10" />
            <polyline points="23 20 23 14 17 14" />
            <path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" />
          </svg>
        </button>
      </div>
    </header>

    <!-- Loading / Error -->
    <div v-if="loading && !stats" class="state-box">加载中...</div>
    <div v-else-if="error" class="state-box error-box">
      <p>{{ error }}</p>
      <button @click="fetchAll">重试</button>
    </div>

    <template v-else>
      <!-- ===== KPI Grid ===== -->
      <section class="kpi-grid">
        <div class="kpi-card">
          <span class="kpi-card-label">总查询数</span>
          <span class="kpi-card-value">{{ stats?.total_queries ?? 0 }}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-card-label">缓存命中率</span>
          <span class="kpi-card-value success">{{ formatPercent(stats?.cache_hit_rate) }}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-card-label">忠实度警告率</span>
          <span class="kpi-card-value" :class="{ warning: (stats?.faithfulness_warning_rate ?? 0) > 0.1, muted: (stats?.faithfulness_warning_rate ?? 0) <= 0.1 }">
            {{ formatPercent(stats?.faithfulness_warning_rate) }}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-card-label">P50 延迟</span>
          <span class="kpi-card-value">{{ formatMs(extractLatency(stats?.latency_p50)) }}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-card-label">P95 延迟</span>
          <span class="kpi-card-value">{{ formatMs(extractLatency(stats?.latency_p95)) }}</span>
        </div>
      </section>

      <!-- ===== RAGAS Average Metrics ===== -->
      <section class="card">
        <h2 class="card-title">RAGAS 平均指标</h2>
        <div v-if="!latestEval" class="eval-empty">暂无评估数据</div>
        <div v-else class="ragas-list">
          <div class="ragas-row">
            <div class="ragas-row-header">
              <span class="ragas-row-label">忠实度</span>
              <span class="ragas-row-value">{{ formatScore(latestEval.avg_faithfulness ?? latestEval.faithfulness) }}</span>
            </div>
            <div class="ragas-bar-track">
              <div class="ragas-bar-fill" :style="{ width: scoreBarWidth(latestEval.avg_faithfulness ?? latestEval.faithfulness), background: 'var(--chart-5)' }"></div>
            </div>
          </div>
          <div class="ragas-row">
            <div class="ragas-row-header">
              <span class="ragas-row-label">上下文精确率</span>
              <span class="ragas-row-value">{{ formatScore(latestEval.avg_context_precision ?? latestEval.context_precision) }}</span>
            </div>
            <div class="ragas-bar-track">
              <div class="ragas-bar-fill" :style="{ width: scoreBarWidth(latestEval.avg_context_precision ?? latestEval.context_precision), background: 'var(--chart-4)' }"></div>
            </div>
          </div>
          <div class="ragas-row">
            <div class="ragas-row-header">
              <span class="ragas-row-label">上下文召回率</span>
              <span class="ragas-row-value">{{ formatScore(latestEval.avg_context_recall ?? latestEval.context_recall) }}</span>
            </div>
            <div class="ragas-bar-track">
              <div class="ragas-bar-fill" :style="{ width: scoreBarWidth(latestEval.avg_context_recall ?? latestEval.context_recall), background: 'var(--chart-3)' }"></div>
            </div>
          </div>
          <div class="ragas-row">
            <div class="ragas-row-header">
              <span class="ragas-row-label">答案相关性</span>
              <span class="ragas-row-value">{{ formatScore(latestEval.avg_answer_relevancy ?? latestEval.answer_relevancy) }}</span>
            </div>
            <div class="ragas-bar-track">
              <div class="ragas-bar-fill" :style="{ width: scoreBarWidth(latestEval.avg_answer_relevancy ?? latestEval.answer_relevancy), background: 'var(--chart-4)' }"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== Two Column: Latency + Cache ===== -->
      <div class="two-col">
        <!-- Latency Distribution -->
        <section class="card">
          <h2 class="card-title">延迟分布</h2>
          <div class="latency-bars">
            <div class="latency-row">
              <span class="latency-row-label">P50</span>
              <div class="latency-bar-track">
                <div class="latency-bar-fill p50" :style="{ width: latencyBarWidth(extractLatency(stats?.latency_p50)) }"></div>
              </div>
              <span class="latency-row-value">{{ formatMs(extractLatency(stats?.latency_p50)) }}</span>
            </div>
            <div class="latency-row">
              <span class="latency-row-label">P95</span>
              <div class="latency-bar-track">
                <div class="latency-bar-fill p95" :style="{ width: latencyBarWidth(extractLatency(stats?.latency_p95)) }"></div>
              </div>
              <span class="latency-row-value">{{ formatMs(extractLatency(stats?.latency_p95)) }}</span>
            </div>
          </div>
          <div class="latency-detail-grid">
            <div class="latency-detail-item">
              <span class="latency-detail-label">平均检索耗时</span>
              <span class="latency-detail-value">{{ formatMs(stats?.avg_retrieve_ms) }}</span>
            </div>
            <div class="latency-detail-item">
              <span class="latency-detail-label">平均生成耗时</span>
              <span class="latency-detail-value">{{ formatMs(stats?.avg_generate_ms) }}</span>
            </div>
            <div class="latency-detail-item">
              <span class="latency-detail-label">平均检索文档数</span>
              <span class="latency-detail-value">{{ stats?.avg_retrieval_count?.toFixed(1) ?? '--' }}</span>
            </div>
            <div class="latency-detail-item">
              <span class="latency-detail-label">忠实度警告次数</span>
              <span class="latency-detail-value">{{ stats?.faithfulness_warnings ?? 0 }}</span>
            </div>
          </div>
        </section>

        <!-- Cache Statistics -->
        <section class="card">
          <h2 class="card-title">缓存统计</h2>
          <div class="cache-stats">
            <div class="cache-block">
              <span class="cache-block-value hit">{{ stats?.cache_hits ?? 0 }}</span>
              <span class="cache-block-label">缓存命中</span>
            </div>
            <div class="cache-block">
              <span class="cache-block-value miss">{{ stats?.cache_misses ?? 0 }}</span>
              <span class="cache-block-label">缓存未命中</span>
            </div>
          </div>
        </section>
      </div>

      <!-- ===== Query Trends ===== -->
      <section class="card">
        <h2 class="card-title">查询趋势</h2>
        <div class="chart-container">
          <div class="chart-col" v-for="bar in computeDayBars()" :key="bar.label">
            <span class="chart-col-value">{{ bar.value }}</span>
            <div class="chart-bar-wrapper">
              <div class="chart-bar" :style="{ height: bar.height, background: bar.color }"></div>
            </div>
            <span class="chart-col-label">{{ bar.label }}</span>
          </div>
        </div>
      </section>

      <!-- ===== Recent Evaluation ===== -->
      <section class="card">
        <div class="card-title-row">
          <h2 class="card-title">最近评估</h2>
          <a class="card-link" href="#" @click.prevent="router.push('/evaluation')">查看全部</a>
        </div>
        <div v-if="!latestEval && evalHistory.length === 0" class="eval-empty">暂无评估数据</div>
        <div v-else class="eval-summary-row">
          <div class="eval-summary-item">
            <span class="eval-summary-label">最近评估时间</span>
            <span class="eval-summary-value">{{ formatDate(latestEval?.created_at || latestEval?.timestamp) }}</span>
          </div>
          <div class="eval-summary-item">
            <span class="eval-summary-label">评估条数</span>
            <span class="eval-summary-value">{{ (latestEval?.total_evaluated ?? latestEval?.dataset_size ?? 0) }} 条</span>
          </div>
          <div class="eval-summary-item">
            <span class="eval-summary-label">综合得分</span>
            <span class="eval-summary-value">{{ overallScore() }}</span>
          </div>
          <div class="eval-summary-item">
            <span class="eval-summary-label">评估次数</span>
            <span class="eval-summary-value">{{ evalCount() }} 次</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   DashboardView — Design System Styles
   ═══════════════════════════════════════════════════════════════ */

.dashboard {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 36px 48px;
}

/* ===== Header ===== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 28px;
  gap: 16px;
}

.page-header-text h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--foreground);
  line-height: 1.3;
  margin: 0;
}

.page-header-text p {
  font-size: 13px;
  color: var(--muted-foreground);
  margin-top: 3px;
  margin-bottom: 0;
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.auto-refresh-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border);
  transition: background 0.2s;
}

.auto-refresh-dot.active {
  background: var(--success);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.auto-refresh-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--muted-foreground);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.auto-refresh-toggle:hover {
  background: var(--muted);
  color: var(--foreground);
}

.auto-refresh-toggle svg {
  width: 14px;
  height: 14px;
}

/* ===== State Boxes ===== */
.state-box {
  text-align: center;
  padding: 40px;
  color: var(--muted-foreground);
  font-size: 14px;
}

.error-box {
  color: var(--destructive);
}

.error-box button {
  margin-top: 12px;
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}

.error-box button:hover {
  background: var(--muted);
}

/* ===== KPI Grid ===== */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.kpi-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kpi-card-label {
  font-size: 12px;
  font-weight: 450;
  color: var(--muted-foreground);
  letter-spacing: 0.01em;
}

.kpi-card-value {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--foreground);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.kpi-card-value.success {
  color: var(--success);
}

.kpi-card-value.muted {
  color: var(--muted-foreground);
}

.kpi-card-value.warning {
  color: var(--destructive);
}

/* ===== Section Cards ===== */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 22px 24px;
  margin-bottom: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  margin: 0 0 18px 0;
  letter-spacing: -0.01em;
}

/* ===== RAGAS Metrics ===== */
.ragas-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ragas-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ragas-row-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.ragas-row-label {
  font-size: 13px;
  font-weight: 450;
  color: var(--foreground);
}

.ragas-row-value {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  letter-spacing: -0.02em;
}

.ragas-bar-track {
  width: 100%;
  height: 6px;
  background: var(--muted);
  border-radius: 3px;
  overflow: hidden;
}

.ragas-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

/* ===== Two Column Layout ===== */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.two-col > .card {
  margin-bottom: 0;
}

/* ===== Latency Distribution ===== */
.latency-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.latency-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.latency-row-label {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  width: 32px;
  flex-shrink: 0;
  letter-spacing: -0.02em;
}

.latency-bar-track {
  flex: 1;
  height: 6px;
  background: var(--muted);
  border-radius: 3px;
  overflow: hidden;
}

.latency-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.latency-bar-fill.p50 {
  background: var(--chart-5);
}

.latency-bar-fill.p95 {
  background: var(--chart-2);
}

.latency-row-value {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  width: 36px;
  text-align: right;
  flex-shrink: 0;
  letter-spacing: -0.02em;
}

.latency-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.latency-detail-item {
  background: var(--card);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.latency-detail-label {
  font-size: 12px;
  font-weight: 450;
  color: var(--muted-foreground);
}

.latency-detail-value {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

/* ===== Cache Stats ===== */
.cache-stats {
  display: flex;
  align-items: stretch;
  height: 100%;
}

.cache-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 20px;
}

.cache-block:first-child {
  border-right: 1px solid var(--border);
}

.cache-block-value {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.cache-block-value.hit {
  color: var(--primary);
}

.cache-block-value.miss {
  color: var(--muted-foreground);
}

.cache-block-label {
  font-size: 13px;
  font-weight: 450;
  color: var(--muted-foreground);
}

/* ===== Query Trends Chart ===== */
.chart-container {
  display: flex;
  align-items: flex-end;
  gap: 0;
  height: 140px;
  padding-top: 8px;
}

.chart-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  height: 100%;
  justify-content: flex-end;
}

.chart-bar-wrapper {
  width: 100%;
  max-width: 40px;
  height: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.chart-bar {
  width: 100%;
  border-radius: 3px 3px 0 0;
  transition: height 0.4s ease;
}

.chart-col-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-foreground);
  font-family: var(--font-mono);
}

.chart-col-value {
  font-size: 11px;
  font-weight: 500;
  color: var(--foreground);
  font-family: var(--font-mono);
  letter-spacing: -0.02em;
}

/* ===== Card Title Row ===== */
.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-title-row .card-title {
  margin-bottom: 0;
}

.card-link {
  font-size: 12px;
  color: var(--muted-foreground);
  text-decoration: none;
}

.card-link:hover {
  color: var(--foreground);
}

/* ===== Evaluation Summary ===== */
.eval-summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.eval-summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--muted);
  border-radius: var(--radius-sm);
}

.eval-summary-label {
  font-size: 11px;
  color: var(--muted-foreground);
}

.eval-summary-value {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
  font-variant-numeric: tabular-nums;
}

.eval-empty {
  text-align: center;
  padding: 24px;
  color: var(--muted-foreground);
  font-size: 13px;
}

/* ===== Responsive ===== */
@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 860px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>