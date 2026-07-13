import { test, expect } from '@playwright/test';

const FEEDBACK_URL = 'http://localhost:8522/web/feed_back.html';

test.describe('问题反馈页面 (feed_back.html)', () => {
  test('1. 页面加载 — HTTP 200 且无报错', async ({ page }) => {
    const response = await page.goto(FEEDBACK_URL);
    expect(response?.status()).toBe(200);
  });

  test('2. 页面标题是否为 "成信大校园助手 - 问题反馈"', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    await expect(page).toHaveTitle('成信大校园助手 - 问题反馈');
  });

  test('3. 侧边栏是否正确渲染', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    // sidebar.js 将 HTML 注入到 #side_left 中
    const sidebar = page.locator('#side_left');
    await expect(sidebar).toBeVisible();
    // 侧边栏应包含菜单文字
    await expect(sidebar.locator('.menu_font_row').first()).toBeVisible();
    // "问题反馈" 菜单项应该有 active 类（当前页高亮）
    const feedbackMenuItem = sidebar.locator('a[href="./feed_back.html"] > .menu_item_row.active');
    await expect(feedbackMenuItem).toBeVisible();
  });

  test('4. 邮箱输入框 #email 存在且 type=email', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    const emailInput = page.locator('#email');
    await expect(emailInput).toBeVisible();
    const inputType = await emailInput.getAttribute('type');
    expect(inputType).toBe('email');
    // 检查 placeholder
    const placeholder = await emailInput.getAttribute('placeholder');
    expect(placeholder).toBe('请输入您的邮箱地址...');
  });

  test('5. 反馈文本框 #feedback 存在', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    const textarea = page.locator('#feedback');
    await expect(textarea).toBeVisible();
    // 检查 placeholder
    const placeholder = await textarea.getAttribute('placeholder');
    expect(placeholder).toBe('请输入您的宝贵意见...');
  });

  test('6. 提交按钮 #feedbackButton 存在', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    const submitBtn = page.locator('#feedbackButton');
    await expect(submitBtn).toBeVisible();
    const buttonText = await submitBtn.textContent();
    expect(buttonText?.trim()).toBe('提交反馈');
  });

  test('7. CSS (style.css) 是否正确加载', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    // 检查 style.css 链接是否存在
    const cssLink = page.locator('link[href="./style.css"]');
    await expect(cssLink).toBeTruthy();
    // 验证关键样式是否生效：glass_card 的 backdrop-filter 或类似样式
    const card = page.locator('.glass_card');
    await expect(card).toBeVisible();
    const bgColor = await card.evaluate(el => window.getComputedStyle(el).backgroundColor);
    expect(bgColor).not.toBe('');
  });

  test('8. feedback.js 是否正确加载', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    const script = page.locator('script[src="./feedback.js"]');
    await expect(script).toBeTruthy();
    // 验证 submitFeedback 函数已定义
    const fnExists = await page.evaluate(() => typeof submitFeedback === 'function');
    expect(fnExists).toBe(true);
  });

  test('9. 是否有控制台错误', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    await page.goto(FEEDBACK_URL);
    // 等 JS 执行完毕
    await page.waitForTimeout(1000);
    expect(consoleErrors).toHaveLength(0);
  });

  test('10. 是否有未捕获的 JS 错误', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', err => {
      pageErrors.push(err.message);
    });
    await page.goto(FEEDBACK_URL);
    await page.waitForTimeout(1000);
    expect(pageErrors).toHaveLength(0);
  });

  test('11. Toast 容器 #toast-container 存在', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    const toastContainer = page.locator('#toast-container');
    // toast-container 初始隐藏(display:none)，检查是否已挂载
    await expect(toastContainer).toBeAttached();
    const classes = await toastContainer.getAttribute('class');
    expect(classes).toContain('feedback-top');
  });

  test('12. 表单验证 — 提交空表单应有错误提示', async ({ page }) => {
    await page.goto(FEEDBACK_URL);

    // 监听 toast 出现
    const toastPromise = page.waitForSelector('.toast.toast-error', { timeout: 5000 }).catch(() => null);

    // 点击提交按钮（空表单）
    await page.locator('#feedbackButton').click();

    // 应出现错误 toast
    const toast = await toastPromise;
    expect(toast).not.toBeNull();
    const toastText = await toast!.textContent();
    // 预期: 邮箱无效 或 反馈内容为空 的提示
    expect(toastText).toMatch(/邮箱|反馈/);
  });

  test('13. 截图保存', async ({ page }) => {
    await page.goto(FEEDBACK_URL);
    await page.waitForTimeout(500); // 确保所有动画/加载完成
    await page.screenshot({
      path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/feedback.png',
      fullPage: false,
    });
  });
});
