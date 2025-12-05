import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 1442,
    proxy: {
      '/api': {
        target: 'http://localhost:1443',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:1443',
        ws: true,
      },
    },
  },
})
