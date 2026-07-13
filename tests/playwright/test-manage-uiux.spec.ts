import { test, expect } from '@playwright/test';

test('知识库管理页面 UI/UX 深度检查', async ({ page }) => {
  await page.goto('http://localhost:8522/web/manage.html', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  console.log('\n=== 知识库管理页面 UI/UX 深度检查 ===\n');
  const issues: string[] = [];

  // 1. #side_left display & width
  const sidebarDisplay = await page.$eval('#side_left', el => getComputedStyle(el).display);
  const sidebarWidth = await page.$eval('#side_left', el => {
    const r = el.getBoundingClientRect();
    return `${Math.round(r.width)}px`;
  });
  console.log(`#side_left display=${sidebarDisplay} width=${sidebarWidth}`);
  if (sidebarDisplay !== 'block') issues.push('#side_left 不是 block 显示模式');
  if (parseFloat(sidebarWidth) < 200 || parseFloat(sidebarWidth) > 400) issues.push(`#side_left 宽度异常: ${sidebarWidth}`);

  // 2. .dashboard_container layout
  const dashboard = await page.$eval('.dashboard_container', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, flexDirection: cs.flexDirection, overflow: cs.overflow };
  });
  console.log(`.dashboard_container display=${dashboard.display} flexDirection=${dashboard.flexDirection} overflow=${dashboard.overflow}`);
  if (dashboard.flexDirection !== 'row') issues.push('.dashboard_container flex-direction 不是 row');

  // 3. .panel_left & .panel_right width
  const panelLeft = await page.$eval('.panel_left', el => {
    const r = el.getBoundingClientRect();
    return `${Math.round(r.width)}px`;
  });
  const panelRight = await page.$eval('.panel_right', el => {
    const r = el.getBoundingClientRect();
    return `${Math.round(r.width)}px`;
  });
  console.log(`.panel_left=${panelLeft} .panel_right=${panelRight}`);
  if (parseFloat(panelLeft) < 300) issues.push(`.panel_left 太窄: ${panelLeft}`);

  // 4. Check .glass_card is visible
  const glassCards = await page.$$('.glass_card');
  console.log(`.glass_card 数量: ${glassCards.length}`);
  if (glassCards.length < 2) issues.push('.glass_card 数量不足，应有至少 2 个');

  // 5. Check tabs
  const tabBtns = await page.$$('.tab_btn');
  console.log(`.tab_btn 数量: ${tabBtns.length}`);
  if (tabBtns.length !== 3) issues.push(`.tab_btn 数量异常: 期望 3 个, 实际 ${tabBtns.length}`);

  // 6. Check tab content visibility
  const tabContents = await page.$$eval('.tab_content', els => els.map(el => {
    const cs = getComputedStyle(el);
    return { class: el.className, display: cs.display };
  }));
  console.log('.tab_content 状态:', JSON.stringify(tabContents));
  const activeTab = tabContents.find(t => t.display !== 'none');
  if (!activeTab) issues.push('无 tab_content 处于显示状态');

  // 7. Check #drag-zone
  const dragZone = await page.$eval('#drag-zone', el => {
    const cs = getComputedStyle(el);
    return {
      display: cs.display,
      borderStyle: cs.borderStyle,
      padding: `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}`
    };
  });
  console.log(`#drag-zone display=${dragZone.display} borderStyle=${dragZone.borderStyle} padding=${dragZone.padding}`);
  if (dragZone.display === 'none') issues.push('#drag-zone 不可见');

  // 8. Check .node_card styling
  const nodeCards = await page.$$eval('.node_card', els => els.map(el => {
    const cs = getComputedStyle(el);
    return {
      display: cs.display,
      padding: cs.padding,
      border: cs.borderStyle,
      borderRadius: cs.borderRadius,
      width: el.getBoundingClientRect().width,
      height: el.getBoundingClientRect().height
    };
  }));
  console.log('.node_card 数量:', nodeCards.length);
  for (const [i, nc] of nodeCards.entries()) {
    console.log(`  node_card[${i}] display=${nc.display} size=${nc.width}x${nc.height} borderRadius=${nc.borderRadius}`);
    if (nc.display === 'none') issues.push(`node_card[${i}] 不可见`);
    if (parseFloat(nc.borderRadius) < 4) issues.push(`node_card[${i}] borderRadius 太小: ${nc.borderRadius}`);
  }

  // 9. Check #loading-overlay (hidden by default)
  const loadingOverlay = await page.$eval('#loading-overlay', el => {
    const cs = getComputedStyle(el);
    return { opacity: cs.opacity, visibility: cs.visibility };
  });
  console.log(`#loading-overlay opacity=${loadingOverlay.opacity} visibility=${loadingOverlay.visibility}`);
  if (loadingOverlay.visibility !== 'hidden') issues.push('#loading-overlay 应该默认隐藏');

  // 10. Check #pagination-bar
  const paginationBar = await page.$eval('#pagination-bar', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, height: cs.height };
  });
  console.log(`#pagination-bar display=${paginationBar.display} height=${paginationBar.height}`);
  if (paginationBar.display === 'none' && nodeCards.length > 0) issues.push('有节点但分页栏不可见');

  // 11. Check text contrast - node_editor
  const nodeEditorStyle = await page.$eval('.node_editor', el => {
    const cs = getComputedStyle(el);
    return {
      fontSize: cs.fontSize,
      color: cs.color,
      lineHeight: cs.lineHeight,
      padding: cs.padding
    };
  });
  console.log(`.node_editor fontSize=${nodeEditorStyle.fontSize} color=${nodeEditorStyle.color} lineHeight=${nodeEditorStyle.lineHeight}`);
  if (parseFloat(nodeEditorStyle.fontSize) < 12) issues.push('.node_editor 字体太小');

  // 12. Check input fields
  const inputFields = await page.$$eval('.form_group input, .form_group textarea', els => els.map(el => {
    const cs = getComputedStyle(el);
    return { type: el.tagName, display: cs.display, width: cs.width };
  }));
  console.log('.form_group 输入框:', JSON.stringify(inputFields));

  // 13. Check buttons
  const btns = await page.$$eval('.btn-submit, .btn', els => els.map(el => ({
    text: el.textContent?.trim(),
    display: getComputedStyle(el).display,
    width: getComputedStyle(el).width
  })));
  console.log('按钮:', JSON.stringify(btns));

  // 14. Check .node_search_input
  const searchInput = await page.$eval('#node-search', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, width: cs.width };
  });
  console.log(`#node-search display=${searchInput.display} width=${searchInput.width}`);

  // 15. Check #toast-container
  const toastContainer = await page.$eval('#toast-container', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, zIndex: cs.zIndex };
  });
  console.log(`#toast-container display=${toastContainer.display} zIndex=${toastContainer.zIndex}`);

  // 16. Check no horizontal scroll
  const overflowX = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { overflowX: cs.overflowX, overflowY: cs.overflowY };
  });
  console.log('body overflow:', JSON.stringify(overflowX));

  // Screenshot
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/manage-uiux.png' });
  console.log('\n截图已保存: screenshots/manage-uiux.png');

  // Summary
  console.log(`\n=== 发现问题数: ${issues.length} ===`);
  for (const issue of issues) {
    console.log(`  [ISSUE] ${issue}`);
  }

  if (issues.length > 0) {
    expect(issues.length).toBe(0);
  }
});
