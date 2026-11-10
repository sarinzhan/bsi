import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// npm run dev: the browser calls /api on this server, which forwards it to platform-api.
// Point it elsewhere with PLATFORM_API_URL (default http://localhost:8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.PLATFORM_API_URL ?? 'http://localhost:8000', changeOrigin: true } },
  },
});
