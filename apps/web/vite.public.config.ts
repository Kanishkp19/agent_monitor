import { defineConfig, type Plugin } from 'vite'
import base from './vite.config'

const readOnlyApi: Plugin = {
  name: 'public-preview-read-only-api',
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      const path = new URL(request.url ?? '/', 'http://localhost').pathname
      const method = request.method ?? 'GET'
      const autopilotWrite = method === 'POST' && (
        path === '/api/v1/autopilot/jobs' ||
        /^\/api\/v1\/autopilot\/jobs\/ap_[a-f0-9]+\/reset$/.test(path)
      )
      if (path.startsWith('/api/') && !autopilotWrite && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        response.statusCode = 403
        response.setHeader('Content-Type', 'application/json')
        response.end(JSON.stringify({ error: {
          code: 'read_only_demo', message: 'Public preview is read-only outside Autopilot.',
        } }))
        return
      }
      next()
    })
  },
}

// Keep the public preview on its own port. The rest of the app can read live
// state, while only token-protected Autopilot endpoints can accept writes.
export default defineConfig({
  ...base,
  plugins: [...(base.plugins ?? []), readOnlyApi],
  server: {
    ...base.server,
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    allowedHosts: ['.ngrok-free.dev', '.ngrok.app', '.ngrok-free.app'],
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8001', ws: true },
    },
  },
})
