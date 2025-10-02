import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.RETELL_API_KEY': 'undefined',
    'process.env.OPENAI_API_KEY': 'undefined'
  },
  server: {
    host: true,
    port: 5173
  }
})
