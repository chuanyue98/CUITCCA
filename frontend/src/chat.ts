// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.ts、marked.min.js、purify.min.js 已在上方加载

import { apiFetch } from './utils/api';
import { showToast } from './utils/toast';

const HISTORY_KEY = 'cuitcca_chat_history_v1';
const HISTORY_MAX = 50;

// ===== 自动路由：后端按检索置信度自己决定走标准问答还是 Agent 模式 =====
// 原来这里有一个"标准问答/Agent 模式"切换器，把"这个问题复不复杂"的架构
// 决策甩给了用户——学生没有依据判断该点哪个按钮。现在所有提问统一发到
// /graph/ask_stream，后端（handlers/auto_router.py）先按检索置信度自动判定
// 走哪条链路，NDJSON 流里第一个事件（type: "route"）会带上判定结果，前端
// 只在自动升级到 Agent 深入查证时露出一个低调的提示，不需要用户预先选择。
const TOOL_NAME_LABELS: Record<string, string> = {
    search_knowledge_base: '知识库检索',
    list_knowledge_bases: '列出知识库',
    get_document_chunks_by_source: '按来源取原文',
    get_current_datetime: '当前日期',
};

// ===== 输入框事件 =====
const inputEl = document.getElementById('input') as HTMLInputElement;

// 自动增长输入框高度：超过 4 行高的内容不额外增长，用滚动显示
function autoResizeInput() {
    inputEl.style.height = 'auto';
    const maxHeight = 120;
    inputEl.style.height = Math.min(inputEl.scrollHeight, maxHeight) + 'px';
}

inputEl.addEventListener('input', autoResizeInput);

// 窄屏 placeholder 精简：完整文案"输入你的问题...（Enter 发送，Shift+Enter
// 换行）"在 390px 宽下会换到第二行，被 1 行高的 textarea 从中间切掉半截
// （截图确认），而且移动端软键盘本来就没有 Shift+Enter 概念，这段说明对
// 移动端是无意义信息。html 里保留完整文案作为默认值（宽屏 / 首次渲染）。
const FULL_PLACEHOLDER = inputEl.placeholder;
const SHORT_PLACEHOLDER = '输入你的问题...';
const mobilePlaceholderQuery = window.matchMedia('(max-width: 480px)');
function syncPlaceholder(matches: boolean) {
    inputEl.placeholder = matches ? SHORT_PLACEHOLDER : FULL_PLACEHOLDER;
}
syncPlaceholder(mobilePlaceholderQuery.matches);
mobilePlaceholderQuery.addEventListener('change', (ev) => syncPlaceholder(ev.matches));

inputEl.addEventListener('keydown', function (event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        (document.getElementById('submit') as HTMLButtonElement).click();
    }
});

const changeborderDiv = document.getElementById('changeborder_div') as HTMLElement;
inputEl.addEventListener('focus', () => {
    // 切换 .is-focused 类而不是写死内联色值：焦点描边用 CSS 的 var(--primary)，
    // 暗色模式下 --primary 是浅蓝，写死的深蓝边框会看不见。
    changeborderDiv.classList.add('is-focused');
});
inputEl.addEventListener('blur', () => {
    changeborderDiv.classList.remove('is-focused');
});

// ===== Markdown 渲染 =====
function renderMarkdown(rawText: string): string {
    const html = marked.parse(rawText || '', { breaks: true });
    return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
}

