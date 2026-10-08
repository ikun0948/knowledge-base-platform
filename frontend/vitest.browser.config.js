import { defineConfig } from 'vitest/config'

// 与 vitest.config.js 分开，而不是往它的 include 里加一项：
// 那套 include 是 tests/**/*.test.js，本目录刻意叫 tests-browser/，
// 让 `npm test`（任何机器上都能跑的单位门）永远不会顺手拉起一个浏览器。
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests-browser/**/*.test.js'],
    // 同一时刻只开一个 Edge：两个进程抢同一个 userDataDir 会直接起不来。
    fileParallelism: false,
    // 真浏览器 + 真登录 + 多轮视口切换，单位门的 5s 档在这里必然假红。
    testTimeout: 60000,
    hookTimeout: 180000,
  },
})
