import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './',
  timeout: 60000,
  use: {
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    baseURL: 'http://localhost:8522',
  },
  reporter: [['list'], ['json', { outputFile: 'test-results.json' }]],
  projects: [
    { name: 'default', use: { viewport: { width: 1280, height: 720 } } },
  ],
});
