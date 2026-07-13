import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Package stub re-exports SoT (packages/brand-tokens/tokens.css → desktop SoT)
      '@melosviz/brand-tokens': path.resolve(
        repoRoot,
        'packages/brand-tokens/tokens.css',
      ),
    },
  },
  server: {
    // Allow importing the shared tokens file outside web/
    fs: { allow: [repoRoot] },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
