import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api、/ws、/static 代理到本地后端，避免跨域与端口硬编码。
const BACKEND = process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
})
