import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
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
