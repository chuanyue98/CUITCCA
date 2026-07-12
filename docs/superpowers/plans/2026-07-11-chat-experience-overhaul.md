# Chat Experience Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the chat page from a stateless fake-typewriter demo into a real multi-turn, real-token-streaming assistant with Markdown rendering, visible source citations, and a conversation that survives a page reload.

**Architecture:** The backend already has a working multi-turn chat engine (`compose_graph_chat_egine` + `CondenseQuestionChatEngine`, session-scoped via cookie) and a real streaming endpoint (`/graph/chat_stream`) that the frontend has simply never used — `chat.js` calls the stateless `/graph/query` and fakes streaming with a `setTimeout` typewriter. This plan rewires the frontend onto `/graph/chat_stream`, reads the response body as a real `ReadableStream`, renders it as sanitized Markdown, and adds a lightweight citations panel backed by a small backend change to `/graph/chat_stream` (capture `source_nodes`, mirroring what `/graph/query_stream` already does). Conversation history is persisted client-side in `localStorage`; "clear conversation" resets both the UI and the server-side chat engine via the existing `/graph/create` endpoint.

**Tech Stack:** Vanilla JS (no build step, matching the existing frontend), `marked` 12.0.2 + `DOMPurify` 3.1.6 vendored locally (no CDN dependency at runtime), FastAPI `StreamingResponse` (already exists), `fetch` + `ReadableStream` for real token streaming.

## Global Constraints

- No build tooling may be introduced — the frontend stays plain HTML/CSS/JS served as static files, per the existing project structure.
- Do not touch `/index/*` authentication — explicitly out of scope for this round (project is pre-launch).
- Keep all existing CSS class names that Playwright specs assert on (`content_bot`, `content_man`, `content_bot_img`, `content_man_img`, `talk_content`, `chatbox`) unless a step explicitly says to rename and update the spec too.
- Vendored JS libraries live in `frontend/vendor/` and are committed to the repo (already downloaded: `frontend/vendor/marked.min.js`, `frontend/vendor/purify.min.js`).
- Every backend change must keep `tests/test_graph_router.py` passing; extend it, don't break it.

---

## File Structure

- Modify: `backend/app/router/graph.py` — capture `source_nodes` from `chat_stream` into the existing `_last_query_response` TTL cache.
- Modify: `frontend/index.html` — load vendored `marked`/`DOMPurify`, add a "stop generating" affordance, add a citations container per message, update header text.
- Modify: `frontend/chat.js` — replace fake-typewriter/query flow with real streaming, Markdown rendering, source citations, localStorage persistence, new flexbox message layout (no more `box_side` width hack).
- Modify: `frontend/style.css` — new flexbox message alignment, dark-mode variables, citations panel styles, updated clear-button icon, drop `box_side`/typing-cursor CSS that's no longer needed.
- Test: `tests/test_graph_router.py` — new test asserting `chat_stream` populates `_last_query_response`.

---

### Task 1: Backend — capture source nodes from chat_stream

**Files:**
- Modify: `backend/app/router/graph.py:73-84`
- Test: `tests/test_graph_router.py` (add near the existing `chat_stream` tests around line 218)

**Interfaces:**
- Produces: `_last_query_response` TTLCache now also populated by `POST /graph/chat_stream`, consumed unchanged by the existing `POST /graph/query_sources` endpoint (no signature change there).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph_router.py`, in the `# ── /graph/chat_stream ──` section, right after `test_chat_stream_uses_existing_engine`:

```python
    @patch('router.graph.compose_graph_chat_egine')
    def test_chat_stream_populates_query_sources(self, mock_compose):
        fake_engine = MagicMock()
        source_node = MagicMock()
        source_node.node.id_ = "n1"
        source_node.node.text = "cited text"
        source_node.score = 0.8

        async def mock_astream_chat(q):
            resp = MagicMock()
            resp.response_gen = iter(["hello"])
            resp.source_nodes = [source_node]
            return resp
        fake_engine.astream_chat = mock_astream_chat
        mock_compose.return_value = fake_engine

        self.client.post("/graph/chat_stream", data={"query": "hi"})
        response = self.client.post("/graph/query_sources")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["source_nodes"]), 1)
        self.assertEqual(data["source_nodes"][0]["id"], "n1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_router.py::GraphRouterTest::test_chat_stream_populates_query_sources -v`
