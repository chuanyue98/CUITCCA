import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = 'http://localhost:8000';

test.describe('CUITCCA 聊天页面 (index.html) 检查', () => {
  test('聊天页面综合检查', async ({ browser }) => {
    const results: { check: string; status: 'PASS' | 'FAIL' | 'WARN'; detail: string }[] = [];
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();

    // 收集控制台错误
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', (err) => {
      pageErrors.push(err.message);
    });

    // ---- 1. 页面加载 (HTTP 200) ----
    try {
      const resp = await page.goto(BASE_URL + '/web/', { waitUntil: 'networkidle', timeout: 15000 });
      const status = resp?.status();
      if (resp && status && status === 200) {
        results.push({ check: '页面加载', status: 'PASS', detail: `HTTP ${status}` });
      } else {
        results.push({ check: '页面加载', status: 'FAIL', detail: `HTTP ${status}` });
      }
    } catch (e: any) {
      results.push({ check: '页面加载', status: 'FAIL', detail: e.message });
    }

    // ---- 2. 页面标题 ----
    try {
      const title = await page.title();
      if (title === '成信大校园助手') {
        results.push({ check: '页面标题', status: 'PASS', detail: `标题: "${title}"` });
      } else {
        results.push({ check: '页面标题', status: 'FAIL', detail: `期望 "成信大校园助手", 实际 "${title}"` });
      }
    } catch (e: any) {
      results.push({ check: '页面标题', status: 'FAIL', detail: e.message });
    }

    // ---- 3. 侧边栏渲染 (4 个菜单项) ----
    try {
      await page.waitForSelector('#side_left', { timeout: 5000 });
      const sidebarHTML = await page.$eval('#side_left', (el) => el.innerHTML);
      const menuItems = ['知识库管理', '使用指南', '智能聊天', '问题反馈'];
      const found = menuItems.map((item) => sidebarHTML.includes(item));
      const foundCount = found.filter(Boolean).length;
      if (foundCount === 4) {
        results.push({ check: '侧边栏菜单项', status: 'PASS', detail: `4 个菜单项全部渲染: ${menuItems.join(', ')}` });
      } else {
        const missing = menuItems.filter((_, i) => !found[i]);
        results.push({ check: '侧边栏菜单项', status: 'FAIL', detail: `只找到 ${foundCount}/4 项, 缺失: ${missing.join(', ')}` });
      }
    } catch (e: any) {
      results.push({ check: '侧边栏菜单项', status: 'FAIL', detail: `侧边栏未渲染: ${e.message}` });
    }

    // ---- 4. 聊天框 (textarea#input) ----
    try {
      await page.waitForSelector('textarea#input', { timeout: 5000 });
      const placeholder = await page.$eval('textarea#input', (el) => el.getAttribute('placeholder') || '');
      results.push({ check: '聊天框 (textarea#input)', status: 'PASS', detail: `存在, placeholder="${placeholder}"` });
    } catch (e: any) {
      results.push({ check: '聊天框 (textarea#input)', status: 'FAIL', detail: `未找到: ${e.message}` });
    }

    // ---- 5. 发送按钮 (button#submit) ----
    try {
      await page.waitForSelector('button#submit', { timeout: 5000 });
      const text = await page.$eval('button#submit', (el) => el.textContent || '');
      results.push({ check: '发送按钮 (button#submit)', status: 'PASS', detail: `存在, 文本="${text.trim()}"` });
    } catch (e: any) {
      results.push({ check: '发送按钮 (button#submit)', status: 'FAIL', detail: `未找到: ${e.message}` });
    }

    // ---- 6. CSS 加载 ----
    try {
      const linkTags = await page.$$eval('link[rel="stylesheet"]', (links) =>
        links.map((l) => ({ href: l.href, sheet: l.sheet ? 'ok' : 'missing' }))
      );
      const loaded = linkTags.filter((l) => l.sheet === 'ok');
      if (loaded.length > 0) {
        results.push({
          check: 'CSS 加载',
          status: 'PASS',
          detail: `成功加载 ${loaded.length} 个样式表: ${linkTags.map((l) => path.basename(l.href)).join(', ')}`,
        });
      } else {
        results.push({ check: 'CSS 加载', status: 'FAIL', detail: `引用了 ${linkTags.length} 个 CSS 但均未成功加载` });
      }
    } catch (e: any) {
      results.push({ check: 'CSS 加载', status: 'FAIL', detail: e.message });
    }

    // ---- 7. JS 脚本加载 ----
    try {
      const scripts = await page.$$eval('script[src]', (scripts) => scripts.map((s) => s.src));
      if (scripts.length >= 2) {
        results.push({
          check: 'JS 脚本加载',
          status: 'PASS',
          detail: `加载了 ${scripts.length} 个脚本: ${scripts.map((s) => path.basename(s)).join(', ')}`,
        });
      } else {
        results.push({ check: 'JS 脚本加载', status: 'WARN', detail: `只加载了 ${scripts.length} 个脚本, 期望至少 2 个` });
      }
    } catch (e: any) {
      results.push({ check: 'JS 脚本加载', status: 'FAIL', detail: e.message });
    }

    // ---- 8. 页面内容包含欢迎消息 ----
    try {
      await page.waitForSelector('.content_bot', { timeout: 5000 });
      const content = await page.$eval('.content_bot', (el) => el.textContent || '');
      if (content.includes('成信大校园助手') || content.includes('你好')) {
        results.push({ check: '欢迎消息', status: 'PASS', detail: `"${content.trim().slice(0, 60)}..."` });
      } else {
        results.push({ check: '欢迎消息', status: 'FAIL', detail: `未找到欢迎消息, 内容: "${content.slice(0, 60)}"` });
      }
    } catch (e: any) {
      results.push({ check: '欢迎消息', status: 'FAIL', detail: `未找到 .content_bot: ${e.message}` });
    }

    // 等待页面稳定后收集错误
    await page.waitForTimeout(2000);

    // ---- 9. 控制台错误 ----
    if (consoleErrors.length > 0) {
      results.push({ check: '控制台错误', status: 'WARN', detail: `${consoleErrors.length} 个错误: ${consoleErrors.join('; ')}` });
    } else {
      results.push({ check: '控制台错误', status: 'PASS', detail: '无控制台错误' });
    }

    // ---- 10. 未捕获的 JS 错误 ----
    if (pageErrors.length > 0) {
      results.push({ check: '未捕获 JS 错误', status: 'WARN', detail: `${pageErrors.length} 个错误: ${pageErrors.join('; ')}` });
    } else {
      results.push({ check: '未捕获 JS 错误', status: 'PASS', detail: '无未捕获 JS 错误' });
    }

    // ---- 截图 ----
    const screenshotDir = '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots';
    await page.screenshot({ path: path.join(screenshotDir, 'index.png'), fullPage: false });

    // ---- 输出报告 ----
    console.log('\n\n=======================================================');
    console.log('  CUITCCA 聊天页面 (index.html) 测试报告');
    console.log('=======================================================');

    for (const r of results) {
      const icon = r.status === 'PASS' ? '✅ PASS' : r.status === 'FAIL' ? '❌ FAIL' : '⚠️  WARN';
      console.log(`  ${icon}  ${r.check}`);
      console.log(`         ${r.detail}`);
    }

    console.log('-------------------------------------------------------');
    const passCount = results.filter((r) => r.status === 'PASS').length;
    const failCount = results.filter((r) => r.status === 'FAIL').length;
    const warnCount = results.filter((r) => r.status === 'WARN').length;
    console.log(`  总计:  ✅ ${passCount}   ❌ ${failCount}   ⚠️  ${warnCount}`);
    console.log('-------------------------------------------------------');
    console.log(`  截图: ${path.join(screenshotDir, 'index.png')}`);
    console.log('=======================================================\n');

    await context.close();

    // 如果有失败项，标记测试失败
    expect(failCount).toBe(0);
  });
});
