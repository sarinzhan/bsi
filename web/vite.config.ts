import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// npm run dev: the browser calls /api on this server, which forwards it to platform-api.
// Point it elsewhere with PLATFORM_API_URL (default http://localhost:8000).
// BSI_BASE_PATH: where the app lives, e.g. "/bsi/" behind a shared nginx (default "/"). Fixed at build time.
export default defineConfig({
  base: process.env.BSI_BASE_PATH ?? '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.PLATFORM_API_URL ?? 'http://localhost:8000', changeOrigin: true } },
  },
});
