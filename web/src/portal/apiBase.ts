/* Where the API lives.

   In development Vite proxies `/api` to uvicorn, and in the bundled build FastAPI serves the
   frontend from its own origin — in both cases a bare `/api/...` path is correct and nothing
   here does anything.

   A split deployment is the case this exists for. The frontend is a static bundle and hosts
   anywhere; the Python service cannot follow it onto a serverless platform, because torch,
   sentence-transformers and EasyOCR exceed the function size limit on their own, MahaSBERT's
   weights are 1.9 GB, and Ollama is a separate daemon on localhost. So the API is hosted
   separately and its origin is supplied at build time:

       VITE_API_BASE=https://gr-api.example.org

   ## Why this rewrites `fetch` instead of touching the call sites

   There are eighteen `fetch('/api/...')` calls across eight files. Prefixing each one is
   eighteen chances to miss one, and a missed one fails only in the split deployment — which is
   exactly where nobody is watching. Rewriting at the boundary means a call site cannot get it
   wrong, including call sites added later.

   Only same-document `/api/` paths are touched. Absolute URLs, the portal PDF links on
   `gr.maharashtra.gov.in`, and everything else pass through untouched. */

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')

export const apiBase = BASE

export function installApiBase(): void {
  if (!BASE || typeof window === 'undefined') return
  const original = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      return original(BASE + input, init)
    }
    if (input instanceof Request && new URL(input.url, location.href).pathname.startsWith('/api/')) {
      const u = new URL(input.url, location.href)
      return original(new Request(BASE + u.pathname + u.search, input), init)
    }
    return original(input, init)
  }
}
