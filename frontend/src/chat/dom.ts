// ===== 聊天 DOM 基元：Markdown 渲染、气泡构建、滚动、加载态 =====
// 纯 DOM 构建，不做持久化——写不写 localStorage 由调用方（conversation/
// history）决定，避免本模块反向依赖 history 形成循环。

export function renderMarkdown(rawText: string): string {
    const html = marked.parse(rawText || '', { breaks: true });
    return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
}

export function scrollToBottom() {
    // 真正装消息、可滚动的容器是 .talk_content（style.css 里 overflow-y:
    // auto 的那个），不是 .chat_bottom——.chat_bottom 是它的兄弟节点，待在
    // .talk_outline 这个外层容器里，可滚动余量恒为 0，scrollIntoView 在它
    // 身上是空操作（实测 12 轮对话后 scrollTop 停在 0，可滚动余量 1209px）。
    const scroller = document.querySelector('.talk_content') as HTMLElement | null;
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
}

export function appendUserBubble(text: string): { message: HTMLElement; content: HTMLElement } {
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
    return { message, content };
}

export function appendBotBubble(): { message: HTMLElement; content: HTMLElement; answerEl: HTMLElement; citations: HTMLElement } {
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
    return { message, content, answerEl, citations };
}

export function showThinkingIndicator(answerEl: HTMLElement) {
    // 省略号由 .thinking-dots::after 的 CSS 动画逐段点亮，比静态"..."更有"正在
    // 打字"的临场感。
    answerEl.innerHTML = '<span class="thinking-indicator"><span class="thinking-spinner"></span>正在思考<span class="thinking-dots"></span></span>';
}
