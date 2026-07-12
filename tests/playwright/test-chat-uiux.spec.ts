// ===== UI/UX 深度检查: 聊天页面 =====
// 重点检查对话框布局是否混乱

import { test, expect } from '@playwright/test';

test('聊天页面 UI/UX 深度检查', async ({ page }) => {
  await page.goto('http://localhost:8000/web/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);

  console.log('\n=== 聊天页面 UI/UX 深度检查 ===\n');
  const issues: string[] = [];

  // ===== 1. #chatbox 的 display 属性 =====
  const chatboxDisplay = await page.$eval('#chatbox', el => getComputedStyle(el).display);
  console.log(`#chatbox display: ${chatboxDisplay}`);
  if (chatboxDisplay === 'inline') {
    issues.push('CRITICAL: #chatbox display=inline，应该为 block 或 flex！inline 容器内的 flex 子元素会完全失效');
  }

  // ===== 2. 消息气泡的布局检查 =====
  const messages = await page.$$eval('.message', msgs => msgs.map(m => {
    const cs = getComputedStyle(m);
    const children = Array.from(m.children).map(c => ({
      className: c.className.replace(/\s+/g, ' ').trim(),
      width: getComputedStyle(c).width,
      height: getComputedStyle(c).height,
      flexGrow: cs.flexGrow,
      content: c.textContent.slice(0, 50)
    }));
    return {
      display: cs.display,
      width: cs.width,
      height: cs.height,
      children: children
    };
  }));

  console.log('\n--- 消息气泡结构 ---');
  for (const [i, msg] of messages.entries()) {
    console.log(`\nMessage[${i}] display=${msg.display} size=${msg.width}x${msg.height}`);
    for (const c of msg.children) {
      console.log(`  .${c.className} size=${c.width}x${c.height} flexGrow=${c.flexGrow} text="${c.content}"`);
    }
  }

  // ===== 3. sender_bot / sender_man 尺寸异常 =====
  for (const msg of messages) {
    for (const c of msg.children) {
      if (c.className.includes('sender_')) {
        const width = parseFloat(c.width);
        if (width > 200 || width < 50) {
          issues.push(`sender_ 元素尺寸异常: width=${c.width} (class=${c.className})`);
        }
        if (c.content.trim() === '') {
          issues.push(`sender_ 元素为空但占空间: class=${c.className}, width=${c.width}`);
        }
      }
      if (c.className.includes('box_side')) {
        const width = parseFloat(c.width);
        if (width > 0) {
          issues.push(`box_side 应该为 0 但有宽度: ${c.width}`);
        }
      }
    }
  }

  // ===== 4. content_bot 和 content_man 的对齐问题 =====
  const contentBots = await page.$$eval('.content_bot', els => els.map(el => {
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return {
      marginLeft: cs.marginLeft,
      marginRight: cs.marginRight,
      width: cs.width,
      maxWidth: cs.maxWidth,
      rect: { left: rect.left, width: rect.width }
    };
  }));

  console.log('\n--- 机器人消息气泡对齐 ---');
  for (const cb of contentBots) {
    console.log(`  marginLeft=${cb.marginLeft} marginRight=${cb.marginRight} size=${cb.width} maxWidth=${cb.maxWidth}`);
  }

  // ===== 5. 聊天输入框区域布局 =====
  const inputLayout = await page.$eval('.chat_container', el => {
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const children = Array.from(el.children).map(c => ({
      className: c.className.replace(/\s+/g, ' ').trim(),
      width: getComputedStyle(c).width,
      height: getComputedStyle(c).height,
      rect: { left: c.getBoundingClientRect().left, top: c.getBoundingClientRect().top }
    }));
    return { display: cs.display, rect, children };
  });

  console.log('\n--- 输入框区域布局 ---');
  console.log(`chat_container display=${inputLayout.display} rect=${JSON.stringify(inputLayout.rect)}`);
  for (const c of inputLayout.children) {
    console.log(`  .${c.className} size=${c.width}x${c.height} rect=${JSON.stringify(c.rect)}`);
  }

  // ===== 6. textarea 字体大小检查 =====
  const textareaFontSize = await page.$eval('#input', el => getComputedStyle(el).fontSize);
  console.log(`\n#input fontSize: ${textareaFontSize}`);
  if (parseFloat(textareaFontSize) > 16) {
    issues.push(`输入框字体过大: ${textareaFontSize} (>16px 显得突兀)`);
  }

  // ===== 7. 检查 footer 是否遮挡内容 =====
  const footerRect = await page.$eval('.foot_fix', el => {
    const r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, height: r.height };
  });
  console.log(`\n.foot_fix rect: top=${footerRect.top} bottom=${footerRect.bottom} height=${footerRect.height}`);

  const chatboxRect = await page.$eval('#chatbox', el => {
    const r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, height: r.height };
  });
  console.log(`#chatbox rect: top=${chatboxRect.top} bottom=${chatboxRect.bottom} height=${chatboxRect.height}`);

  if (chatboxRect.bottom > footerRect.top) {
    issues.push(`聊天内容区域与底部输入框重叠: chatbox.bottom=${chatboxRect.bottom}, footer.top=${footerRect.top}`);
  }

  // ===== 8. 检查 talk_outline 的 overflow =====
  const talkOverflow = await page.$eval('.talk_outline', el => getComputedStyle(el).overflow);
  console.log(`\n.talk_outline overflow: ${talkOverflow}`);
  if (talkOverflow === 'visible') {
    issues.push(`.talk_outline overflow=visible，内容可能溢出边界`);
  }

  // ===== 9. 检查消息内元素是否错位 =====
  const msgLayout = await page.$$eval('.message', els => els.map((el, idx) => {
    const cs = getComputedStyle(el);
    const children = Array.from(el.children);
    const classOrder = children.map(c => c.className.replace(/\s+/g, ' ').trim());
    const leftItems = children.filter(c => c.className.includes('content_') || c.className.includes('sender_')).map(c => c.getBoundingClientRect());
    return {
      idx,
      classOrder,
      leftItems: leftItems.map(r => ({ left: Math.round(r.left), width: Math.round(r.width) })),
      flexWrap: cs.flexWrap,
      flexDir: cs.flexDirection
    };
  }));

  console.log('\n--- 消息内部元素顺序 ---');
  for (const ml of msgLayout) {
    console.log(`  Message[${ml.idx}] flexWrap=${ml.flexWrap} flexDir=${ml.flexDir}`);
    console.log(`    类顺序: ${ml.classOrder.join(' > ')}`);
    console.log(`    位置: ${ml.leftItems.map(r => `(${r.left},${r.width})`).join(' ')}`);
  }

  // ===== 10. 检查头像与内容的间距 =====
  const avatarGaps = await page.$$eval('.message', els => {
    return els.map(el => {
      const items = Array.from(el.children);
      const gaps: { from: string; to: string; gap: number }[] = [];
      for (let i = 0; i < items.length - 1; i++) {
        const r1 = items[i].getBoundingClientRect();
        const r2 = items[i + 1].getBoundingClientRect();
        gaps.push({
          from: items[i].className.replace(/\s+/g, ' ').trim(),
          to: items[i + 1].className.replace(/\s+/g, ' ').trim(),
          gap: Math.round(r2.left - (r1.left + r1.width))
        });
      }
      return gaps;
    });
  });

  console.log('\n--- 头像与内容间距 ---');
  for (const [i, gaps] of avatarGaps.entries()) {
    for (const g of gaps) {
      console.log(`  Message[${i}] ${g.from} -> ${g.to}: gap=${g.gap}px`);
    }
  }

  // ===== 汇总 =====
  console.log(`\n=== 发现问题数: ${issues.length} ===`);
  for (const issue of issues) {
    console.log(`  [ISSUE] ${issue}`);
  }

  // 截图
  await page.screenshot({ path: '/home/cy/github/chuanyue98/CUITCCA/tests/playwright/screenshots/index-uiux.png' });
  console.log('\n截图已保存: screenshots/index-uiux.png');

  // 如果有关键问题，标记失败
  const criticalIssues = issues.filter(i => i.includes('CRITICAL'));
  if (criticalIssues.length > 0) {
    expect(criticalIssues.length).toBe(0);
  }
});
