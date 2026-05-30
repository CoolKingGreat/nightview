import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import cesium from 'vite-plugin-cesium';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const repoRoot = path.resolve(process.cwd(), '..');
  const env = loadEnv(mode, repoRoot, '');
  const backendUrl = env.VITE_BACKEND_URL || env.VITE_API_BASE || 'http://localhost:8000';

  return {
    plugins: [react(), cesium()],
    envDir: repoRoot,
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  };
});
