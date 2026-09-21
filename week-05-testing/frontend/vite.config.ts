import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// Host uvicorn and the compose gateway both listen here.
const BACKEND_URL = 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // Same origin for the browser, so the backend needs no CORS.
  // Keys match by prefix; the trailing slash keeps routes like /authors in the app.
  server: {
    proxy: {
      '/api/': BACKEND_URL,
      '/auth/': BACKEND_URL,
    },
  },
})