// ===== 对话持久化 (localStorage) =====
function loadHistory(): Array<{ role: string; content: string; ts: number }> {
    try {
        const raw = localStorage.getItem(HISTORY_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

function saveHistory(history: Array<{ role: string; content: string; ts: number }>) {
    const trimmed = history.slice(-HISTORY_MAX);
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
    } catch (e) {
        // localStorage 不可用（隐私模式等）时静默跳过持久化
    }
}

function appendHistory(role: string, content: string) {
    const history = loadHistory();
    history.push({ role, content, ts: Date.now() });
    saveHistory(history);
}

function clearHistory() {
    try {
        localStorage.removeItem(HISTORY_KEY);
    } catch (e) {
        // 忽略
    }
}

function replayHistory() {
    const history = loadHistory();
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    if (history.length === 0) return;
    // 有历史记录时，移除默认欢迎语与首屏引导，改为回放真实历史
    chatbox.innerHTML = '';
    history.forEach(entry => {
        if (entry.role === 'user') {
            appendUserBubble(entry.content, { persist: false });
        } else {
            const { answerEl } = appendBotBubble({ persist: false });
            answerEl.innerHTML = renderMarkdown(entry.content);
        }
    });
    scrollToBottom();
}

function scrollToBottom() {
    // 真正装消息、可滚动的容器是 .talk_content（style.css 里 overflow-y:
    // auto 的那个），不是 .chat_bottom——.chat_bottom 是它的兄弟节点，待在
    // .talk_outline 这个外层容器里，可滚动余量恒为 0，scrollIntoView 在它
    // 身上是空操作（实测 12 轮对话后 scrollTop 停在 0，可滚动余量 1209px）。
    const scroller = document.querySelector('.talk_content') as HTMLElement | null;
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
}

// ===== DOM 构建 =====
function appendUserBubble(text: string, { persist = true }: { persist?: boolean } = {}): { message: HTMLElement; content: HTMLElement } {
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    const message = document.createElement('div');
    message.className = 'message user';
    const content = document.createElement('div');
    content.className = 'content_man';
    content.textContent = text;
    const img = document.createElement('div');
    img.className = 'content_man_img';
    message.appendChild(content);
    message.appendChild(img);
    chatbox.appendChild(message);
    if (persist) appendHistory('user', text);
    return { message, content };
}

function appendBotBubble({ persist = true }: { persist?: boolean } = {}): { message: HTMLElement; content: HTMLElement; answerEl: HTMLElement; citations: HTMLElement; persist: boolean } {
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    const message = document.createElement('div');
    message.className = 'message bot';
    const img = document.createElement('div');
    img.className = 'content_bot_img';
    const content = document.createElement('div');
    content.className = 'content_bot';
    const answerEl = document.createElement('div');
    answerEl.className = 'replycontent';
    content.appendChild(answerEl);
    const citations = document.createElement('div');
    citations.className = 'citations is-hidden';
    content.appendChild(citations);
    message.appendChild(img);
    message.appendChild(content);
    chatbox.appendChild(message);
    return { message, content, answerEl, citations, persist };
}

// ===== 加载态 =====
function showThinkingIndicator(answerEl: HTMLElement) {
    // 省略号由 .thinking-dots::after 的 CSS 动画逐段点亮，比静态"..."更有"正在
    // 打字"的临场感。
    answerEl.innerHTML = '<span class="thinking-indicator"><span class="thinking-spinner"></span>正在思考<span class="thinking-dots"></span></span>';
}

// ===== 主发送流程 =====
let activeAbortController: AbortController | null = null;

function setGeneratingUI(isGenerating: boolean) {
    (document.getElementById('submit') as HTMLButtonElement).disabled = isGenerating;
    (document.getElementById('submit') as HTMLElement).classList.toggle('is-loading', isGenerating);
    (document.getElementById('stop-generating') as HTMLElement).classList.toggle('is-hidden', !isGenerating);
}

// 首屏引导入口：一旦真的开始对话就没有存在意义了，收起来把空间还给消息流。
function dismissStarter() {
    document.getElementById('starter')?.remove();
}

function initStarter() {
    document.getElementById('starter')?.addEventListener('click', (ev) => {
        const chip = (ev.target as HTMLElement).closest('.starter_chip') as HTMLElement | null;
        if (!chip) return;
        const question = chip.dataset.q;
        if (!question) return;
        const input = document.getElementById('input') as HTMLInputElement;
        // 填进输入框再发送，而不是直接发：用户能看到自己"问了什么"，
        // 也保留了发送前改一改措辞的余地。
        input.value = question;
        sendMessage();
    });
}

function sendMessage() {
    const input = document.getElementById('input') as HTMLInputElement;
    const question = input.value.trim();
    if (question === '') return;

    // 新一轮提问开始：上一条回答下面的追问建议不再适用于当前语境，清掉，
    // 避免用户误以为那些建议还是针对"接下来要问什么"的。
    clearActiveSuggestions();
    dismissStarter();
    appendUserBubble(question);
    input.value = '';

    const { answerEl, citations, message } = appendBotBubble();
    showThinkingIndicator(answerEl);
    // 不再额外调用 message.scrollIntoView：它的平滑滚动会被后续 streamAsk
    // 里逐帧同步赋值 scrollTop 的 scrollToBottom 打断，两者打架。
    scrollToBottom();

    setGeneratingUI(true);
    streamAsk(question, answerEl, citations, message).finally(() => setGeneratingUI(false));
}

// ===== NDJSON 流式解析 + 工具调用轨迹 =====
// /graph/ask_stream 统一用 NDJSON（每行一个 JSON 事件），事件类型：
// route（路由判定，standard 或 agent，最先发出）、token（答案增量）、
// tool_call（自动升级到 agent 时，模型决定调某个工具）、tool_result（工具
// 返回）、done（结束）、suggestions（追问建议，done 之后单独发出）、error
// （出错兜底）。见 backend/app/router/graph.py 的 ask_stream docstring。

function createToolTraceContainer(contentEl: HTMLElement): HTMLElement {
    const trace = document.createElement('div');
    trace.className = 'agent-tooltrace is-hidden';
    const title = document.createElement('div');
    title.className = 'agent-tooltrace-title';
    title.textContent = '工具调用过程';
    trace.appendChild(title);
    contentEl.appendChild(trace);
    return trace;
}

function addToolTraceItem(traceEl: HTMLElement, toolName: string, args: Record<string, unknown> | null) {
    const label = TOOL_NAME_LABELS[toolName] || toolName;
    const item = document.createElement('div');
    item.className = 'agent-tool-item';

    const badge = document.createElement('span');
    badge.className = 'tool-badge';
    badge.textContent = label;
    item.appendChild(badge);

    const status = document.createElement('span');
    status.className = 'tool-status running';
    status.textContent = '运行中…';
    item.appendChild(status);

    const argsDiv = document.createElement('div');
    argsDiv.className = 'tool-args';
    try {
        argsDiv.textContent = args ? JSON.stringify(args) : '';
    } catch {
        argsDiv.textContent = '';
    }
    item.appendChild(argsDiv);

    traceEl.appendChild(item);
    traceEl.classList.remove('is-hidden');
    return { item, status, toolName, done: false };
}

function finishToolTraceItem(statusEl: HTMLElement, itemEl: HTMLElement, ok: boolean) {
    statusEl.textContent = ok ? '✓ 完成' : '✗ 失败';
    statusEl.className = 'tool-status ' + (ok ? 'ok' : 'fail');
    if (!ok) itemEl.classList.add('is-error');
}

function stopGenerating() {
    if (activeAbortController) {
        activeAbortController.abort();
    }
}

// ===== 追问建议：回答结束后的可点击胶囊 =====
// 用户反馈"提问本身就费劲"——追问建议让用户点着往下走，不用每次都自己想
// 问题该怎么问。复用引导入口的 .starter_chip 样式（视觉上是同一类"可以点的
// 建议问题"），点击行为也一致：填进输入框再发送。

let activeSuggestionsEl: HTMLElement | null = null;

function clearActiveSuggestions() {
    // 新一轮提问开始时调用：上一条回答下面的建议胶囊不再代表"接下来能问
    // 什么"，留着容易让人误点过时的建议。
    activeSuggestionsEl?.remove();
    activeSuggestionsEl = null;
}

function renderSuggestions(messageEl: HTMLElement, suggestions: string[]) {
    if (!suggestions.length) return;
    const contentEl = messageEl.querySelector('.content_bot') as HTMLElement | null;
    if (!contentEl) return;

    const wrap = document.createElement('div');
    wrap.className = 'followup_suggestions';
    suggestions.forEach(question => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'starter_chip followup_chip';
        chip.textContent = question;
        chip.addEventListener('click', () => {
            const input = document.getElementById('input') as HTMLInputElement;
            input.value = question;
            sendMessage();
        });
        wrap.appendChild(chip);
    });
    contentEl.appendChild(wrap);
    activeSuggestionsEl = wrap;
    scrollToBottom();
}

// ===== 回答质量反馈：👍 沉淀 / 👎 反馈 =====
// 反馈闭环的入口：👍 把这条问答沉淀进语义缓存（后续相似问题直接复用，Dify
// annotation reply 同款机制），👎 删除该问题的缓存条目并记录反馈。一条回答
// 只能反馈一次，点过之后按钮锁定，避免重复提交刷缓存。
function renderFeedbackRow(messageEl: HTMLElement, query: string, answer: string) {
    const contentEl = messageEl.querySelector('.content_bot') as HTMLElement | null;
    if (!contentEl) return;
    if (contentEl.querySelector('.answer_feedback')) return;

    const row = document.createElement('div');
    row.className = 'answer_feedback';

    const hint = document.createElement('span');
    hint.className = 'answer_feedback_hint';
    hint.textContent = '这个回答有帮助吗？';

    const upBtn = document.createElement('button');
    upBtn.type = 'button';
    upBtn.className = 'feedback_btn';
    upBtn.textContent = '👍 有帮助';
    upBtn.title = '沉淀为高价值问答，后续相似问题将直接复用此答案';

    const downBtn = document.createElement('button');
    downBtn.type = 'button';
    downBtn.className = 'feedback_btn';
    downBtn.textContent = '👎 没帮助';
    downBtn.title = '记录反馈，并移除该问答的缓存条目';

    const lock = (chosen: HTMLButtonElement, label: string) => {
        upBtn.disabled = true;
        downBtn.disabled = true;
        chosen.classList.add('chosen');
        chosen.textContent = label;
    };

    const submit = async (vote: 'up' | 'down', chosen: HTMLButtonElement, okLabel: string) => {
        lock(chosen, okLabel);
        try {
            const resp = await apiFetch('/graph/qa_feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body:
                    'query=' + encodeURIComponent(query) +
                    '&response=' + encodeURIComponent(answer) +
                    '&vote=' + vote,
            });
            showToast(resp.ok ? (vote === 'up' ? '已沉淀，相似问题将直接复用此答案' : '已记录反馈，感谢你的帮助') : '反馈提交失败，请稍后再试', resp.ok ? 'success' : 'error');
        } catch (e) {
            showToast('反馈提交失败，请检查网络', 'error');
        }
    };

    upBtn.addEventListener('click', () => submit('up', upBtn, '✓ 已沉淀'));
    downBtn.addEventListener('click', () => submit('down', downBtn, '✓ 已记录'));

    row.appendChild(hint);
    row.appendChild(upBtn);
    row.appendChild(downBtn);
    contentEl.appendChild(row);
}

