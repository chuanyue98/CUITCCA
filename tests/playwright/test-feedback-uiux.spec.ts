import { test, expect } from '@playwright/test';

test('问题反馈页面 UI/UX 深度检查', async ({ page }) => {
  await page.goto('http://localhost:8000/web/feed_back.html', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);

  console.log('\n=== 问题反馈页面 UI/UX 深度检查 ===\n');
  const issues: string[] = [];

  // 1. #side_left
  const sidebarDisplay = await page.$eval('#side_left', el => getComputedStyle(el).display);
  const sidebarWidth = await page.$eval('#side_left', el => `${Math.round(el.getBoundingClientRect().width)}px`);
  console.log(`#side_left display=${sidebarDisplay} width=${sidebarWidth}`);
  if (sidebarDisplay !== 'block') issues.push('#side_left 不是 block');
  if (parseFloat(sidebarWidth) < 200 || parseFloat(sidebarWidth) > 400) issues.push(`#side_left 宽度异常: ${sidebarWidth}`);

  // 2. .feedback_container layout
  const feedbackContainer = await page.$eval('.feedback_container', el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { display: cs.display, padding: `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}`, width: r.width, height: r.height };
  });
  console.log(`.feedback_container display=${feedbackContainer.display} padding=${feedbackContainer.padding} size=${feedbackContainer.width}x${feedbackContainer.height}`);
  if (feedbackContainer.display === 'none') issues.push('.feedback_container 不可见');

  // 3. .feedback_card width
  const feedbackCard = await page.$eval('.feedback_card', el => {
    const r = el.getBoundingClientRect();
    return `${Math.round(r.width)}px`;
  });
  console.log(`.feedback_card width=${feedbackCard}`);
  if (parseFloat(feedbackCard) > 800 || parseFloat(feedbackCard) < 300) issues.push(`.feedback_card 宽度异常: ${feedbackCard}`);

  // 4. #email input
  const emailInput = await page.$eval('#email', el => {
    const cs = getComputedStyle(el);
    return { type: el.type, display: cs.display, fontSize: cs.fontSize, width: cs.width };
  });
  console.log(`#email type=${emailInput.type} display=${emailInput.display} fontSize=${emailInput.fontSize} width=${emailInput.width}`);
  if (emailInput.type !== 'email') issues.push('#email 不是 email 类型');
  if (emailInput.display === 'none') issues.push('#email 不可见');

  // 5. #feedback textarea
  const feedbackTextarea = await page.$eval('#feedback', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, fontSize: cs.fontSize, width: cs.width, minHeight: cs.minHeight };
  });
  console.log(`#feedback display=${feedbackTextarea.display} fontSize=${feedbackTextarea.fontSize} width=${feedbackTextarea.width}`);
  if (parseFloat(feedbackTextarea.fontSize) < 13) issues.push('#feedback 字体太小');

  // 6. #feedbackButton
  const submitBtn = await page.$eval('#feedbackButton', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, fontSize: cs.fontSize, padding: cs.padding, color: cs.color, backgroundColor: cs.backgroundColor };
  });
  console.log(`#feedbackButton display=${submitBtn.display} fontSize=${submitBtn.fontSize} padding=${submitBtn.padding} color=${submitBtn.color} backgroundColor=${submitBtn.backgroundColor}`);
  if (submitBtn.display === 'none') issues.push('#feedbackButton 不可见');

  // 7. #toast-container.position
  const toastContainer = await page.$eval('#toast-container', el => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { display: cs.display, top: `${Math.round(r.top)}px`, right: `${Math.round(r.width)}px`, zIndex: cs.zIndex };
  });
  console.log(`#toast-container display=${toastContainer.display} top=${toastContainer.top} right=${toastContainer.right} zIndex=${toastContainer.zIndex}`);
  if (toastContainer.display === 'none') issues.push('#toast-container 不可见');
  if (parseFloat(toastContainer.top) > 100) issues.push('#toast-container 位置异常，应在顶部');

  // 8. Check text contrast on form elements
  const formElements = await page.$$eval('#email, #feedback', els => els.map(el => {
    const cs = getComputedStyle(el);
    return { tag: el.tagName, color: cs.color, backgroundColor: cs.backgroundColor };
  }));
  console.log('表单元素颜色:', JSON.stringify(formElements));

  // 9. Check no body scroll
  const bodyOverflow = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { overflowX: cs.overflowX, overflowY: cs.overflowY };
  });
  console.log('body overflow:', JSON.stringify(bodyOverflow));

  // 10. Check .feedback_submit_wrap
  const submitWrap = await page.$eval('.feedback_submit_wrap', el => {
    const cs = getComputedStyle(el);
    return { display: cs.display, justifyContent: cs.justifyContent };
  });
  console.log(`.feedback_submit_wrap display=${submitWrap.display} justifyContent=${submitWrap.justifyContent}`);
  if (submitWrap.display === 'none') issues.push('.feedback_submit_wrap 不可见');
  if (submitWrap.justifyContent !== 'center') issues.push('.feedback_submit_wrap 未居中');

  // 11. Check #side_left highlights feedback
  const activeMenu = await page.$eval('.menu_item_row.active', el => {
    const cs = getComputedStyle(el);
    return { text: el.textContent?.trim(), backgroundColor: cs.backgroundColor };
  });
  console.log('活跃菜单项:', activeMenu ? activeMenu.text : '无');
  if (activeMenu && !activeMenu.text.includes('问题反馈')) issues.push('问题反馈菜单未高亮');

  // 12. Check #headline_head text
  const headlineHead = await page.$eval('.headline_head', el => el.textContent?.trim());
  console.log('.headline_head:', headlineHead);
  if (!headlineHead?.includes('问题反馈')) issues.push('.headline_head 标题不正确');

  // 13. Check overall form readability
  const feedbackCardStyle = await page.$eval('.glass_card', el => {
    const cs = getComputedStyle(el);
    return { backgroundColor: cs.backgroundColor, borderRadius: cs.borderRadius };
  });
  console.log('.glass_card 背景:', feedbackCardStyle.backgroundColor, '圆角:', feedbackCardStyle.borderRadius);

  // Screenshot
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/feedback-uiux.png' });
  console.log('\n截图已保存: screenshots/feedback-uiux.png');

  console.log(`\n=== 发现问题数: ${issues.length} ===`);
  for (const issue of issues) {
    console.log(`  [ISSUE] ${issue}`);
  }

  if (issues.length > 0) {
    expect(issues.length).toBe(0);
  }
});
