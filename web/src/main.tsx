import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './portal.css'
import App from './App'
import { installApiBase } from './portal/apiBase'

// Must run before the first request. No-op unless VITE_API_BASE is set at build time.
installApiBase()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