// ===== 统一的 NDJSON 流式解析：standard/agent 两条链路共用一个解析器 =====
// /graph/ask_stream 对前端屏蔽了"走哪条链路"这个选择——但 Agent 分支的
// 工具调用轨迹展示（这个项目的亮点）不能因为自动路由就丢掉：route 事件一旦
// 表明这轮升级到了 agent，照样挂上工具轨迹容器和低调的"深入查证"提示；
// standard 分支自动路由时 route.mode === 'standard'，不需要额外提示，这是
// 多数问题走的零决策开销路径，不该每次都刷一条提示制造噪音。
async function streamAsk(
    query: string,
    answerEl: HTMLElement,
    citationsEl: HTMLElement,
    messageEl: HTMLElement,
) {
    activeAbortController = new AbortController();
    const startTs = performance.now();
    let firstTokenMs: number | null = null;
    let fullText = '';
    let firstChunk = true;
    let routeBadge: HTMLElement | null = null;
    // 后端发过 error 事件（Agent 决策 LLM 异常、超时等）。置位后影响三处收尾
    // 行为：不补"我还不知道"兜底、不写历史、不把错误文案混进答案正文。
    let runFailed = false;
    let traceEl: HTMLElement | null = null;
    const runningTraces: Array<{ status: HTMLElement; item: HTMLElement; toolName: string; done: boolean }> = [];

    // 回答元信息条：路由判定原因 + 首字/总耗时，放在气泡最底部一行小字。
    // 对日常用户是低噪的透明说明；对排查/演示场景，这一行把"后端自动路由
    // 架构"和"性能开销"直接摊开——比如标准问答会显示"已检索到高置信度内容
    // （top1=0.73）"，Agent 会显示"检索置信度不足，深入查证"，面试时指着
    // 它就能讲清楚两条链路的取舍。
    //
    // 注意：原设计里 standard 分支刻意不刷"用了什么模式"的提示（多数问题的
    // 零决策开销路径不该有噪音），这里把路由原因对所有模式都摊开是有意的
    // 偏离——这个 demo 的看点就是自动路由架构，代价只是一行 11px 三级色
    // 小字，可接受。
    const contentEl = messageEl.querySelector('.content_bot') as HTMLElement;
    const metaStrip = document.createElement('div');
    metaStrip.className = 'answer_meta is-hidden';
    const routePart = document.createElement('span');
    routePart.className = 'answer_meta_route';
    const timePart = document.createElement('span');
    timePart.className = 'answer_meta_time';
    metaStrip.appendChild(routePart);
    metaStrip.appendChild(timePart);
    contentEl.appendChild(metaStrip);

    const fmtSecs = (ms: number) => (ms / 1000).toFixed(1) + 's';
    let metaFinalized = false;
    const finalizeMeta = () => {
        // 幂等：总耗时只在第一次定格（done 事件 = 主回答结束的时刻），不能
        // 被后续的追问建议生成 / 引用来源请求重新刷新成更大的值。
        if (metaFinalized) return;
        metaFinalized = true;
        const totalMs = performance.now() - startTs;
        timePart.textContent =
            firstTokenMs !== null
                ? `首字 ${fmtSecs(firstTokenMs)} · 总耗时 ${fmtSecs(totalMs)}`
                : `总耗时 ${fmtSecs(totalMs)}`;
        metaStrip.classList.remove('is-hidden');
    };

    // rAF 节流：避免每个 NDJSON 事件都触发一次 Markdown 解析 + DOM 重绘。
    let rafId: number | null = null;
    let pendingText: string | null = null;
    const flushRender = () => {
        if (pendingText !== null) {
            answerEl.innerHTML = renderMarkdown(pendingText);
            scrollToBottom();
            pendingText = null;
        }
    };
    const cancelPendingRaf = () => {
        if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
    };
    const scheduleRender = (text: string) => {
        pendingText = text;
        if (rafId === null) {
            rafId = requestAnimationFrame(() => {
                rafId = null;
                flushRender();
            });
        }
    };

    try {
        const response = await apiFetch('/graph/ask_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'query=' + encodeURIComponent(query),
            signal: activeAbortController.signal,
        });

        if (!response.ok || !response.body) {
            throw new Error('HTTP ' + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // NDJSON：按行切分，每行一个完整 JSON 事件；跨 chunk 的半行留在 buffer
            let newlineIdx: number;
            while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
                const line = buffer.slice(0, newlineIdx).trim();
                buffer = buffer.slice(newlineIdx + 1);
                if (!line) continue;
                let event: Record<string, unknown>;
                try {
                    event = JSON.parse(line);
                } catch {
                    continue;
                }

                if (event.type === 'route') {
                    // route 事件是 NDJSON 流里第一个事件，带 mode（standard/
                    // agent/cache）和 reason（为什么走这条链路，比如
                    // "已检索到高置信度内容（top1=0.73）"）。mode=cache 表示
                    // 语义缓存命中（跳过检索与生成），同样摊开在元信息条里。
                    const modeLabel =
                        event.mode === 'agent'
                            ? 'Agent 深入查证'
                            : event.mode === 'cache'
                                ? '缓存命中'
                                : '标准问答';
                    const reason = String(event.reason || '');
                    routePart.textContent = modeLabel + ' · ' + reason;
                    routePart.title = '本次提问由后端自动路由判定：' + reason;
                    metaStrip.classList.remove('is-hidden');
                    if (event.mode === 'agent') {
                        routeBadge = document.createElement('div');
                        routeBadge.className = 'route_badge';
                        routeBadge.textContent = '正在深入查证…';
                        contentEl.insertBefore(routeBadge, answerEl);
                        traceEl = createToolTraceContainer(contentEl);
                        // 工具调用轨迹要插入在答案之前——先看到工具怎么查，
                        // 再看到答案。默认 appendChild 会放到底部（meta /
                        // feedback 之后），违反时间线顺序。
                        contentEl.insertBefore(traceEl, answerEl);
                    }
                } else if (event.type === 'token') {
                    if (firstTokenMs === null) {
                        firstTokenMs = performance.now() - startTs;
                    }
                    if (firstChunk) {
                        answerEl.innerHTML = '';
                        firstChunk = false;
                    }
                    fullText += String(event.content || '');
                    scheduleRender(fullText);
                } else if (event.type === 'tool_call') {
                    if (traceEl) {
                        const trace = addToolTraceItem(traceEl, String(event.tool_name), event.tool_kwargs as Record<string, unknown> | null);
                        runningTraces.push(trace);
                        scrollToBottom();
                    }
                } else if (event.type === 'tool_result') {
                    // 按 tool_name 匹配而不是 shift()：llama_index 支持并行工具
                    // 调用，结果返回顺序不一定等于调用顺序，shift 会配错对。
                    const trace = runningTraces.find(t => !t.done && t.toolName === String(event.tool_name));
                    if (trace) {
                        trace.done = true;
                        finishToolTraceItem(trace.status, trace.item, event.is_error !== true);
                    }
                } else if (event.type === 'error') {
                    // 关键：**不能**把错误文案拼进 fullText。Agent 在调工具前会
                    // 先流出一段过程独白（"我来帮您查询…让我先检索校园知识库。"），
                    // 正常跑完时后面跟着真答案还算通顺，但中途失败（实测是 LLM
                    // 供应商 429）时留在屏幕上的只有独白，再拼上"刚才没能查完"
                    // 就成了一段前言不搭后语的东西，用户以为是模型在胡言乱语。
                    // 改成：已经流出的内容原样保留，错误作为独立区块单独渲染，
                    // 两者视觉上分开，谁是答案、谁是故障提示一目了然。
                    runFailed = true;
                    if (firstChunk) {
                        answerEl.innerHTML = '';
                        firstChunk = false;
                    }
                    cancelPendingRaf();
                    flushRender();
                    const errorEl = document.createElement('div');
                    errorEl.className = 'answer_error';
                    errorEl.textContent = String(event.message || '出错了，请稍后再试一下');
                    answerEl.insertAdjacentElement('afterend', errorEl);
                    // 失败时 route badge 停在"正在深入查证…"会像是还在跑（清除
                    // 它的代码只在 done 分支里，而失败路径永远走不到 done）。
                    if (routeBadge) {
                        routeBadge.textContent = '查证未完成';
                        routeBadge.classList.add('is-failed');
                    }
                    scrollToBottom();
                } else if (event.type === 'done') {
                    // done 是主回答结束的信号，带 final response（agent 分支还有
                    // truncated 标记）。response 已经在 token 事件里流式展示过了。
                    // 总耗时在这里定格：done 之后还会来 suggestions 事件（那是
                    // 答案完成后才发起的额外 LLM 调用，最多 8 秒）和引用来源
                    // 请求，不能把这两段算进"回答耗时"。
                    finalizeMeta();
                    // 回答质量反馈行：👍 沉淀 / 👎 反馈。缓存命中（mode=cache）
                    // 的回答也挂——用户觉得缓存答案不行时正需要 👎 把坏条目删掉。
                    renderFeedbackRow(messageEl, query, fullText);
                    if (routeBadge) {
                        routeBadge.textContent = '已深入查证多个来源';
                    }
                    if (event.truncated === true && traceEl) {
                        const note = document.createElement('div');
                        note.className = 'agent-tooltrace-note';
                        note.textContent = '⚠ 本轮回答因工具调用轮数上限而收尾，可能不完整';
                        traceEl.appendChild(note);
                        traceEl.classList.remove('is-hidden');
                    }
                } else if (event.type === 'suggestions') {
                    // suggestions 在 done 之后单独发出——这是答案讲完之后才
                    // 生成的追问建议，跟主回答内容无关，不需要等它就能先展示答案。
                    renderSuggestions(messageEl, (event.suggestions as string[]) || []);
                }
            }
        }

        // 流异常结束（没收到 done 事件）时的兜底定格：正常路径 done 事件
        // 已经 finalize 过，这里幂等跳过。
        finalizeMeta();
        cancelPendingRaf();
        flushRender();

        // 一个字都没流出来时才补兜底文案；runFailed 时错误区块已经把情况说清楚
        // 了，再叠一句"我还不知道"是第二段互相矛盾的提示。
        if (!fullText.trim() && !runFailed) {
            fullText = '我还不知道，请反馈给我吧';
            answerEl.innerHTML = renderMarkdown(fullText);
        }

        // 失败的这轮不写历史：fullText 此时可能只是半截过程独白，存进
        // localStorage 会在刷新后被当成一条正常回答重放，而且因为没有 done
        // 事件、👍👎 反馈行也没挂上，用户连纠正它的入口都没有。
        if (!runFailed) {
            appendHistory('bot', fullText);
        }
        await loadCitations(citationsEl);
    } catch (error) {
        cancelPendingRaf();
        if (error instanceof Error && error.name === 'AbortError') {
            flushRender();
            if (fullText) {
                appendHistory('bot', fullText);
            } else {
                answerEl.innerHTML = renderMarkdown('*已停止生成*');
            }
            finalizeMeta();
            return;
        }
        console.error('请求失败:', error);
        const errText = '请求失败: ' + (error instanceof Error ? error.message : String(error));
        fullText = fullText || errText;
        // 失败气泡: 显示已生成的部分 + 错误信息 + 重试按钮
        const retryBtn = document.createElement('button');
        retryBtn.className = 'chat_retry_btn';
        retryBtn.type = 'button';
        retryBtn.textContent = '🔄 重试';
        retryBtn.addEventListener('click', () => {
            // 清空当前气泡内容, 重新发起相同 query 的流式生成
            answerEl.innerHTML = '';
            citationsEl.classList.add('is-hidden');
            citationsEl.innerHTML = '';
            showThinkingIndicator(answerEl);
            // 新建一个 abort controller, 避免与已结束的请求冲突
            const newAbort = new AbortController();
            activeAbortController = newAbort;
            // 本地这条链路的流式函数叫 streamAsk，且需要 messageEl（追问建议、
            // 反馈行都挂在整条消息上，不是只挂答案元素）——远端那版函数名与
            // 签名都不同，合并时按本地签名改过来。
            streamAsk(query, answerEl, citationsEl, messageEl).finally(() => setGeneratingUI(false));
            setGeneratingUI(true);
            retryBtn.remove();
        });
        answerEl.innerHTML = renderMarkdown(fullText);
        answerEl.appendChild(retryBtn);
        appendHistory('bot', fullText);
        finalizeMeta();
    } finally {
        activeAbortController = null;
    }
}

