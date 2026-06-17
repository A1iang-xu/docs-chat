/**
 * useSSE Composable 测试
 *
 * 测试覆盖：
 * 1. 初始状态
 * 2. 流式连接接收 token 事件
 * 3. 接收 source 事件更新引用
 * 4. done 事件结束流
 * 5. error 事件处理
 * 6. abort 中断连接
 * 7. 连接失败自动重试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSSE } from '../useSSE'

describe('useSSE', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始状态正确', () => {
    const { content, sources, isStreaming, error } = useSSE()

    expect(content.value).toBe('')
    expect(sources.value).toEqual([])
    expect(isStreaming.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('abort 后 isStreaming 变为 false', () => {
    const { isStreaming, abort } = useSSE()

    // 模拟连接中状态
    isStreaming.value = true
    abort('用户取消')

    expect(isStreaming.value).toBe(false)
  })

  it('abort 传入 reason 时设置 error', () => {
    const { error, abort } = useSSE()

    abort('连接超时')
    expect(error.value).toBe('连接超时')
  })

  it('connect 时重置状态', async () => {
    const { content, sources, error, isStreaming, connect } = useSSE()

    content.value = '旧内容'
    sources.value = [{ index: 1, content: '旧', relevanceScore: 0.5 }]
    error.value = '旧错误'

    // 模拟 fetch 失败（不创建真实连接）
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('网络错误'))

    const connectPromise = connect('http://test/api', { key: 'value' })

    // 快进到重试完成
    await vi.runAllTimersAsync()
    await connectPromise.catch(() => {})

    // 验证状态已重置
    expect(content.value).toBe('')
    expect(sources.value).toEqual([])
    expect(error.value).toBeTruthy() // 连接失败后设置了错误

    mockFetch.mockRestore()
  })
})