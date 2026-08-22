// ===== 聊天页首屏引导入口 =====
// 空状态原来是一句欢迎语 + 一整屏空白：第一次用的人既看不出知识库覆盖了什么，
// 也不知道怎么问才问得准。这组用例锁住引导入口的存在与点击行为。

import { test, expect } from '@playwright/test';

const CHAT_URL = 'http://localhost:8522/';

test.describe('聊天页首屏引导', () => {
  test.beforeEach(async ({ page }) => {
    // 引导只在"没有历史对话"时出现，先清掉 localStorage 保证是空状态
    await page.goto(CHAT_URL, { waitUntil: 'networkidle', timeout: 15000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
  });

  test('空状态展示引导入口', async ({ page }) => {
    const chips = page.locator('.starter_chip');
    await expect(chips.first()).toBeVisible();
    expect(await chips.count()).toBeGreaterThanOrEqual(4);
  });

  test('不再展示标准问答/Agent 模式切换器', async ({ page }) => {
    // 架构决策（这个问题该走标准问答还是 Agent）已经收回后端自动路由
    // （handlers/auto_router.py），学生不需要也不该被要求先弄懂两条链路
    // 的区别才能问问题——页面上不应该再出现这个切换器。
    await expect(page.locator('.mode_switcher')).toHaveCount(0);
    await expect(page.locator('.mode_btn')).toHaveCount(0);
    // 清空对话按钮仍然要在（它是切换器旁边唯一保留的操作）。
    await expect(page.locator('.clear')).toBeVisible();
  });

  test('每个入口都带一个非空问题', async ({ page }) => {
    const questions = await page.$$eval('.starter_chip', els =>
      els.map(e => (e as HTMLElement).dataset.q || '')
    );
    expect(questions.length).toBeGreaterThan(0);
    for (const q of questions) {
      expect(q.trim().length).toBeGreaterThan(5);
    }
  });

  test('点击入口把问题填进输入框', async ({ page }) => {
    const first = page.locator('.starter_chip').first();
    const question = await first.getAttribute('data-q');
    await first.click();
    // 点击会立即发送（输入框随即被清空），所以断言"用户气泡里出现了这个问题"，
    // 这比断言输入框内容更贴近用户真正看到的结果。
    await expect(page.locator('.message.user').last()).toContainText(question!.slice(0, 10));
  });

  test('开始对话后引导入口消失', async ({ page }) => {
    await page.locator('.starter_chip').first().click();
    await expect(page.locator('#starter')).toHaveCount(0);
  });

  test('引导入口不遮挡输入区', async ({ page }) => {
    // 引导是塞在消息流里的，不能浮在输入框上方挡住操作
    const starter = await page.locator('#starter').boundingBox();
    const input = await page.locator('#input').boundingBox();
    expect(starter).not.toBeNull();
    expect(input).not.toBeNull();
    expect(starter!.y + starter!.height).toBeLessThanOrEqual(input!.y + 1);
  });
});

test.describe('清空对话', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(CHAT_URL, { waitUntil: 'networkidle', timeout: 15000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
  });

  test('按钮有可见文字标签，不只是一个图标', async ({ page }) => {
    // 原来是输入行里一个裸垃圾桶图标，只有 hover tooltip 说明用途——移动端
    // 没有 hover，用户根本不知道它是干什么的。
    await expect(page.locator('.clear')).toContainText('清空');
  });

  test('取消确认时不清空', async ({ page }) => {
    page.on('dialog', d => d.dismiss());
    await page.locator('.starter_chip').first().click();
    await expect(page.locator('.message.user')).toHaveCount(1);

    await page.locator('.clear').click();
    await page.waitForTimeout(300);
    // 用户点了取消，对话必须还在
    await expect(page.locator('.message.user')).toHaveCount(1);
  });

  test('确认后回到与首次加载一致的空状态', async ({ page }) => {
    // 这里曾经有个真实缺陷：clearAllMessage 自己硬编码了一段和 index.html
    // 不一样的欢迎语，而且引导入口清空后不会回来——于是欢迎语写着"试试下面
    // 这些"，下面却什么都没有。
    const initialGreeting = (await page.locator('.content_bot').first().textContent())?.trim();
    const initialChips = await page.locator('.starter_chip').count();

    page.on('dialog', d => d.accept());
    await page.locator('.starter_chip').first().click();
    await expect(page.locator('.message.user')).toHaveCount(1);

    await page.locator('.clear').click();
    await page.waitForTimeout(600);

    await expect(page.locator('.message.user')).toHaveCount(0);
    await expect(page.locator('.starter_chip')).toHaveCount(initialChips);
    expect((await page.locator('.content_bot').first().textContent())?.trim()).toBe(initialGreeting);
  });

  test('清空后引导入口仍然可点', async ({ page }) => {
    // innerHTML 还原会换掉整棵子树，事件监听必须重新绑定，否则引导变成死按钮
    page.on('dialog', d => d.accept());
    await page.locator('.starter_chip').first().click();
    await page.locator('.clear').click();
    await page.waitForTimeout(600);

    await page.locator('.starter_chip').first().click();
    await expect(page.locator('.message.user')).toHaveCount(1);
  });
});

test.describe('回答里的 Markdown 表格', () => {
  test('表格渲染出边框与表头，不是一堆纯文字', async ({ page }) => {
    // 语料里大量内容（借阅规则、校车时刻表、奖学金标准）本来就是表格，后端解析器
    // 专门把它们还原成了 Markdown 表格。前端如果没有 table 样式，这一层结构会在
    // 最后一步又被拍平成流水账——这条用例就是钉住这件事。
    await page.goto(CHAT_URL, { waitUntil: 'networkidle', timeout: 15000 });
    await page.evaluate(() => {
      const box = document.getElementById('chatbox')!;
      const msg = document.createElement('div');
      msg.className = 'message bot';
      const content = document.createElement('div');
      content.className = 'content_bot';
      // 至少两行：样式里刻意去掉了最后一行的下边框（表格底部有容器边界，
      // 再画一条会显得脏），只放一行的话断言的正是被有意去掉的那条线。
      content.innerHTML =
        '<table><thead><tr><th>读者类型</th><th>册数</th></tr></thead>' +
        '<tbody><tr><td>本科生</td><td>10 册</td></tr>' +
        '<tr><td>硕士生</td><td>15 册</td></tr></tbody></table>';
      msg.appendChild(content);
      box.appendChild(msg);
    });

    const th = page.locator('.content_bot thead th').first();
    await expect(th).toBeVisible();

    const styles = await th.evaluate(el => {
      const cs = getComputedStyle(el);
      return { padding: cs.paddingLeft, bg: cs.backgroundColor };
    });
    // 有内边距 + 表头有底色 = 样式确实生效了（浏览器默认表格两者都没有）
    expect(parseFloat(styles.padding)).toBeGreaterThan(4);
    expect(styles.bg).not.toBe('rgba(0, 0, 0, 0)');

    const borderBottom = await page
      .locator('.content_bot td')
      .first()
      .evaluate(el => getComputedStyle(el).borderBottomWidth);
    expect(parseFloat(borderBottom)).toBeGreaterThan(0);
  });
});
