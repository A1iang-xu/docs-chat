/**
 * Axios 实例 + 请求/响应拦截器
 * 统一管理 baseURL、错误处理、Token 等
 */
import axios, { type AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器 ──
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('docschat_token') || import.meta.env.VITE_DEV_AUTH_TOKEN
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => Promise.reject(error),
)

// ── 响应拦截器 ──
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<ApiError>) => {
    const detail = error.response?.data?.detail || error.message || '网络请求失败'
    console.error(`[API Error] ${error.config?.url}: ${detail}`)
    return Promise.reject(error)
  },
)

export default api
