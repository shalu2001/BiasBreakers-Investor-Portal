import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { applyColorTheme } from './theme/colors'
import { applyFontTheme } from './theme/fonts'
import { SessionProvider } from './session/SessionContext'
import { AuthProvider } from './session/AuthContext'
import './index.css'
import App from './App.tsx'

applyColorTheme()
applyFontTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <SessionProvider>
          <App />
        </SessionProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
