import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    // The app talks to same-origin `/api/v1` and `/ws` in every environment,
    // so nothing in `src/` ever needs to know a host. Production points the
    // same paths at the deployed API.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Phaser is ~1.2 MB and only the office route needs it. Splitting it
          // out keeps the console's first paint off the critical path of a
          // game engine.
          phaser: ['phaser'],
          charts: ['recharts'],
        },
      },
    },
  },
})
