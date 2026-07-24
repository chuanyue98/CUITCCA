// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.ts、marked.min.js、purify.min.js 已在上方加载

const HISTORY_KEY = 'cuitcca_chat_history_v1';
const HISTORY_MAX = 50;

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

    try {
        const response = await fetch('/graph/chat_stream', {
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
            answerEl.innerHTML = renderMarkdown(fullText);
            scrollToBottom();
        }

        if (!fullText.trim()) {
            fullText = '我还不知道，请反馈给我吧';
            answerEl.innerHTML = renderMarkdown(fullText);
        }

        appendHistory('bot', fullText);
        await loadCitations(citationsEl);
    } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
            if (fullText) {
                appendHistory('bot', fullText);
            } else {
                answerEl.innerHTML = renderMarkdown('*已停止生成*');
            }
            return;
        }
        console.error('请求失败:', error);
        fullText = fullText || ('请求失败: ' + (error instanceof Error ? error.message : String(error)));
        answerEl.innerHTML = renderMarkdown(fullText);
        appendHistory('bot', fullText);
    } finally {
        activeAbortController = null;
    }
}

async function loadCitations(citationsEl: HTMLElement) {
    try {
        const response = await fetch('/graph/query_sources', { method: 'POST' });
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
        nodes.forEach((node: { text: string }) => {
            const item = document.createElement('div');
            item.className = 'citation_item';
            const snippet = node.text.length > 200 ? node.text.slice(0, 200) + '…' : node.text;
            item.textContent = snippet;
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
async function clearAllMessage() {
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    chatbox.innerHTML = '';
    clearHistory();
    try {
        await fetch('/graph/create', { method: 'POST' });
    } catch (e) {
        // 服务端重置失败不阻塞本地清空
    }
    const { answerEl } = appendBotBubble({ persist: false });
    answerEl.innerHTML = renderMarkdown('你好！我是成信大校园助手，你可以问我关于学校的任何问题，比如：学校有哪些社团？图书馆怎么借书？');
}

// ===== 页面初始化 =====
window.addEventListener('DOMContentLoaded', () => {
    replayHistory();
});
