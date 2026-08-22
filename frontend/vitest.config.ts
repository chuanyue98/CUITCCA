import { defineConfig } from 'vitest/config';

// 与 vite.config.ts 分离，避免影响生产构建。
// 测试只覆盖纯逻辑（utils/），页面脚本（chat/manage/sidebar/feed_back）因
// 顶层 DOM 副作用 + 非导出 + 依赖 marked/DOMPurify 全局变量而难以单测，
// 不纳入覆盖率统计，详见交付报告。
export default defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['tests/**/*.test.ts'],
    exclude: ['vendor/**', '**/*.d.ts', '**/node_modules/**', '**/dist/**'],
    // node>=22.4 的实验性 localStorage getter 会让 happy-dom 的实现装不上
    // 全局（见 tests/setup.storage.ts），这里统一补齐。
    setupFiles: ['tests/setup.storage.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/utils/**/*.ts'],
      exclude: ['vendor/**', '**/*.d.ts', '**/node_modules/**', 'tests/**'],
    },
  },
});