async function loadCitations(citationsEl: HTMLElement) {
    try {
        const response = await apiFetch('/graph/query_sources', { method: 'POST' });
        if (!response.ok) return;
        const data = await response.json();
        const nodes = (data.source_nodes || []).filter((n: { text?: string }) => n && n.text);
        if (nodes.length === 0) return;

        citationsEl.innerHTML = '';
        const toggle = document.createElement('button');
        toggle.className = 'citations_toggle';
        toggle.type = 'button';
        toggle.textContent = `参考来源 (${nodes.length})`;
        const list = document.createElement('div');
        list.className = 'citations_list is-hidden';
        nodes.forEach((node: { text: string; file_name?: string | null; score?: number | null }) => {
            const item = document.createElement('div');
            item.className = 'citation_item';
            // 头部：来源文件名 + 相关度分数（/graph/query_sources 返回的
            // score 是重排后的 cross-encoder 分数，能直观看出"这条依据有多
            // 可信"；检索质量的透明是 RAG demo 的核心看点）。
            const head = document.createElement('div');
            head.className = 'citation_head';
            const source = node.file_name || '未知来源';
            const scoreText =
                typeof node.score === 'number' && Number.isFinite(node.score)
                    ? '相关度 ' + node.score.toFixed(3)
                    : '';
            head.textContent = [source, scoreText].filter(Boolean).join(' · ');
            item.appendChild(head);
            const snippet = document.createElement('div');
            snippet.textContent = node.text.length > 200 ? node.text.slice(0, 200) + '…' : node.text;
            item.appendChild(snippet);
            // 复制按钮：复制的是**完整**原文，不是上面截断到 200 字的展示片段
            // ——核对信息时要的是全文。
            const copyBtn = document.createElement('button');
            copyBtn.className = 'citation_copy_btn';
            copyBtn.type = 'button';
            copyBtn.title = '复制';
            copyBtn.textContent = '📋';
            copyBtn.addEventListener('click', () => {
                navigator.clipboard?.writeText(node.text).then(() => {
                    copyBtn.textContent = '✓';
                    setTimeout(() => { copyBtn.textContent = '📋'; }, 1200);
                }).catch(() => { /* 静默 */ });
            });
            item.appendChild(copyBtn);
            list.appendChild(item);
        });
        toggle.addEventListener('click', () => list.classList.toggle('is-hidden'));
        citationsEl.appendChild(toggle);
        citationsEl.appendChild(list);
        citationsEl.classList.remove('is-hidden');
    } catch (e) {
        // 引用来源是增强信息，静默失败不影响主对话
    }
}

