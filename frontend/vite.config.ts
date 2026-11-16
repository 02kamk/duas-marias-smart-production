import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

// Única interface em React: a Gestão. O build vai direto para a pasta que o
// servidor Python publica em /gestao; emptyOutDir evita acumular builds antigos.
export default defineConfig({
  plugins: [tailwindcss()],
  base: '/gestao-assets/',
  server: { host: '127.0.0.1', open: '/gestao.html', proxy: { '/api': 'http://127.0.0.1:8000', '/static': 'http://127.0.0.1:8000' } },
  build: { outDir: '../src/pontocerto/management/static', emptyOutDir: true, rollupOptions: { input: 'gestao.html' } },
});
