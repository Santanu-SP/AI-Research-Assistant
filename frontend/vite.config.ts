import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Listen on localhost only. Set VITE_DEV_HOST=0.0.0.0 to test from
    // another device on your network (and enable CORS_ALLOW_LOCAL_NETWORK).
    host: process.env.VITE_DEV_HOST || '127.0.0.1',
    port: 3000,
  },
  resolve: {
    preserveSymlinks: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Use the filesystem root to avoid Windows case-sensitivity issues
    root: path.resolve(__dirname),
    typecheck: {
      tsconfig: './tsconfig.test.json',
    },
  },
});
