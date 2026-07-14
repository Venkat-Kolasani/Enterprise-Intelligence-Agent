import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/agent': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/simulation': 'http://localhost:8000',
      '/signals': 'http://localhost:8000',
      '/insights': 'http://localhost:8000',
      '/recommendations': 'http://localhost:8000',
    },
  },
})
