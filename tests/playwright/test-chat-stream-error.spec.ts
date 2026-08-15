// ===== 流式回答中途失败时的降级表现 =====
// 真实触发场景：Agent 分支跑到一半，决策 LLM 调用被供应商限流（429 rpm
// exhausted）打断。后端 agents/agent_workflow.py 捕获后发一个 error 事件干净
// 收尾，剩下的全看前端怎么呈现——这里锁住三条，都是实际踩过的坑：
//
// 1. 错误文案不能拼进答案正文。Agent 调工具前会先流出一段过程独白
//    （"让我先检索校园知识库。"），失败时屏幕上只剩独白，再拼上"刚才没能查完"
//    就成了一段前言不搭后语的话，用户会以为模型在胡言乱语。
// 2. route badge 不能停在"正在深入查证…"。清除它的代码原来只在 done 分支里，
//    而失败路径永远走不到 done，于是看起来像卡死。
// 3. 失败的这轮不写 localStorage 历史。半截独白被当成正常回答存下来，刷新后
//    还会重放，而且没有 done 事件就没有 👍👎 行，用户连纠正的入口都没有。
//
// 用 page.route 伪造 NDJSON 流，不依赖真的把后端打到限流。

import { test, expect } from '@playwright/test';

const CHAT_URL = 'http://localhost:8522/web/';
const PARTIAL_TEXT = '我来帮您查询学校有哪些学院。让我先检索校园知识库。';
const ERROR_TEXT = '刚才没能查完，请稍后再试一次。';

/** 拼一条以 error 事件结尾（没有 done）的 NDJSON 流，模拟 Agent 中途被限流打断。 */
function agentFailureStream(): string {
  return [
    { type: 'route', mode: 'agent', reason: '检索置信度不足（top1=0.01 < 0.60），交给 Agent 深入查证' },
    { type: 'tool_call', tool_name: 'search_knowledge_base', tool_kwargs: { query: '学校有哪些学院' } },
    { type: 'tool_result', tool_name: 'search_knowledge_base', is_error: false, output: '（片段）' },
    { type: 'token', content: PARTIAL_TEXT },
    { type: 'error', message: ERROR_TEXT },
  ].map(e => JSON.stringify(e)).join('\n') + '\n';
}

test.describe('流式回答中途失败', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(CHAT_URL, { waitUntil: 'networkidle', timeout: 15000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.route('**/graph/ask_stream', async route => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'application/x-ndjson' },
        body: agentFailureStream(),
      });
    });
    await page.fill('#input', '学校有哪些学院');
    await page.click('#submit');
    await expect(page.locator('.answer_error')).toBeVisible({ timeout: 10000 });
  });

  test('错误文案独立成块，不混进答案正文', async ({ page }) => {
    const answerText = await page.locator('.message.bot .replycontent').last().innerText();
    // 已经流出的内容原样保留……
    expect(answerText).toContain('让我先检索校园知识库');
    // ……但故障提示不能出现在正文里
    expect(answerText).not.toContain(ERROR_TEXT);

    const errorBlock = page.locator('.answer_error');
    await expect(errorBlock).toHaveText(ERROR_TEXT);
  });

  test('route badge 不再停在进行时', async ({ page }) => {
    const badge = page.locator('.route_badge');
    await expect(badge).toBeVisible();
    await expect(badge).not.toHaveText('正在深入查证…');
    await expect(badge).toHaveClass(/is-failed/);
  });

  test('失败的这轮不写进历史', async ({ page }) => {
    // 给收尾逻辑一点时间（finalizeMeta / loadCitations 都在 error 之后）
    await page.waitForTimeout(800);
    const stored = await page.evaluate(() => {
      const keys = Object.keys(localStorage);
      return keys.map(k => localStorage.getItem(k) || '').join('\n');
    });
    expect(stored).not.toContain('让我先检索校园知识库');
    expect(stored).not.toContain(ERROR_TEXT);
  });

  test('不叠加"我还不知道"兜底文案', async ({ page }) => {
    // 已经有错误区块说明情况了，再补一句"我还不知道"是第二段互相矛盾的提示
    const answerText = await page.locator('.message.bot .replycontent').last().innerText();
    expect(answerText).not.toContain('我还不知道');
  });
});
