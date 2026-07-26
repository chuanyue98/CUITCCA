// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.ts、marked.min.js、purify.min.js 已在上方加载

import { apiFetch } from './utils/api';

const HISTORY_KEY = 'cuitcca_chat_history_v1';
const HISTORY_MAX = 50;

// 统一欢迎语与示例问题，避免初始化 / 清空后两处文案不一致
const WELCOME_MESSAGE = '你好！我是成信大校园助手，你可以问我关于学校的任何问题。';
const WELCOME_EXAMPLES_HTML = `
    <div class="welcome_examples" id="welcome-examples">
        <div class="welcome_examples_hint">💡 试试这些问题，或接着追问「需要带什么证件？」体验多轮对话</div>
        <div class="example_questions">
            <button class="example_q" type="button">学校有哪些社团？</button>
            <button class="example_q" type="button">图书馆怎么借书？</button>
            <button class="example_q" type="button">宿舍几点熄灯？</button>
            <button class="example_q" type="button">怎么申请奖学金？</button>
        </div>
    </div>`;

// ===== 输入框事件 =====
const inputEl = document.getElementById('input') as HTMLInputElement;
inputEl.addEventListener('keydown', function (event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        (document.getElementById('submit') as HTMLButtonElement).click();
    }
});

const changeborderDiv = document.getElementById('changeborder_div') as HTMLElement;
inputEl.addEventListener('focus', () => {
    changeborderDiv.style.borderColor = 'rgb(151, 204, 242)';
    changeborderDiv.style.boxShadow = '0 12px 16px 0 rgb(0,0,0,.24),0 17px 50px 0 rgb(0,0,0,.19)';
});
inputEl.addEventListener('blur', () => {
    changeborderDiv.style.borderColor = 'rgb(209, 209, 209)';
    changeborderDiv.style.boxShadow = '';
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
    // 有历史记录时，移除默认欢迎语，改为回放真实历史
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
    const bottom = document.querySelector('.chat_bottom');
    if (bottom) bottom.scrollIntoView({ behavior: 'auto', block: 'end' });
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
    answerEl.innerHTML = '<span class="thinking-indicator"><span class="thinking-spinner"></span>正在思考...</span>';
}

// ===== 主发送流程 =====
let activeAbortController: AbortController | null = null;

function setGeneratingUI(isGenerating: boolean) {
    (document.getElementById('submit') as HTMLButtonElement).disabled = isGenerating;
    (document.getElementById('stop-generating') as HTMLElement).classList.toggle('is-hidden', !isGenerating);
}

function sendMessage() {
    const input = document.getElementById('input') as HTMLInputElement;
    const question = input.value.trim();
    if (question === '') return;

    // 首次发送后移除欢迎示例区
    document.getElementById('welcome-examples')?.remove();

    appendUserBubble(question);
    input.value = '';

    const { answerEl, citations, message } = appendBotBubble();
    showThinkingIndicator(answerEl);
    scrollToBottom();
    message.scrollIntoView({ behavior: 'smooth', block: 'end' });

    setGeneratingUI(true);
    streamAnswer(question, answerEl, citations).finally(() => setGeneratingUI(false));
}

function stopGenerating() {
    if (activeAbortController) {
        activeAbortController.abort();
    }
}

async function streamAnswer(query: string, answerEl: HTMLElement, citationsEl: HTMLElement) {
    activeAbortController = new AbortController();
    let fullText = '';
    let firstChunk = true;

    // rAF 节流: 避免每个 chunk 都触发 Markdown 解析 + DOM 重绘
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

    try {
        const response = await apiFetch('/graph/chat_stream', {
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

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            if (firstChunk) {
                answerEl.innerHTML = '';
                firstChunk = false;
            }
            fullText += decoder.decode(value, { stream: true });

            // 节流: 仅在无待执行 rAF 时调度新帧
            pendingText = fullText;
            if (rafId === null) {
                rafId = requestAnimationFrame(() => {
                    rafId = null;
                    flushRender();
                });
            }
        }

        // 流结束: 取消待执行 rAF 并做最终渲染
        cancelPendingRaf();
        flushRender();

        if (!fullText.trim()) {
            fullText = '我还不知道，请反馈给我吧';
            answerEl.innerHTML = renderMarkdown(fullText);
        }

        appendHistory('bot', fullText);
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
            streamAnswer(query, answerEl, citationsEl).finally(() => setGeneratingUI(false));
            setGeneratingUI(true);
            retryBtn.remove();
        });
        answerEl.innerHTML = renderMarkdown(fullText);
        answerEl.appendChild(retryBtn);
        appendHistory('bot', fullText);
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
        list.className = 'citations_list';
        nodes.forEach((node: { text: string }) => {
            const item = document.createElement('div');
            item.className = 'citation_item';
            const snippet = node.text.length > 200 ? node.text.slice(0, 200) + '…' : node.text;
            item.textContent = snippet;
            // 加复制按钮, 提升效率
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

// ===== 清空对话（带二次确认，避免误触丢失全部历史） =====
async function clearAllMessage() {
    if (!window.confirm('确定要清空当前对话吗？此操作不可恢复。')) {
        return;
    }
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    chatbox.innerHTML = '';
    clearHistory();
    try {
        await apiFetch('/graph/create', { method: 'POST' });
    } catch (e) {
        // 服务端重置失败不阻塞本地清空
    }
    appendWelcomeBubble();
}

// 欢迎气泡（含示例问题），初始化与清空后共用
function appendWelcomeBubble() {
    const { answerEl, content } = appendBotBubble({ persist: false });
    answerEl.innerHTML = renderMarkdown(WELCOME_MESSAGE);
    content.insertAdjacentHTML('beforeend', WELCOME_EXAMPLES_HTML);
}

// ===== 页面初始化 =====
window.addEventListener('DOMContentLoaded', () => {
    replayHistory();
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('.clear')?.addEventListener('click', clearAllMessage);
  document.getElementById('stop-generating')?.addEventListener('click', stopGenerating);
  document.getElementById('submit')?.addEventListener('click', sendMessage);

  // 示例问题点击: 填入并发送 (事件委托, 清空重建后依然生效)
  document.getElementById('chatbox')?.addEventListener('click', (e: Event) => {
    const target = e.target as HTMLElement;
    if (!target || !target.classList.contains('example_q')) return;
    const input = document.getElementById('input') as HTMLInputElement;
    input.value = target.textContent || '';
    // 隐藏欢迎区, 标记首次使用已开始
    const welcome = document.getElementById('welcome-examples');
    if (welcome) welcome.remove();
    sendMessage();
  });
});
