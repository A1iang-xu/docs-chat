/**
 * 测试环境初始化 —— 配置全局 Mock、stub 浏览器 API
 */
import { config } from '@vue/test-utils'
import { vi } from 'vitest'

// ── Stub 浏览器 API 中 Vitest 未提供的部分 ──
if (typeof globalThis.crypto === 'undefined') {
  vi.stubGlobal('crypto', {
    randomUUID: () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
    }),
    getRandomValues: (arr: Uint8Array) => {
      for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256)
      return arr
    },
  })
}

// ── 全局 Mock：import.meta.env ──
vi.stubGlobal('import.meta', {
  env: {
    VITE_API_BASE_URL: 'http://localhost:8000',
  },
})

// ── 关闭 Vue Test Utils 的全局 stubs 警告 ──
config.global.stubs = {
  transition: false,
}