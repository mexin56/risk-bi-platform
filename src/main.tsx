import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import PageLoadBoundary from './components/PageLoadBoundary'

const container = document.getElementById('root')
if (!container) throw new Error('页面挂载容器不存在')

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <PageLoadBoundary><App /></PageLoadBoundary>
    </BrowserRouter>
  </StrictMode>,
)
