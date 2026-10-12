import path from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { inspectAttr } from 'kimi-plugin-inspect-react';

// The attribution API stays on 127.0.0.1:8010. Colleagues access only the
// frontend on the office LAN; /api requests remain proxied server-side, so
// MaxCompute credentials are never exposed to browsers.
export default defineConfig({
  base: './',
  plugins: [inspectAttr(), react()],
  build: {
    rollupOptions: {
      output: {
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          if (id.includes('commonjsHelpers')) return 'vendor-runtime';
          if (!id.includes('/node_modules/')) return undefined;
          if (/\/node_modules\/(echarts|echarts-for-react|zrender)\//.test(id)) return 'vendor-charts';
          if (/\/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler|cookie|set-cookie-parser)\//.test(id)) return 'vendor-react';
          if (/\/node_modules\/(framer-motion|motion-dom|motion-utils)\//.test(id)) return 'vendor-motion';
          if (id.includes('/node_modules/lucide-react/')) return 'vendor-icons';
          return undefined;
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    // 归因预计算管线会锁定/重写 server/data 下的 DuckDB WAL、parquet 快照与 SQLite 库；
    // chokidar 对被锁文件建 watcher 会抛 EBUSY 并击穿整个 dev server（进程直接退出），
    // 因此必须把数据目录排除在 HMR 文件监听之外。
    watch: {
      ignored: [
        '**/server/data/**',
        '**/*.duckdb*',
        '**/*.parquet',
        '**/dist/**',
        '**/.pytest_tmp*/**',
        '**/agentmonitor.pytest_tmp*/**',
        '**/.superpowers/**',
      ],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
