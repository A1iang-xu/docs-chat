/**
 * useSSE — 管理 SSE 流式连接的 Composable
 * 支持断线重连、心跳检测、AbortController 中断
 *
 * v4.5: connect() 中先 cancel 前一个 reader 再发起新请求，
 * 彻底消除浏览器 ERR_ABORTED（根因：旧 reader 持有 HTTP 连接导致新 fetch 冲突）。
 */
import { ref, onUnmounted } from 'vue'
import type { SourceCitation, SSEEvent } from '@/types'

export interface SSEOptions {
  maxRetries?: number
  retryBaseMs?: number
  heartbeatTimeoutMs?: number
}

export function useSSE(options: SSEOptions = {}) {
  const { maxRetries = 3, retryBaseMs = 1000, heartbeatTimeoutMs = 120_000 } = options

  const content = ref('')
  const sources = ref<SourceCitation[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const cacheHit = ref(false)
  const stage = ref<string>('')
  const stageLabel = ref<string>('')
  const faithfulnessWarning = ref<string | null>(null)

  let abortController: AbortController | null = null
  let retryCount = 0
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null

  // v4.5: 请求令牌 + 活跃 reader 引用
  let requestToken = 0
  let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null

  function resetHeartbeat() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => {
      abort('心跳超时，连接已断开')
    }, heartbeatTimeoutMs)
  }

  function clearHeartbeat() {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function abort(reason?: string) {
    requestToken++
    // v4.5: 先 cancel reader 再 abort controller，确保 HTTP 连接正确关闭
    if (activeReader) {
      try { activeReader.cancel() } catch { /* already cancelled */ }
      activeReader = null
    }
    abortController?.abort()
    abortController = null
    isStreaming.value = false
    clearHeartbeat()
    if (reason) error.value = reason
  }

  async function connect(url: string, body: Record<string, unknown>) {
    // v4.5: 关键修复 —— 先正确关闭前一个 reader 的 HTTP 连接，再发起新请求
    // 这才是 ERR_ABORTED 的根因：旧 reader 持有连接，新 fetch 与之冲突
    requestToken++
    if (activeReader) {
      try { await activeReader.cancel() } catch { /* ignore */ }
      activeReader = null
    }
    abortController?.abort()
    abortController = null
    clearHeartbeat()

    content.value = ''
    sources.value = []
    error.value = null
    cacheHit.value = false
    stage.value = ''
    stageLabel.value = ''
    faithfulnessWarning.value = null
    isStreaming.value = true
    retryCount = 0
    await doConnect(url, body)
  }

  async function doConnect(url: string, body: Record<string, unknown>) {
    const myToken = requestToken
    const myController = new AbortController()
    abortController = myController

    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null

    try {
      resetHeartbeat()

      const token = localStorage.getItem('docschat_token') || import.meta.env.VITE_DEV_AUTH_TOKEN
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: myController.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      reader = response.body?.getReader() ?? null
      if (!reader) throw new Error('无法获取响应流')
      activeReader = reader  // v4.5: 全局引用，供 connect() cancel

      const decoder = new TextDecoder()
      let buffer = ''
      let doneReceived = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // v4.5: 检查令牌 —— 新请求已发起，退出（reader 已被 connect() cancel）
        if (myToken !== requestToken) {
          return
        }

        if (!doneReceived) {
          resetHeartbeat()
        }

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith(':') || line.trim() === '') continue

          if (line.startsWith('data: ')) {
            try {
              const event: SSEEvent = JSON.parse(line.slice(6))

              switch (event.event) {
                case 'token':
                  content.value += event.data
                  break
                case 'source':
                  sources.value = JSON.parse(event.data) as SourceCitation[]
                  break
                case 'done':
                  if (myToken === requestToken) {
                    isStreaming.value = false
                    stage.value = ''
                    stageLabel.value = ''
                    clearHeartbeat()
                    abortController = null
                  }
                  doneReceived = true
                  break
                case 'error':
                  if (myToken === requestToken) {
                    error.value = event.data
                    isStreaming.value = false
                    clearHeartbeat()
                    abortController = null
                  }
                  doneReceived = true
                  break
                case 'cache':
                  cacheHit.value = true
                  break
                case 'stage':
                  try {
                    const stageData = JSON.parse(event.data)
                    stage.value = stageData.stage || ''
                    stageLabel.value = stageData.label || ''
                  } catch { /* ignore */ }
                  break
                case 'faithfulness_warning':
                  console.warn('[SSE] 忠实度警告:', event.data)
                  try {
                    const warnData = JSON.parse(event.data)
                    if (warnData.clear_content) {
                      content.value = ''
                    }
                    faithfulnessWarning.value = warnData.retries_exhausted
                      ? '部分信息无法从文档中完全确认，请注意甄别'
                      : '正在修正可能不准确的回答...'
                  } catch {
                    faithfulnessWarning.value = '答案忠实度校验中...'
                  }
                  break
              }
            } catch { /* 非 JSON 行 */ }
          }
        }
      }

      // 流自然结束
      if (myToken === requestToken) {
        isStreaming.value = false
        clearHeartbeat()
        abortController = null
      }
    } catch (e: unknown) {
      if ((e as Error).name === 'AbortError') return
      if (myToken !== requestToken) return

      if (retryCount < maxRetries) {
        retryCount++
        const delay = retryBaseMs * Math.pow(2, retryCount - 1)
        console.warn(`[SSE] 重连 ${retryCount}/${maxRetries}，等待 ${delay}ms`)
        await new Promise((r) => setTimeout(r, delay))
        if (myToken === requestToken) {
          return doConnect(url, body)
        }
        return
      }

      error.value = (e as Error).message
      isStreaming.value = false
      clearHeartbeat()
      abortController = null
    } finally {
      // v4.5: 释放 reader 锁，清除全局引用
      if (reader) {
        try { reader.releaseLock() } catch { /* already released */ }
      }
      if (activeReader === reader) {
        activeReader = null
      }
    }
  }

  onUnmounted(() => {
    if (isStreaming.value) {
      abort()
    }
  })

  return { content, sources, isStreaming, error, cacheHit, stage, stageLabel, faithfulnessWarning, connect, abort }
}
