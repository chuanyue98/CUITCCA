// ===== Playwright 测试脚本: 知识库管理页面 (manage.html) =====
// 测试地址: http://localhost:8000/web/manage.html

import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';

const BASE_URL = 'http://localhost:8000';
const MANAGE_URL = `${BASE_URL}/web/manage.html`;

// 确保截图目录存在
const screenshotDir = '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots';
mkdirSync(screenshotDir, { recursive: true });

interface CheckResult {
  check: string;
  status: 'PASS' | 'FAIL' | 'WARN';
  detail: string;
}

test.describe('CUITCCA 知识库管理页面 (manage.html)', () => {
  test('完整功能检查', async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();

    const results: CheckResult[] = [];
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    // 监听控制台错误
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // 监听页面 JS 错误
    page.on('pageerror', err => {
      pageErrors.push(err.message);
    });

    // 1. 页面加载 (HTTP 200)
    try {
      const response = await page.goto(MANAGE_URL, { waitUntil: 'networkidle', timeout: 15000 });
      const status = response?.status();
      if (status === 200) {
        results.push({ check: '页面加载 (HTTP 200)', status: 'PASS', detail: `HTTP ${status}` });
      } else {
        results.push({ check: '页面加载 (HTTP 200)', status: 'FAIL', detail: `HTTP ${status}` });
      }
    } catch (e: any) {
      results.push({ check: '页面加载 (HTTP 200)', status: 'FAIL', detail: e.message });
    }

    // 2. 页面标题
    try {
      const title = await page.title();
      if (title === '成信大校园助手 - 知识库管理') {
        results.push({ check: '页面标题', status: 'PASS', detail: `标题: "${title}"` });
      } else {
        results.push({ check: '页面标题', status: 'FAIL', detail: `期望 "成信大校园助手 - 知识库管理", 实际: "${title}"` });
      }
    } catch (e: any) {
      results.push({ check: '页面标题', status: 'FAIL', detail: e.message });
    }

    // 3. 侧边栏渲染 (#side_left)
    try {
      const sidebar = await page.$('#side_left');
      if (sidebar) {
        const sidebarHTML = await sidebar.innerHTML();
        const hasMenu = sidebarHTML.includes('知识库管理') && sidebarHTML.includes('使用指南') && sidebarHTML.includes('智能聊天') && sidebarHTML.includes('问题反馈');
        results.push({ check: '侧边栏渲染 (#side_left)', status: hasMenu ? 'PASS' : 'WARN', detail: hasMenu ? '菜单项完整 (知识库管理/使用指南/智能聊天/问题反馈)' : '菜单项不完整' });
      } else {
        results.push({ check: '侧边栏渲染 (#side_left)', status: 'FAIL', detail: '侧边栏未渲染' });
      }
    } catch (e: any) {
      results.push({ check: '侧边栏渲染 (#side_left)', status: 'FAIL', detail: e.message });
    }

    // 4. 索引选择下拉框 (#index-select)
    try {
      const indexSelect = await page.$('#index-select');
      if (indexSelect) {
        const options = await indexSelect.$$('option');
        results.push({ check: '索引选择下拉框 (#index-select)', status: 'PASS', detail: `存在, 包含 ${options.length} 个选项` });
      } else {
        results.push({ check: '索引选择下拉框 (#index-select)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: '索引选择下拉框 (#index-select)', status: 'FAIL', detail: e.message });
    }

    // 5. 文件上传区域 (#drag-zone)
    try {
      const dragZone = await page.$('#drag-zone');
      if (dragZone) {
        results.push({ check: '文件上传区域 (#drag-zone)', status: 'PASS', detail: '存在' });
      } else {
        results.push({ check: '文件上传区域 (#drag-zone)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: '文件上传区域 (#drag-zone)', status: 'FAIL', detail: e.message });
    }

    // 6. 三个 Tab 按钮 (文件上传/文本录入/QA生成导入)
    try {
      const tabBtns = await page.$$('.tab_btn');
      if (tabBtns.length === 3) {
        const tabTexts = await Promise.all(tabBtns.map(btn => btn.textContent()));
        const expectedTabs = ['文件上传', '文本录入', 'QA生成导入'];
        const hasAllTabs = expectedTabs.every((t, i) => tabTexts[i]?.includes(t));
        results.push({ check: '三个 Tab 按钮', status: hasAllTabs ? 'PASS' : 'WARN', detail: `共 ${tabBtns.length} 个, 内容: ${tabTexts.join(' / ')}` });
      } else {
        results.push({ check: '三个 Tab 按钮', status: 'FAIL', detail: `期望 3 个, 实际 ${tabBtns.length} 个` });
      }
    } catch (e: any) {
      results.push({ check: '三个 Tab 按钮', status: 'FAIL', detail: e.message });
    }

    // 7. 节点列表视口 (#node-list-viewport)
    try {
      const nodeViewport = await page.$('#node-list-viewport');
      if (nodeViewport) {
        const text = await nodeViewport.textContent();
        results.push({ check: '节点列表视口 (#node-list-viewport)', status: 'PASS', detail: `存在, 内容: "${text}"` });
      } else {
        results.push({ check: '节点列表视口 (#node-list-viewport)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: '节点列表视口 (#node-list-viewport)', status: 'FAIL', detail: e.message });
    }

    // 8. 分页组件 (#pagination-bar)
    try {
      const paginationBar = await page.$('#pagination-bar');
      if (paginationBar) {
        const text = await paginationBar.textContent();
        results.push({ check: '分页组件 (#pagination-bar)', status: 'PASS', detail: `存在, 内容: "${text}"` });
      } else {
        results.push({ check: '分页组件 (#pagination-bar)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: '分页组件 (#pagination-bar)', status: 'FAIL', detail: e.message });
    }

    // 9. CSS 是否正确加载
    try {
      const linkTags = await page.$$eval('link[rel="stylesheet"]', links => links.map(l => l.href));
      if (linkTags.length > 0) {
        results.push({ check: 'CSS 加载', status: 'PASS', detail: `加载了 ${linkTags.length} 个样式表: ${linkTags.join(', ')}` });
      } else {
        results.push({ check: 'CSS 加载', status: 'WARN', detail: '未找到 CSS 引用' });
      }
    } catch (e: any) {
      results.push({ check: 'CSS 加载', status: 'FAIL', detail: e.message });
    }

    // 10. manage.js 是否正确加载
    try {
      const scripts = await page.$$eval('script[src]', scripts => scripts.map(s => s.src));
      const hasManageJs = scripts.some(s => s.includes('manage.js'));
      const hasSidebarJs = scripts.some(s => s.includes('sidebar.js'));
      const jsStatus: CheckResult = {
        check: 'JS 脚本加载 (manage.js + sidebar.js)',
        status: (hasManageJs && hasSidebarJs) ? 'PASS' : 'FAIL',
        detail: `加载了 ${scripts.length} 个脚本: ${scripts.join(', ')}`
      };
      if (!hasManageJs) jsStatus.detail += ' [缺少 manage.js]';
      if (!hasSidebarJs) jsStatus.detail += ' [缺少 sidebar.js]';
      results.push(jsStatus);
    } catch (e: any) {
      results.push({ check: 'JS 脚本加载 (manage.js + sidebar.js)', status: 'FAIL', detail: e.message });
    }

    // 11. 控制台错误
    await page.waitForTimeout(2000);
    if (consoleErrors.length > 0) {
      results.push({ check: '控制台错误', status: 'WARN', detail: `${consoleErrors.length} 个错误: ${consoleErrors.slice(0, 5).join('; ')}` });
    } else {
      results.push({ check: '控制台错误', status: 'PASS', detail: '无控制台错误' });
    }

    // 12. 未捕获的 JS 错误
    await page.waitForTimeout(1000);
    if (pageErrors.length > 0) {
      results.push({ check: '未捕获的 JS 错误', status: 'WARN', detail: `${pageErrors.length} 个错误: ${pageErrors.slice(0, 5).join('; ')}` });
    } else {
      results.push({ check: '未捕获的 JS 错误', status: 'PASS', detail: '无未捕获的 JS 错误' });
    }

    // 13. 加载遮罩 (#loading-overlay)
    try {
      const loadingOverlay = await page.$('#loading-overlay');
      if (loadingOverlay) {
        const visibility = await loadingOverlay.isVisible();
        results.push({ check: '加载遮罩 (#loading-overlay)', status: 'PASS', detail: `存在${visibility ? ' (当前可见)' : ' (当前隐藏)'}` });
      } else {
        results.push({ check: '加载遮罩 (#loading-overlay)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: '加载遮罩 (#loading-overlay)', status: 'FAIL', detail: e.message });
    }

    // 14. Toast 容器 (#toast-container)
    try {
      const toastContainer = await page.$('#toast-container');
      if (toastContainer) {
        results.push({ check: 'Toast 容器 (#toast-container)', status: 'PASS', detail: '存在' });
      } else {
        results.push({ check: 'Toast 容器 (#toast-container)', status: 'FAIL', detail: '元素不存在' });
      }
    } catch (e: any) {
      results.push({ check: 'Toast 容器 (#toast-container)', status: 'FAIL', detail: e.message });
    }

    // 15. 截图
    try {
      const screenshotPath = join(screenshotDir, 'manage.png');
      await page.screenshot({ path: screenshotPath, fullPage: true });
      results.push({ check: '截图', status: 'PASS', detail: screenshotPath });
    } catch (e: any) {
      results.push({ check: '截图', status: 'FAIL', detail: e.message });
    }

    // 输出详细报告
    console.log('\n' + '='.repeat(60));
    console.log('CUITCCA 知识库管理页面 (manage.html) 测试报告');
    console.log('='.repeat(60));
    console.log(`测试地址: ${MANAGE_URL}\n`);

    let passCount = 0, failCount = 0, warnCount = 0;
    for (const r of results) {
      const icon = r.status === 'PASS' ? '✅' : r.status === 'FAIL' ? '❌' : '⚠️';
      console.log(`  ${icon} ${r.check}`);
      console.log(`     → ${r.detail}`);
      if (r.status === 'PASS') passCount++;
      else if (r.status === 'FAIL') failCount++;
      else warnCount++;
    }

    console.log('\n' + '-'.repeat(60));
    console.log(`总计: ✅ ${passCount}  PASS  |  ❌ ${failCount}  FAIL  |  ⚠️ ${warnCount}  WARN`);
    console.log(`截图: ${join(screenshotDir, 'manage.png')}`);
    console.log('='.repeat(60));

    // 如果有 FAIL 项，则标记测试失败
    if (failCount > 0) {
      expect(failCount).toBe(0);
    }

    await context.close();
  });
});
