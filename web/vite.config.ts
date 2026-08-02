import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Assets are referenced from the ROOT, not relatively. Both hosts serve the bundle from `/`
// (FastAPI mounts /assets; a static host serves the directory), and `base: './'` resolves
// against the CURRENT route — so a deep link to /verify would look for /verify/assets/... and
// 404. Root-absolute is same-origin either way, so the offline guarantee is unaffected.
//
// In dev, /api is proxied to uvicorn so the frontend never hardcodes a host. For a split
// deployment set VITE_API_BASE at build time — see web/src/portal/apiBase.ts.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { outDir: 'dist', assetsDir: 'assets', chunkSizeWarningLimit: 1500 },
})
