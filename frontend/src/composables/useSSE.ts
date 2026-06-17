/**
 * useSSE — 管理 SSE 流式连接的 Composable
 * 支持断线重连、心跳检测、AbortController 中断
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

  let abortController: AbortController | null = null
  let retryCount = 0
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null

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
    abortController?.abort()
    isStreaming.value = false
    clearHeartbeat()
    if (reason) error.value = reason
  }

  async function connect(url: string, body: Record<string, unknown>) {
    abort()
    content.value = ''
    sources.value = []
    error.value = null
    isStreaming.value = true
    retryCount = 0
    await doConnect(url, body)
  }

  async function doConnect(url: string, body: Record<string, unknown>) {
    abortController = new AbortController()

    try {
      resetHeartbeat()

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法获取响应流')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        resetHeartbeat()
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          // SSE 注释行（心跳），仅重置心跳计时器
          if (line.startsWith(':') || line.trim() === '') {
            continue
          }

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
                  isStreaming.value = false
                  clearHeartbeat()
                  return
                case 'error':
                  error.value = event.data
                  isStreaming.value = false
                  clearHeartbeat()
                  return
              }
            } catch {
              // 非 JSON 行，忽略
            }
          }
        }
      }

      isStreaming.value = false
      clearHeartbeat()
    } catch (e: unknown) {
      if ((e as Error).name === 'AbortError') return

      if (retryCount < maxRetries) {
        retryCount++
        const delay = retryBaseMs * Math.pow(2, retryCount - 1)
        console.warn(`[SSE] 重连 ${retryCount}/${maxRetries}，等待 ${delay}ms`)
        await new Promise((r) => setTimeout(r, delay))
        return doConnect(url, body)
      }

      error.value = (e as Error).message
      isStreaming.value = false
      clearHeartbeat()
    }
  }

  onUnmounted(() => {
    abort()
  })

  return { content, sources, isStreaming, error, connect, abort }
}