Expected: FAIL — `query_sources` returns 400 `"please query first"` because `chat_stream` never wrote to `_last_query_response`.

- [ ] **Step 3: Implement**

In `backend/app/router/graph.py`, replace the `chat_graph_stream` function (lines 73-84):

```python
@graph_app.post("/chat_stream")
async def chat_graph_stream(request: Request, query: str = Form(max_length=5000)):
    client_id = _client_id(request)
    chat_engine = _graph_chat_engines.get(client_id)
    if chat_engine is None:
        chat_engine = compose_graph_chat_egine()
        _graph_chat_engines.set(client_id, chat_engine)
    query = query.strip()
    customer_logger.info(f"chat_stream: {query}")
    res = await chat_engine.astream_chat(query)
    customer_logger.info(f"res: {res}")
    _last_query_response.set(client_id, getattr(res, "source_nodes", None) or [])
    return StreamingResponse(res.response_gen, media_type="text/plain")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_router.py -v`
Expected: All tests in the file PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add backend/app/router/graph.py tests/test_graph_router.py
git commit -m "feat: capture source nodes from chat_stream for citations"
```

---

### Task 2: Load vendored Markdown/sanitizer libs and restructure index.html

**Files:**
- Modify: `frontend/index.html`

**Interfaces:**
- Produces: global `marked` and `DOMPurify` objects available to `chat.js`; new DOM hooks `#stop-generating` button and `.citations` container template consumed by Task 3.

- [ ] **Step 1: Update `frontend/index.html`**

Replace the `<head>` script area is unaffected; add vendor script tags before `chat.js`, change the header title text, and add a stop-generation affordance next to the send button. Replace lines 1-62 with:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="./icon.png" type="image/x-icon">
    <link rel="stylesheet" href="./style.css">
    <title>成信大校园助手</title>
</head>
<body>
    <div class="outline">
        <nav id="side_left" aria-label="主导航"></nav>
        <!-- 右边 -->
        <main class="side_right">
            <header class="headline">
                <div class="headline_hidemenu">
                    <button id="button">
                        <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                            <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
                        </svg>
                    </button>
                </div>
                <div class="headline_head">校园问答助手</div>
                <div class="share"></div>
            </header>
            <div class="talk_outline">
                <div class="talk_outlinein">
                    <div class="talk_content" id="chatbox" aria-live="polite" aria-label="对话记录">
                        <div class="message bot">
                            <div class="content_bot_img"></div>
                            <div class="content_bot">你好！我是成信大校园助手，你可以问我关于学校的任何问题，比如：学校有哪些社团？图书馆怎么借书？</div>
                        </div>
                    </div>
                    <div class="chat_bottom"></div>
                    <footer class="foot_fix">
                        <div class="chat_container">
                            <button class="clear" onclick="clearAllMessage()" title="清空对话" aria-label="清空对话">
                                <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-trash3" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                                    <path d="M6.5 1h3a.5.5 0 0 1 .5.5v1H6v-1a.5.5 0 0 1 .5-.5ZM11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3A1.5 1.5 0 0 0 5 1.5v1H2.506a.58.58 0 0 0-.01 0H1.5a.5.5 0 0 0 0 1h.538l.853 10.66A2 2 0 0 0 4.885 16h6.23a2 2 0 0 0 1.994-1.84l.853-10.66h.538a.5.5 0 0 0 0-1h-.995a.59.59 0 0 0-.01 0H11Zm1.958 1-.846 10.58a1 1 0 0 1-.997.92h-6.23a1 1 0 0 1-.997-.92L3.042 3.5h9.916Zm-7.487 1a.5.5 0 0 1 .528.47l.5 8.5a.5.5 0 0 1-.998.06L5 5.03a.5.5 0 0 1 .47-.53Zm5.058 0a.5.5 0 0 1 .47.53l-.5 8.5a.5.5 0 1 1-.998-.06l.5-8.5a.5.5 0 0 1 .528-.47ZM8 4.5a.5.5 0 0 1 .5.5v8a.5.5 0 0 1-1 0V5a.5.5 0 0 1 .5-.5Z"/>
                                </svg>
                            </button>
                            <div class="chat_talk_container" id="changeborder_div">
                                <div class="chat_textarea">
                                    <div class="textarea">
                                        <textarea name="" id="input" cols="10" rows="1" aria-label="输入问题" placeholder="输入你的问题..."></textarea>
                                    </div>
                                </div>
                                <button class="chat_talk_stop is-hidden" id="stop-generating" onclick="stopGenerating()" title="停止生成" aria-label="停止生成">■</button>
                                <button class="chat_talk_submit" id="submit" onclick="sendMessage()" aria-label="发送">&#10140</button>
                            </div>
                        </div>
                    </footer>
                </div>
            </div>
        </main>
    </div>

    <script src="./vendor/marked.min.js"></script>
    <script src="./vendor/purify.min.js"></script>
    <script src="./sidebar.js" data-active="index"></script>
    <script src="./chat.js"></script>
