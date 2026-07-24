import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  publicDir: 'vendor',
  build: {
    outDir: resolve(__dirname, '../backend/app/static'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        manage: resolve(__dirname, 'manage.html'),
        use_function: resolve(__dirname, 'use_function.html'),
        feed_back: resolve(__dirname, 'feed_back.html'),
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
  server: {
    proxy: {
      '/graph': 'http://localhost:8522',
      '/index': 'http://localhost:8522',
      '/response': 'http://localhost:8522',
      '/manage': 'http://localhost:8522',
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
});
