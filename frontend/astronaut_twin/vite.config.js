import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    lib: {
      entry: path.resolve(__dirname, 'src/main.jsx'),
      name: 'AstronautTwin',
      fileName: () => 'astronaut-twin.js',
      formats: ['es']
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'astronaut-twin.css';
          }
          return assetInfo.name || 'assets/[name].[ext]';
        }
      }
    }
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify('production')
  }
});
