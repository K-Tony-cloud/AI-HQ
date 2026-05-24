import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/operation-timeline/',
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react:  ['react', 'react-dom'],
          vendor: ['clsx', 'date-fns'],
        },
      },
    },
  },
})
