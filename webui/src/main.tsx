import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles.css'

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

// Detect base path when served under /admin or /ui behind FastAPI
const base = (() => {
  try {
    const p = window.location.pathname
    if (p.startsWith('/admin')) return '/admin'
    if (p.startsWith('/ui')) return '/ui'
    return '/'
  } catch { return '/' }
})()

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename={base}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
