import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.VITE_DEV_API_PROXY
  return {
    plugins: [react()],
    server: {
      allowedHosts: env.VITE_DEV_ALLOWED_HOST ? env.VITE_DEV_ALLOWED_HOST.split(',').map((host) => host.trim()).filter(Boolean) : [],
      proxy: target ? {
        '/backend': {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/backend/, ''),
        },
      } : undefined,
    },
  }
})