</body>
</html>
```

Note the welcome message and every future bot/user message now uses a flat `.message.bot` / `.message.user` structure (avatar + bubble as direct siblings, no `sender_*` spacer divs, no `box_side`) — this is intentional; Task 4 updates `chat.js`'s DOM-building code and Task 5 updates the CSS to match.

- [ ] **Step 2: Commit**

```bash
git add frontend/index.html
git commit -m "feat: restructure chat page markup for streaming and stop control"
```

---

### Task 3: Real token streaming with Markdown rendering

**Files:**
- Modify: `frontend/chat.js`

**Interfaces:**
- Consumes: `marked.parse(text)` and `DOMPurify.sanitize(html)` (globals from Task 2's vendored scripts); `POST /graph/chat_stream` (form-encoded `query=`, returns `text/plain` streamed body, existing endpoint enhanced in Task 1).
- Produces: `sendMessage()`, `stopGenerating()`, `clearAllMessage()` — same public function names the HTML `onclick` handlers already reference, so no HTML changes needed beyond Task 2.

- [ ] **Step 1: Replace `frontend/chat.js` in full**

```javascript
// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.js、marked.min.js、purify.min.js 已在上方加载

const HISTORY_KEY = 'cuitcca_chat_history_v1';
const HISTORY_MAX = 50;

// ===== 输入框事件 =====
const inputEl = document.getElementById('input');
inputEl.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        document.getElementById('submit').click();
    }
});

const changeborderDiv = document.getElementById('changeborder_div');
inputEl.addEventListener('focus', () => {
    changeborderDiv.style.borderColor = 'rgb(151, 204, 242)';
    changeborderDiv.style.boxShadow = '0 12px 16px 0 rgb(0,0,0,.24),0 17px 50px 0 rgb(0,0,0,.19)';
});
inputEl.addEventListener('blur', () => {
    changeborderDiv.style.borderColor = 'rgb(209, 209, 209)';
    changeborderDiv.style.boxShadow = '';
});

// ===== Markdown 渲染 =====
function renderMarkdown(rawText) {
    const html = marked.parse(rawText || '', { breaks: true });
    return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
}