// ===== 清空对话 =====
// 空状态的唯一事实来源：页面刚加载时 #chatbox 的原始 HTML（欢迎语 + 首屏引导）。
//
// 之前这里自己硬编码了一段欢迎语，和 index.html 里那段早就不一致了，而且清空
// 之后引导入口不会回来——于是"点清空"和"刚打开页面"是两个不同的空状态，欢迎语
// 还自相矛盾地写着"试试下面这些"却什么都没有。快照 + 还原能保证两者永远一致，
// 也不用维护两份文案。
const EMPTY_STATE_HTML = (document.getElementById('chatbox') as HTMLElement)?.innerHTML ?? '';

function restoreEmptyState() {
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    chatbox.innerHTML = EMPTY_STATE_HTML;
}

async function clearAllMessage() {
    // 破坏性且不可撤销：本地历史、服务端上下文一起清掉。加一次确认——原来是
    // 一个只有 hover tooltip 的裸垃圾桶图标，误点的代价是整段对话没了。
    if (!window.confirm('确定清空当前对话吗？本地记录和助手的上下文记忆都会被清除，且无法恢复。')) {
        return;
    }
    clearHistory();
    try {
        await apiFetch('/graph/create', { method: 'POST' });
    } catch (e) {
        // 服务端重置失败不阻塞本地清空
    }
    restoreEmptyState();
    initStarter();
}

// ===== 页面初始化 =====
window.addEventListener('DOMContentLoaded', () => {
    replayHistory();
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('.clear')?.addEventListener('click', clearAllMessage);
  document.getElementById('stop-generating')?.addEventListener('click', stopGenerating);
  document.getElementById('submit')?.addEventListener('click', sendMessage);
  initStarter();
});
