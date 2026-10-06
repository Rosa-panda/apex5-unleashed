import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 手动分包：单 chunk 515KB 会触发 Vite 默认 500KB 告警。这里只做「按依赖边界拆 vendor」，
  // 不引入路由级懒加载（那会改 App.tsx 的导航结构，属业务变更）——react 与 matter-js 各自独立，
  // 业务代码留在入口 chunk 里，加载顺序由 Rollup 保证。
  // 用函数式 manualChunks 而非对象字面量：本仓库 rollup 类型下对象字面量会命中
  // ManualChunksFunction 分支导致 `tsc -b` 报 TS2769。
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string): string | undefined {
          const p = id.replace(/\\/g, '/')
          if (p.includes('/node_modules/matter-js/')) return 'matter'
          if (/\/(node_modules\/)?(react|react-dom|scheduler)\//.test(p) ||
              p.endsWith('/node_modules/react/index.js')) return 'react'
          return undefined
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:18765',
      '/ws': { target: 'ws://127.0.0.1:18765', ws: true },
    },
  },
})
