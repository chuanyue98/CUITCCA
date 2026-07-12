import { test, expect } from '@playwright/test';

test('使用指南页面 UI/UX 深度检查', async ({ page }) => {
  await page.goto('http://localhost:8000/web/use_function.html', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);

  console.log('\n=== 使用指南页面 UI/UX 深度检查 ===\n');
  const issues: string[] = [];

  // 1. #side_left
  const sidebarDisplay = await page.$eval('#side_left', el => getComputedStyle(el).display);
  const sidebarWidth = await page.$eval('#side_left', el => `${Math.round(el.getBoundingClientRect().width)}px`);
  console.log(`#side_left display=${sidebarDisplay} width=${sidebarWidth}`);
  if (sidebarDisplay !== 'block') issues.push('#side_left 不是 block');
  if (parseFloat(sidebarWidth) < 200 || parseFloat(sidebarWidth) > 400) issues.push(`#side_left 宽度异常: ${sidebarWidth}`);

  // 2. .guide_container layout
  const guideContainer = await page.$eval('.guide_container', el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { display: cs.display, padding: `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}`, width: r.width, height: r.height, overflow: cs.overflow };
  });
  console.log(`.guide_container display=${guideContainer.display} padding=${guideContainer.padding} size=${guideContainer.width}x${guideContainer.height} overflow=${guideContainer.overflow}`);
  if (guideContainer.display === 'none') issues.push('.guide_container 不可见');
  if (guideContainer.overflow === 'visible') issues.push('.guide_container overflow 应为 auto');

  // 3. .guide_card
  const guideCard = await page.$eval('.guide_card', el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { display: cs.display, width: r.width, padding: `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}` };
  });
  console.log(`.guide_card display=${guideCard.display} width=${guideCard.width} padding=${guideCard.padding}`);
  if (parseFloat(guideCard.width) > 1000 || parseFloat(guideCard.width) < 300) issues.push(`.guide_card 宽度异常: ${guideCard.width}`);

  // 4. Guide content readability
  const guideP = await page.$$eval('.guide_card p', els => els.map(el => ({
    text: el.textContent?.slice(0, 30),
    fontSize: getComputedStyle(el).fontSize,
    color: getComputedStyle(el).color,
    lineHeight: getComputedStyle(el).lineHeight
  })));
  console.log('段落样式:', JSON.stringify(guideP));
  for (const p of guideP) {
    if (parseFloat(p.fontSize) < 13) issues.push(`段落字体太小: ${p.fontSize}`);
    if (p.color === 'rgb(0, 0, 0)') issues.push(`段落颜色过深 (纯黑)`);
  }

  // 5. Guide content lists
  const guideLi = await page.$$eval('.guide_card li', els => els.map(el => ({
    text: el.textContent?.slice(0, 30),
    fontSize: getComputedStyle(el).fontSize,
    color: getComputedStyle(el).color,
    marginBottom: getComputedStyle(el).marginBottom
  })));
  console.log('列表样式:', JSON.stringify(guideLi));
  for (const li of guideLi) {
    if (parseFloat(li.fontSize) < 13) issues.push(`列表项字体太小: ${li.fontSize}`);
  }

  // 6. Check content structure (3 sections)
  const sections = await page.$$eval('.guide_card p', els => els.map(el => el.textContent?.trim()));
  const sectionTexts = sections.join(' ');
  const hasWelcome = sectionTexts.includes('欢迎使用成信大校园助手');
  const hasTip = sectionTexts.includes('温馨提示');
  const hasQuestion = sectionTexts.includes('提问方式');
  const hasFeedback = sectionTexts.includes('问题反馈');
  console.log(`章节检查: 欢迎=${hasWelcome} 温馨提示=${hasTip} 提问方式=${hasQuestion} 问题反馈=${hasFeedback}`);
  if (!hasWelcome) issues.push('缺少欢迎文本');
  if (!hasTip) issues.push('缺少温馨提示章节');
  if (!hasQuestion) issues.push('缺少提问方式章节');
  if (!hasFeedback) issues.push('缺少问题反馈章节');

  // 7. Check #side_left highlights use_function (use_function uses inline style on .func, not .menu_item_row.active)
  const activeMenu = await page.$eval('.menu_item_row.active', el => {
    const cs = getComputedStyle(el);
    return { text: el.textContent?.trim(), backgroundColor: cs.backgroundColor };
  }).catch(() => null);
  // For use_function, the highlight is on .func with inline box-shadow
  const funcMenu = await page.$$eval('.menu_mid1 .func, .menu_mid2 .func', els => {
    return els.map(el => {
      const cs = getComputedStyle(el);
      const boxShadow = cs.boxShadow;
      const borderColor = cs.borderColor;
      return { boxShadow, borderColor };
    });
  });
  const useFunctionActive = funcMenu.find(f => f.boxShadow.includes('25, 84, 142'));
  console.log('活跃菜单项:', activeMenu ? activeMenu.text : '无', '(use_function uses inline box-shadow)');
  if (!activeMenu && !useFunctionActive) issues.push('使用指南菜单未高亮');

  // 8. Check .headline_head
  const headlineHead = await page.$eval('.headline_head', el => el.textContent?.trim());
  console.log('.headline_head:', headlineHead);
  if (!headlineHead?.includes('使用指南')) issues.push('.headline_head 标题不正确');

  // 9. Check .guide_card strong
  const guideStrong = await page.$eval('.guide_card strong', el => {
    const cs = getComputedStyle(el);
    return { text: el.textContent?.trim(), color: cs.color, fontWeight: cs.fontWeight };
  });
  console.log('strong 样式:', JSON.stringify(guideStrong));

  // 10. Check body overflow
  const bodyOverflow = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { overflowX: cs.overflowX, overflowY: cs.overflowY };
  });
  console.log('body overflow:', JSON.stringify(bodyOverflow));

  // 11. Check .guide_card line-height for readability
  const lineHeight = await page.$eval('.guide_card p', el => getComputedStyle(el).lineHeight);
  console.log('.guide_card p lineHeight:', lineHeight);
  if (parseFloat(lineHeight) < 1.5) issues.push(`.guide_card p lineHeight 过小: ${lineHeight}`);

  // Screenshot
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/use_function-uiux.png' });
  console.log('\n截图已保存: screenshots/use_function-uiux.png');

  console.log(`\n=== 发现问题数: ${issues.length} ===`);
  for (const issue of issues) {
    console.log(`  [ISSUE] ${issue}`);
  }

  if (issues.length > 0) {
    expect(issues.length).toBe(0);
  }
});