// ===== 对话持久化 (localStorage) =====
function loadHistory() {
    try {
        const raw = localStorage.getItem(HISTORY_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

function saveHistory(history) {
    const trimmed = history.slice(-HISTORY_MAX);
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
    } catch (e) {
        // localStorage 不可用（隐私模式等）时静默跳过持久化
    }
}

function appendHistory(role, content) {
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
    const chatbox = document.getElementById('chatbox');
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
function appendUserBubble(text, { persist = true } = {}) {
    const chatbox = document.getElementById('chatbox');
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

function appendBotBubble({ persist = true } = {}) {
    const chatbox = document.getElementById('chatbox');
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
function showThinkingIndicator(answerEl) {
    answerEl.innerHTML = '<span class="thinking-indicator"><span class="thinking-spinner"></span>正在思考...</span>';
}

// ===== 主发送流程 =====
let activeAbortController = null;

function setGeneratingUI(isGenerating) {
    document.getElementById('submit').disabled = isGenerating;
    document.getElementById('stop-generating').classList.toggle('is-hidden', !isGenerating);
}

function sendMessage() {
    const input = document.getElementById('input');
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

async function streamAnswer(query, answerEl, citationsEl) {
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
        if (error.name === 'AbortError') {
            if (fullText) appendHistory('bot', fullText);
            return;
        }
        console.error('请求失败:', error);
        fullText = fullText || ('请求失败: ' + error.message);
        answerEl.innerHTML = renderMarkdown(fullText);
        appendHistory('bot', fullText);
    } finally {
        activeAbortController = null;
    }
}

async function loadCitations(citationsEl) {
    try {
        const response = await fetch('/graph/query_sources', { method: 'POST' });
        if (!response.ok) return;
        const data = await response.json();
        const nodes = (data.source_nodes || []).filter(n => n && n.text);
        if (nodes.length === 0) return;

        citationsEl.innerHTML = '';
        const toggle = document.createElement('button');
        toggle.className = 'citations_toggle';
        toggle.type = 'button';
        toggle.textContent = `参考来源 (${nodes.length})`;
        const list = document.createElement('div');
        list.className = 'citations_list is-hidden';
        nodes.forEach(node => {
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
    const chatbox = document.getElementById('chatbox');
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
```

- [ ] **Step 2: Manual smoke test**

Start the backend (`cd backend && uv run python app/main.py`), open `http://localhost:8000/web/`, send a message, and confirm: text streams in progressively (not all at once), Markdown (e.g. `**bold**`, lists) renders correctly, a "参考来源" toggle appears if the query hit indexed content, reloading the page replays the conversation, and "清空对话" empties both the UI and `localStorage['cuitcca_chat_history_v1']`.

- [ ] **Step 3: Commit**

```bash
git add frontend/chat.js
git commit -m "feat: real streaming chat with markdown rendering, citations, and history persistence"
```

---

### Task 4: CSS — flexbox message layout, citations panel, dark mode, clear-button icon

**Files:**
- Modify: `frontend/style.css`

**Interfaces:**
- Consumes: `.message.user` / `.message.bot` structure from Task 2/3 (avatar + bubble as flex children, no `sender_*`/`box_side` elements).
- Produces: CSS classes `.citations`, `.citations_toggle`, `.citations_list`, `.citation_item`, `.chat_talk_stop` consumed by `chat.js` from Task 3.

- [ ] **Step 1: Replace the chat message rules**

In `frontend/style.css`, replace the block from `.message {` through `.replycontent { display: inline; }` (lines 487-540) with:

```css
.message {
    width: 100%;
    display: flex;
    align-items: flex-end;
    gap: 10px;
    padding: 6px 10px;
}
.message.user { justify-content: flex-end; }
.message.bot { justify-content: flex-start; }

.message .content_man_img, .message .content_bot_img {
    min-width: 30px;
    width: 30px;
    height: 30px;
    border-radius: 30px;
    flex-shrink: 0;
    box-shadow: 0 2px 20px rgba(157, 157, 157, 0.5);
}
.message .content_man_img {
    background-repeat: no-repeat;
    background-size: 40px;
    background-position: -5px 0px;
    background-image: url("./user.gif");
}
.message .content_bot_img {
    background-repeat: no-repeat;
    background-size: 30px;
    background-position: 1px 5px;
    background-image: url("./logo.png");
}
.message .content_man, .message .content_bot {
    min-width: 20px;
    max-width: min(680px, 80%);
    padding: 10px 14px;
    overflow-x: auto;
    word-wrap: break-word;
    border-radius: 14px;
    box-shadow: 0 2px 20px rgba(157, 157, 157, 0.15);
    line-height: 1.6;
}
.message .content_man { background-color: var(--primary-bg); }
.message .content_bot { background-color: var(--surface-alt); }
.message .content_bot p, .message .content_man p { margin-bottom: 6px; }
.message .content_bot p:last-child, .message .content_man p:last-child { margin-bottom: 0; }
.message .content_bot ul, .message .content_bot ol { margin: 4px 0 4px 20px; }
.message .content_bot code {
    background: rgba(0,0,0,0.06);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 0.9em;
}
.message .content_bot pre {
    background: rgba(0,0,0,0.06);
    padding: 10px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 6px 0;
}

.chat_bottom { width: 100%; height: 40px; }
.talk_content { max-width: 900px; margin: 0 auto; width: 100%; }

#chatbox { display: flex; flex-direction: column; gap: 4px; padding: 10px 0; }

/* 引用来源面板 */
.citations { margin-top: 8px; }
.citations_toggle {
    background: none;
    border: 1px solid rgba(25, 84, 142, 0.25);
    color: var(--primary);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    cursor: pointer;
}
.citations_toggle:hover { background: var(--primary-bg); }
.citations_list { margin-top: 6px; display: flex; flex-direction: column; gap: 6px; }
.citation_item {
    font-size: 12px;
    color: var(--text-secondary);
    background: rgba(0,0,0,0.03);
    border-left: 2px solid var(--primary);
    padding: 6px 10px;
    border-radius: 4px;
    line-height: 1.5;
}
```

- [ ] **Step 2: Add the stop-generation button style and remove obsolete cursor/typing rules**

Replace the `.cursor { ... }` / `@keyframes blink { ... }` block (now unused — real streaming has no blinking-cursor simulation) and the trailing `.thinking-indicator` / `.is-hidden` / `.content_bot.typing` block at the end of the file with:

```css
.chat_talk_stop {
    margin: 3px 6px 6px 0;
    min-width: 40px;
    height: 40px;
    background-color: #fff;
    border: 2px solid rgb(209, 209, 209);
    font-size: 16px;
    border-radius: 30px;
    color: var(--danger);
    cursor: pointer;
    transition: opacity 0.2s;
}
.chat_talk_stop:hover { opacity: 0.85; }

.thinking-indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
    font-style: italic;
}
.thinking-spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid var(--primary-bg);
    border-top: 2px solid var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
}
.is-hidden { display: none !important; }
```

Also remove the now-dead `resizeBox`-related selectors — search the file for `.box_side` and delete the rule `.message .box_side { width: 0px; height: 10px; }` (it no longer has a matching element after Task 3).

- [ ] **Step 3: Add dark mode variables**

At the top of `frontend/style.css`, extend the `:root` block (lines 4-22) with two new variables and add a `prefers-color-scheme: dark` override right after it:

```css
:root {
  --primary: rgb(25, 84, 142);
  --primary-light: rgb(44, 114, 184);
  --primary-bg: rgba(25, 84, 142, 0.1);
  --success: #52c41a;
  --danger: #ff4d4f;
  --warning: #fa8c16;
  --info: #1890ff;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --radius-pill: 30px;
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg: 0 8px 24px rgba(31, 38, 135, 0.1);
  --text-primary: #333;
  --text-secondary: #666;
  --text-tertiary: #999;
  --bg-gradient-start: #f4f6fc;
  --bg-gradient-end: #eef2fa;
  --surface: #ffffff;
  --surface-alt: rgb(242, 242, 242);
}

@media (prefers-color-scheme: dark) {
  :root {
    --primary: rgb(94, 156, 211);
    --primary-light: rgb(120, 176, 224);
    --primary-bg: rgba(94, 156, 211, 0.15);
    --text-primary: #e4e6eb;
    --text-secondary: #b0b3b8;
    --text-tertiary: #8a8d91;
    --bg-gradient-start: #16181c;
    --bg-gradient-end: #0e0f11;
    --surface: #1f2125;
    --surface-alt: #2a2d32;
  }
  body, html { background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%); }
  #side_left, .headline, .panel_right, .node_card, .glass_card, .guide_card { background-color: var(--surface) !important; }
  .foot_fix { background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%); }
  .chat_talk_container, .clear, .chat_talk_stop { background-color: var(--surface); color: var(--text-primary); }
  textarea, .node_editor, .summary_textarea, .form_group input, .form_group textarea, .index_select, .new_index_input, .node_search_input { background-color: var(--surface); color: var(--text-primary); }
}
```

Then replace the two literal gradient declarations that currently hardcode the light colors so they pick up the variables — in `body, html {` (originally line 33-38) change `background: linear-gradient(135deg, #f4f6fc 0%, #eef2fa 100%);` to `background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);`, and make the same substitution in `.foot_fix {` (originally line 394-402).

- [ ] **Step 4: Manual verification**

Reload `http://localhost:8000/web/` with the OS set to dark mode (or DevTools → Rendering → "Emulate CSS prefers-color-scheme: dark") and confirm text stays readable and no white-on-white / black-on-black regions appear on the chat, manage, feedback, and guide pages.

- [ ] **Step 5: Commit**

```bash
git add frontend/style.css
git commit -m "style: flexbox chat layout, citations panel, dark mode, streaming controls"
```

---

### Task 5: Reconcile Playwright chat specs with the new UI

**Files:**
- Modify (if needed): `tests/playwright/test-index.spec.ts`, `tests/playwright/test-chat-uiux-final.spec.ts`

**Interfaces:**
- Consumes: the running app at `http://localhost:8000` (per `tests/playwright/playwright.config.ts` `baseURL`).

- [ ] **Step 1: Start the backend and run the two specs that touch the chat page**

```bash
cd backend && uv run python app/main.py &
cd tests/playwright && npx playwright test test-index.spec.ts test-chat-uiux-final.spec.ts --reporter=list
```

- [ ] **Step 2: Fix any failing assertions caused by intentional changes**

Both specs were confirmed (during planning) to assert against `.content_bot` / `.content_bot_img` / `page.title()` — none of which changed. If a run surfaces a failure, it will be because a spec asserts on now-removed markup (`.sender_bot`, `.box_side`, `.cursor`, the old Slack clear-icon `class="bi-slack"`). Update only the specific failing assertion to match the new markup from Task 2-4; do not rewrite unrelated passing assertions.

- [ ] **Step 3: Stop the background server and commit any spec fixes**

```bash
kill %1
git add tests/playwright/*.spec.ts
git commit -m "test: reconcile playwright chat specs with streaming UI" --allow-empty
```

(`--allow-empty` is safe here since Step 1-2 may find nothing to fix; drop the flag if there are real changes staged.)

---

## Self-Review

**Spec coverage:**
- Item #2 (real multi-turn) → Task 1 wires citation capture onto the already-multi-turn `chat_stream`; Task 3 switches the frontend to call it. ✓
- Item #4 (real streaming + citations) → Task 3 (`streamAnswer`, `loadCitations`) + Task 1 (backend capture). ✓
- Item #7 (Markdown rendering) → Task 2 (vendor libs) + Task 3 (`renderMarkdown`). ✓
- Item #8 (conversation persistence) → Task 3 (`loadHistory`/`saveHistory`/`replayHistory`). ✓
- Item #9 UI details (clear-button icon, `box_side` hack removal, dark mode, "测试版" title) → Task 2 (icon, header text) + Task 4 (layout CSS, dark mode). ✓

**Placeholder scan:** No TBD/TODO markers; every step has literal code or an exact command.

**Type/name consistency:** `sendMessage`, `stopGenerating`, `clearAllMessage` are the exact `onclick` handler names used in Task 2's HTML and defined in Task 3's `chat.js`. `_last_query_response` is the exact cache name already used by `/graph/query_sources` in `backend/app/router/graph.py`. `renderMarkdown`, `appendUserBubble`, `appendBotBubble`, `loadCitations` are defined once in Task 3 and not referenced with different names elsewhere.
