import { defineConfig } from 'vite'
import base from './vite.config'

// Keep the public preview on its own port and expose only the authenticated
// Autopilot API. Other local API routes must never pass through this proxy.
export default defineConfig({
  ...base,
  server: {
    ...base.server,
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    allowedHosts: ['.ngrok-free.dev', '.ngrok.app', '.ngrok-free.app'],
    proxy: {
      '/api/v1/autopilot': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
})
