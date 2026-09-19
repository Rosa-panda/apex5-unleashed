import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { api } from './api'

// 全局 JS 错误上报（事件处理器等 React 边界外的错）：落后端 apex5.log
window.addEventListener('error', e =>
  api.uiError(e.message, e.error?.stack ?? '', `global:${location.pathname}`))
window.addEventListener('unhandledrejection', e =>
  api.uiError(String(e.reason), '', 'unhandledrejection'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
