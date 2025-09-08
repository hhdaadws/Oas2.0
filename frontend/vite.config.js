import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 9000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:9001',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:9001',
        ws: true,
        changeOrigin: true
      }
    }
  }
})