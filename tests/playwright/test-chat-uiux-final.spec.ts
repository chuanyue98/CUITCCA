import { test, expect } from '@playwright/test';

test('聊天页面 UI/UX 最终检查', async ({ page }) => {
  await page.goto('http://localhost:8522/web/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);

  console.log('\n=== 聊天页面 UI/UX 最终检查 ===\n');
  const results: { check: string; status: 'PASS' | 'FAIL'; detail: string }[] = [];

  // 1. #chatbox display
  const chatboxDisplay = await page.$eval('#chatbox', el => getComputedStyle(el).display);
  results.push({ check: '#chatbox display', status: chatboxDisplay === 'flex' ? 'PASS' : 'FAIL', detail: chatboxDisplay });

  // 2. #chatbox flex-direction
  const chatboxFlexDir = await page.$eval('#chatbox', el => getComputedStyle(el).flexDirection);
  results.push({ check: '#chatbox flex-direction', status: chatboxFlexDir === 'column' ? 'PASS' : 'FAIL', detail: chatboxFlexDir });

  // 3. sender_bot size
  const senderBotEl = await page.$('.sender_bot');
  if (senderBotEl) {
    const senderBotSize = await senderBotEl.evaluate(el => {
      const cs = getComputedStyle(el);
      return `${cs.width}x${cs.height}`;
    });
    results.push({ check: '.sender_bot 尺寸', status: senderBotSize === '0pxx0px' ? 'PASS' : 'FAIL', detail: senderBotSize });
  } else {
    results.push({ check: '.sender_bot 尺寸', status: 'PASS', detail: '不存在' });
  }

  // 4. sender_man size
  const senderManEl = await page.$('.sender_man');
  if (senderManEl) {
    const senderManSize = await senderManEl.evaluate(el => {
      const cs = getComputedStyle(el);
      return `${cs.width}x${cs.height}`;
    });
    results.push({ check: '.sender_man 尺寸', status: senderManSize === '0pxx0px' ? 'PASS' : 'FAIL', detail: senderManSize });
  } else {
    results.push({ check: '.sender_man 尺寸', status: 'PASS', detail: '不存在' });
  }

  // 5. textarea font-size
  const textareaFontSize = await page.$eval('#input', el => getComputedStyle(el).fontSize);
  results.push({ check: '#input 字体', status: parseFloat(textareaFontSize) <= 16 ? 'PASS' : 'FAIL', detail: textareaFontSize });

  // 6. .talk_outline overflow
  const talkOverflow = await page.$eval('.talk_outline', el => getComputedStyle(el).overflow);
  results.push({ check: '.talk_outline overflow', status: talkOverflow === 'auto' ? 'PASS' : 'FAIL', detail: talkOverflow });

  // 7. .talk_content overflow
  const talkContentOverflow = await page.$eval('.talk_content', el => getComputedStyle(el).overflow);
  results.push({ check: '.talk_content overflow', status: talkContentOverflow === 'auto' ? 'PASS' : 'FAIL', detail: talkContentOverflow });

  // 8. .foot_fix position
  const footFixPosition = await page.$eval('.foot_fix', el => getComputedStyle(el).position);
  results.push({ check: '.foot_fix position', status: footFixPosition !== 'absolute' ? 'PASS' : 'FAIL', detail: footFixPosition });

  // 9. .chat_container align-items
  const chatContainerAlign = await page.$eval('.chat_container', el => getComputedStyle(el).alignItems);
  results.push({ check: '.chat_container align-items', status: chatContainerAlign === 'center' ? 'PASS' : 'FAIL', detail: chatContainerAlign });

  // 10. .talk_outlinein position
  const talkOutlineInPosition = await page.$eval('.talk_outlinein', el => getComputedStyle(el).position);
  results.push({ check: '.talk_outlinein position', status: talkOutlineInPosition !== 'relative' ? 'PASS' : 'FAIL', detail: talkOutlineInPosition });

  // 11. Check message content is visible
  const contentBotText = await page.$eval('.content_bot', el => el.textContent?.slice(0, 30));
  results.push({ check: '消息内容可见', status: contentBotText ? 'PASS' : 'FAIL', detail: contentBotText || '无内容' });

  // 12. Check message avatar exists
  const avatarExists = await page.$('.content_bot_img');
  results.push({ check: '机器人头像存在', status: avatarExists ? 'PASS' : 'FAIL', detail: avatarExists ? '存在' : '不存在' });

  // 13. Check no chatbox-content overlap
  const chatboxBottom = await page.$eval('#chatbox', el => el.getBoundingClientRect().bottom);
  const footFixTop = await page.$eval('.foot_fix', el => el.getBoundingClientRect().top);
  results.push({ check: '无内容重叠', status: chatboxBottom <= footFixTop ? 'PASS' : 'FAIL', detail: `chatbox.bottom=${Math.round(chatboxBottom)}, foot_fix.top=${Math.round(footFixTop)}` });

  // 14. Check input container is centered (corrected logic)
  const chatContainerRect = await page.$eval('.chat_container', el => el.getBoundingClientRect());
  const chatTalkContainerRect = await page.$eval('.chat_talk_container', el => el.getBoundingClientRect());
  const containerCenter = chatContainerRect.left + chatContainerRect.width / 2;
  const talkCenter = chatTalkContainerRect.left + chatTalkContainerRect.width / 2;
  const centerOffset = Math.abs(talkCenter - containerCenter);
  results.push({ check: '输入框居中', status: centerOffset < 100 ? 'PASS' : 'FAIL', detail: `offset=${Math.round(centerOffset)}px, talk_center=${Math.round(talkCenter)}, container_center=${Math.round(containerCenter)}` });

  // 15. Check clear button is visible
  const clearButtonVisible = await page.$eval('.clear', el => {
    const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }).catch(() => false);
  results.push({ check: '清空按钮可见', status: clearButtonVisible ? 'PASS' : 'FAIL', detail: clearButtonVisible ? '可见' : '不可见' });

  // 16. Check submit button is visible
  const submitButtonVisible = await page.$eval('#submit', el => {
    const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }).catch(() => false);
  results.push({ check: '发送按钮可见', status: submitButtonVisible ? 'PASS' : 'FAIL', detail: submitButtonVisible ? '可见' : '不可见' });

  // Print results
  console.log('\n--- 检查结果 ---');
  for (const r of results) {
    const icon = r.status === 'PASS' ? '✅' : '❌';
    console.log(`  ${icon} ${r.check}: ${r.detail}`);
  }

  const passCount = results.filter(r => r.status === 'PASS').length;
  const failCount = results.filter(r => r.status === 'FAIL').length;
  console.log(`\n总计: ✅${passCount} ❌${failCount}`);

  // Screenshot
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/index-uiux-final.png' });
  console.log('\n截图已保存: screenshots/index-uiux-final.png');

  expect(failCount).toBe(0);
});
