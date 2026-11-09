import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[tailwindcss()],base:'/gestao-assets/',build:{outDir:'../pontocerto/src/pontocerto/management/static',emptyOutDir:false,rollupOptions:{input:'gestao.html'}}});
