import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 单独成文件而不是塞进 vite.config.js：dev/build 不需要测试环境，
// 而 vitest 会优先认 vitest.config.js，两边互不干扰。
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom', // useChat 摸不到 DOM 也要 mount ChatInput，一个口径到底
    include: ['tests/**/*.test.js'],
  },
})
