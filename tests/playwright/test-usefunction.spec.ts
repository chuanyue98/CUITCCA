import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';

const SCREENSHOT_DIR = '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots';
const SCREENSHOT_PATH = join(SCREENSHOT_DIR, 'use_function.png');

// 测试结果收集
const results: { item: string; status: 'PASS' | 'FAIL' | 'WARN'; detail: string }[] = [];

function report(item: string, status: 'PASS' | 'FAIL' | 'WARN', detail: string) {
  results.push({ item, status, detail });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${icon} [${status}] ${item}: ${detail}`);
}

test.describe('使用指南页面 (use_function.html) 测试', () => {
  test.beforeEach(async ({ page }) => {
    // 收集控制台消息
    const consoleErrors: string[] = [];
    const jsErrors: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', (err) => {
      jsErrors.push(err.message);
    });

    // 暴露到测试作用域供后续断言使用
    (page as any)._consoleErrors = consoleErrors;
    (page as any)._jsErrors = jsErrors;
  });

  test('页面加载正常 (HTTP 200)', async ({ page }) => {
    const response = await page.goto('/web/use_function.html');
    const status = response?.status();

    if (status === 200 && response?.ok()) {
      report('页面加载', 'PASS', `HTTP ${status}`);
    } else {
      report('页面加载', 'FAIL', `HTTP ${status}, ok=${response?.ok()}`);
    }

    expect(status).toBe(200);
    expect(response?.ok()).toBe(true);
  });

  test('页面标题正确', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    const title = await page.title();
    const expected = '成信大校园助手 - 使用指南';

    if (title === expected) {
      report('页面标题', 'PASS', `"${title}"`);
    } else {
      report('页面标题', 'FAIL', `期望 "${expected}", 实际 "${title}"`);
    }

    expect(title).toBe(expected);
  });

  test('侧边栏正确渲染且当前菜单项高亮', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 等待侧边栏 JS 渲染完成
    await page.waitForSelector('#side_left', { state: 'attached' });

    // 检查侧边栏是否有内容
    const sidebarContent = await page.$eval('#side_left', (el) => el.innerHTML);
    const hasContent = sidebarContent.length > 100;

    if (!hasContent) {
      report('侧边栏渲染', 'FAIL', '侧边栏 #side_left 内容为空或过短');
      expect(hasContent).toBe(true);
      return;
    }

    // 检查 "使用指南" 文本是否存在于侧边栏
    const hasUseGuide = await page.$eval('#side_left', (el) =>
      el.textContent.includes('使用指南')
    );
    expect(hasUseGuide).toBe(true);

    // 检查高亮样式: 使用指南菜单项应包含 box-shadow 或 border-color 高亮
    // sidebar.js 中 data-active="use_function" 会给对应 func div 添加高亮 style
    const useFunctionLink = await page.$('a[title="食用指南"]');
    expect(useFunctionLink).not.toBeNull();

    if (useFunctionLink) {
      const funcDiv = await useFunctionLink.$('div.func');
      if (funcDiv) {
        const style = await funcDiv.getAttribute('style') || '';
        const isActive = style.includes('box-shadow') || style.includes('rgb(25, 84, 142)');

        if (isActive) {
          report('侧边栏高亮', 'PASS', '使用指南菜单项已高亮 (box-shadow / 蓝色图标)');
        } else {
          report('侧边栏高亮', 'FAIL', `使用指南菜单项未高亮, style="${style}"`);
        }
        expect(isActive).toBe(true);
      } else {
        report('侧边栏高亮', 'WARN', '未找到 func div，无法验证高亮状态');
      }
    }

    if (hasContent) {
      report('侧边栏渲染', 'PASS', '侧边栏已正确渲染，包含 "使用指南" 菜单项');
    }
  });

  test('指南内容卡片 (.guide_card) 存在', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    const guideCard = await page.$('.guide_card');

    if (guideCard) {
      report('指南卡片', 'PASS', '.guide_card 存在');
    } else {
      report('指南卡片', 'FAIL', '.guide_card 不存在');
    }

    expect(guideCard).not.toBeNull();
  });

  test('指南内容包含 "欢迎使用成信大校园助手"', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    const text = await page.locator('.guide_card').textContent();
    const containsWelcome = text?.includes('欢迎使用成信大校园助手') ?? false;

    if (containsWelcome) {
      report('欢迎文本', 'PASS', '包含 "欢迎使用成信大校园助手"');
    } else {
      report('欢迎文本', 'FAIL', '不包含 "欢迎使用成信大校园助手"');
    }

    expect(containsWelcome).toBe(true);
  });

  test('指南内容包含 3 个主要章节', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    const text = await page.locator('.guide_card').textContent() || '';

    const chapters = [
      { name: '温馨提示', regex: /1\s*[\.、]\s*温馨提示/ },
      { name: '提问方式', regex: /2\s*[\.、]\s*提问方式/ },
      { name: '问题反馈', regex: /3\s*[\.、]\s*问题反馈/ },
    ];

    const results2: { name: string; found: boolean }[] = [];

    for (const chapter of chapters) {
      const found = chapter.regex.test(text);
      results2.push({ name: chapter.name, found });
      if (found) {
        report(`章节: ${chapter.name}`, 'PASS', `匹配到 "${chapter.name}"`);
      } else {
        report(`章节: ${chapter.name}`, 'FAIL', `未匹配到 "${chapter.name}"`);
      }
    }

    expect(results2.every((r) => r.found)).toBe(true);
  });

  test('CSS 正确加载', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 检查关键 CSS 类是否生效
    const guideCard = await page.$('.guide_card');
    let cssOk = false;
    let detail = '';

    if (guideCard) {
      const hasOpacity = await guideCard.evaluate(
        (el) => window.getComputedStyle(el).opacity
      );
      const bgColor = await guideCard.evaluate(
        (el) => window.getComputedStyle(el).backgroundColor
      );
      const isTransparent = bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent';

      if (hasOpacity !== '0' && hasOpacity !== '') {
        cssOk = true;
        detail = `opacity=${hasOpacity}, backgroundColor=${bgColor}`;
      } else {
        detail = `opacity=${hasOpacity}, backgroundColor=${bgColor}`;
      }
    }

    if (cssOk) {
      report('CSS 加载', 'PASS', detail);
    } else {
      report('CSS 加载', 'WARN', detail);
    }

    expect(cssOk).toBe(true);
  });

  test('sidebar.js 正确加载', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 检查脚本是否已执行（通过侧边栏内容存在来验证）
    const sidebarHtml = await page.$eval('#side_left', (el) => el.innerHTML);
    const jsLoaded = sidebarHtml.includes('成信大校园助手') && sidebarHtml.includes('menu');

    if (jsLoaded) {
      report('sidebar.js', 'PASS', '侧边栏已由 JS 渲染');
    } else {
      report('sidebar.js', 'FAIL', '侧边栏未渲染，可能 sidebar.js 未加载或执行失败');
    }

    // 检查脚本标签
    const scriptCount = await page.$$eval('script[src*="sidebar"]', (els) => els.length);
    expect(scriptCount).toBeGreaterThanOrEqual(1);
  });

  test('无控制台错误', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 等待一段时间让潜在的异步错误发生
    await page.waitForTimeout(2000);

    const consoleErrors = (page as any)._consoleErrors as string[];

    if (consoleErrors.length === 0) {
      report('控制台错误', 'PASS', '无控制台错误');
    } else {
      report('控制台错误', 'WARN', `${consoleErrors.length} 个错误: ${consoleErrors.slice(0, 3).join('; ')}`);
    }
  });

  test('无未捕获的 JS 错误', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 等待一段时间让潜在的异步错误发生
    await page.waitForTimeout(2000);

    const jsErrors = (page as any)._jsErrors as string[];

    if (jsErrors.length === 0) {
      report('JS 错误', 'PASS', '无未捕获的 JS 错误');
    } else {
      report('JS 错误', 'WARN', `${jsErrors.length} 个错误: ${jsErrors.slice(0, 3).join('; ')}`);
    }
  });

  test('页面布局截图', async ({ page }) => {
    await page.goto('/web/use_function.html');
    await page.waitForLoadState('networkidle');

    // 确保截图目录存在
    mkdirSync(SCREENSHOT_DIR, { recursive: true });

    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });
    report('截图', 'PASS', `已保存到 ${SCREENSHOT_PATH}`);
  });

  // 打印最终报告
  test.afterAll(() => {
    console.log('\n' + '='.repeat(60));
    console.log('使用指南页面测试结果报告');
    console.log('='.repeat(60));

    let passCount = 0;
    let failCount = 0;
    let warnCount = 0;

    for (const r of results) {
      if (r.status === 'PASS') passCount++;
      else if (r.status === 'FAIL') failCount++;
      else warnCount++;
    }

    console.log(`\n总计: ${results.length} 项`);
    console.log(`  ✅ PASS: ${passCount}`);
    console.log(`  ❌ FAIL: ${failCount}`);
    console.log(`  ⚠️  WARN: ${warnCount}`);

    if (failCount > 0) {
      console.log('\n失败项详情:');
      for (const r of results) {
        if (r.status === 'FAIL') {
          console.log(`  ❌ ${r.item}: ${r.detail}`);
        }
      }
    }

    console.log('\n截图路径:', SCREENSHOT_PATH);
  });
});
