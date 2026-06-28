import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    // 代码分割：将大型依赖拆分为独立 chunk
    rollupOptions: {
      output: {
        // Rollup 4: manualChunks 必须为函数，对象形式已废弃
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            if (id.includes('vue') || id.includes('pinia')) return 'vendor-vue'
            if (id.includes('marked') || id.includes('highlight.js')) return 'vendor-marked'
            if (id.includes('@vueuse')) return 'vendor-vueuse'
            return 'vendor'
          }
        },
      },
    },
    // 提高 chunk 大小警告阈值（marked + highlight.js 较大）
    chunkSizeWarningLimit: 600,
    // 生成 sourcemap 用于生产环境调试
    sourcemap: false,
  },
  // 开发服务器配置
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})