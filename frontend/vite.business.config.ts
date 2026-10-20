import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[tailwindcss()],base:'/business-assets/',build:{outDir:'../pontocerto/src/pontocerto/business/static',emptyOutDir:false,rollupOptions:{input:'business.html'}}});
