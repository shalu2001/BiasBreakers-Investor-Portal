import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Open the browser on the login screen so the first-run flow is
  // Login -> Onboarding -> Behavioural game -> Dashboard.
  server: { open: '/login' },
})
