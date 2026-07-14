// ===== Playwright 测试脚本: 所有页面检查 =====
// 使用方式: npx playwright test playwright/check-pages.ts --headed

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:8522';
const PAGES = [
  { name: 'index', url: '/web/', title: '聊天页面' },
  { name: 'manage', url: '/web/manage.html', title: '知识库管理页面' },
  { name: 'feedback', url: '/web/feed_back.html', title: '问题反馈页面' },
  { name: 'use_function', url: '/web/use_function.html', title: '使用指南页面' },
];

// ===== 通用检查函数 =====
async function checkPage(title: string, page: any, name: string) {
  const results: { check: string; status: 'PASS' | 'FAIL' | 'WARN'; detail: string }[] = [];
  
  try {
    await page.goto(BASE_URL + title.url, { waitUntil: 'networkidle', timeout: 15000 });
    results.push({ check: '页面加载', status: 'PASS', detail: '成功加载' });
  } catch (e: any) {
    results.push({ check: '页面加载', status: 'FAIL', detail: e.message });
    return { name: title.name, results };
  }

  // 1. 检查标题
  try {
    const pageTitle = await page.title();
    results.push({ check: '页面标题', status: 'PASS', detail: `标题: ${pageTitle}` });
  } catch (e: any) {
    results.push({ check: '页面标题', status: 'FAIL', detail: e.message });
  }

  // 2. 检查 404/错误状态
  try {
    const resp = await page.goto(BASE_URL + title.url, { waitUntil: 'domcontentloaded' });
    const status = resp?.status();
    if (status && status < 400) {
      results.push({ check: 'HTTP 状态', status: 'PASS', detail: `HTTP ${status}` });
    } else {
      results.push({ check: 'HTTP 状态', status: 'FAIL', detail: `HTTP ${status}` });
    }
  } catch (e: any) {
    results.push({ check: 'HTTP 状态', status: 'FAIL', detail: e.message });
  }

  // 3. 检查侧边栏渲染
  try {
    const sidebar = await page.$('#side_left');
    if (sidebar) {
      const sidebarHTML = await sidebar.innerHTML();
      const hasMenu = sidebarHTML.includes('知识库管理') && sidebarHTML.includes('使用指南') && sidebarHTML.includes('智能聊天') && sidebarHTML.includes('问题反馈');
      results.push({ check: '侧边栏', status: hasMenu ? 'PASS' : 'WARN', detail: hasMenu ? '菜单项完整' : '菜单项不完整' });
    } else {
      results.push({ check: '侧边栏', status: 'FAIL', detail: '侧边栏未渲染' });
    }
  } catch (e: any) {
    results.push({ check: '侧边栏', status: 'FAIL', detail: e.message });
  }

  // 4. 检查 CSS 加载
  try {
    const linkTags = await page.$$eval('link[rel="stylesheet"]', links => links.map(l => l.href));
    if (linkTags.length > 0) {
      results.push({ check: 'CSS 加载', status: 'PASS', detail: `加载了 ${linkTags.length} 个样式表` });
    } else {
      results.push({ check: 'CSS 加载', status: 'WARN', detail: '未找到 CSS 引用' });
    }
  } catch (e: any) {
    results.push({ check: 'CSS 加载', status: 'FAIL', detail: e.message });
  }

  // 5. 检查 JS 脚本加载
  try {
    const scripts = await page.$$eval('script[src]', scripts => scripts.map(s => s.src));
    results.push({ check: 'JS 脚本', status: scripts.length > 0 ? 'PASS' : 'WARN', detail: `加载了 ${scripts.length} 个脚本` });
  } catch (e: any) {
    results.push({ check: 'JS 脚本', status: 'FAIL', detail: e.message });
  }

  // 6. 检查浏览器控制台错误
  const consoleErrors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });
  // 给页面时间触发错误
  await page.waitForTimeout(2000);
  if (consoleErrors.length > 0) {
    results.push({ check: '控制台错误', status: 'WARN', detail: `${consoleErrors.length} 个错误: ${consoleErrors.join('; ')}` });
  } else {
    results.push({ check: '控制台错误', status: 'PASS', detail: '无控制台错误' });
  }

  // 7. 检查页面可见内容
  try {
    const bodyText = await page.textContent('body');
    if (bodyText && bodyText.length > 50) {
      results.push({ check: '页面内容', status: 'PASS', detail: `页面有内容 (${bodyText.length} 字符)` });
    } else {
      results.push({ check: '页面内容', status: 'WARN', detail: '页面内容很少或为空' });
    }
  } catch (e: any) {
    results.push({ check: '页面内容', status: 'FAIL', detail: e.message });
  }

  // 8. 检查图标加载
  try {
    const favicon = await page.$('link[rel="icon"]');
    if (favicon) {
      const href = await favicon.getAttribute('href');
      results.push({ check: 'Favicon', status: 'PASS', detail: `Favicon: ${href}` });
    } else {
      results.push({ check: 'Favicon', status: 'WARN', detail: '未设置 favicon' });
    }
  } catch (e: any) {
    results.push({ check: 'Favicon', status: 'FAIL', detail: e.message });
  }

  // 9. 检查是否有未捕获的 JavaScript 错误
  const pageErrors: string[] = [];
  page.on('pageerror', err => {
    pageErrors.push(err.message);
  });
  await page.waitForTimeout(1000);
  if (pageErrors.length > 0) {
    results.push({ check: '页面 JS 错误', status: 'WARN', detail: `${pageErrors.length} 个页面错误: ${pageErrors.join('; ')}` });
  } else {
    results.push({ check: '页面 JS 错误', status: 'PASS', detail: '无页面 JS 错误' });
  }

  // 10. 检查响应式适配 (viewport)
  try {
    const width = page.viewportSize()?.width || 0;
    const height = page.viewportSize()?.height || 0;
    results.push({ check: 'Viewport', status: 'PASS', detail: `${width}x${height}` });
  } catch (e: any) {
    results.push({ check: 'Viewport', status: 'FAIL', detail: e.message });
  }

  return { name: title.name, results };
}

// ===== 各页面专项测试 =====

test.describe('CUITCCA 页面检查 - 多Agent并发测试', () => {
  for (const pageConfig of PAGES) {
    test(`检查页面: ${pageConfig.title} (${pageConfig.name})`, async ({ browser }) => {
      const context = await browser.newContext({
        viewport: { width: 1280, height: 720 },
        ignoreHTTPSErrors: true,
      });
      const page = await context.newPage();
      
      const result = await checkPage(pageConfig, page, pageConfig.name);
      
      // 输出结果
      console.log(`\n=== ${pageConfig.title} 检查报告 ===`);
      for (const r of result.results) {
        const icon = r.status === 'PASS' ? '✅' : r.status === 'FAIL' ? '❌' : '⚠️';
        console.log(`  ${icon} ${r.check}: ${r.detail}`);
      }
      
      // 统计
      const passCount = result.results.filter(r => r.status === 'PASS').length;
      const failCount = result.results.filter(r => r.status === 'FAIL').length;
      const warnCount = result.results.filter(r => r.status === 'WARN').length;
      console.log(`  总计: ✅${passCount} ❌${failCount} ⚠️${warnCount}`);
      
      // 截图
      await page.screenshot({ path: `/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/${pageConfig.name}.png` });
      
      await context.close();
      
      // 如果有失败项，标记测试失败
      if (failCount > 0) {
        expect(failCount).toBe(0);
      }
    });
  }
});
