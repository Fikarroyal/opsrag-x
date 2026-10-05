import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'

// In development /api is proxied to the FastAPI backend (VITE_API_PROXY, default http://localhost:8000).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: { port: 5173, host: true, proxy: { '/api': { target: process.env.VITE_API_PROXY ?? 'http://localhost:8000', changeOrigin: true } } },
  build: { chunkSizeWarningLimit: 1200 },
})
