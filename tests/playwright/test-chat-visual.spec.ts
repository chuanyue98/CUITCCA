import { test } from '@playwright/test';

test('聊天页面最终截图', async ({ page }) => {
  await page.goto('http://localhost:8522/web/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/chat-final.png' });
});
