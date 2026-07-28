import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The production build is served by FastAPI out of web/dist, so asset paths must be relative
// and same-origin — the demo runs with no network. In dev, /api is proxied to uvicorn so the
// frontend never hardcodes a host.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { outDir: 'dist', assetsDir: 'assets', chunkSizeWarningLimit: 1500 },
})
