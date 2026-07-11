// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.js 已在上方加载

// ===== 输入框事件 =====
const inputEl = document.getElementById('input');
inputEl.addEventListener('keydown', function(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        document.getElementById("submit").click();
    }
});

const changeborderDiv = document.getElementById('changeborder_div');
inputEl.addEventListener('focus', () => {
    changeborderDiv.style.borderColor = 'rgb(151, 204, 242)';
    changeborderDiv.style.boxShadow = "0 12px 16px 0 rgb(0,0,0,.24),0 17px 50px 0 rgb(0,0,0,.19)";
});
inputEl.addEventListener('blur', () => {
    changeborderDiv.style.borderColor = 'rgb(209, 209, 209)';
    changeborderDiv.style.boxShadow = '';
});

// ===== 工具函数 =====
function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function escapeHTML(str) {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/[&<>'"]/g,
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}

function resizeBox(box) {
    var width = window.innerWidth > 1300 ? window.innerWidth - 1300 : 0;
    box.style.width = width + "px";
}

window.addEventListener("resize", function() {
    document.querySelectorAll(".box_side").forEach(function(box) {
        resizeBox(box);
    });
});

// ===== 聊天逻辑 =====
function sendMessage() {
    const input = document.getElementById("input");
    const chatbox = document.getElementById("chatbox");
    const question = input.value;

    if (input.value.trim() === "") return;

    const message = document.createElement("div");
    const sender = document.createElement("div");
    const content = document.createElement("div");
    const img = document.createElement("div");
    const box_side = document.createElement("div");

    content.textContent = input.value;
    message.classList.add("message");
    sender.classList.add("sender_man");
    content.classList.add("content_man");
    img.classList.add("content_man_img");
    box_side.classList.add("box_side");
    message.appendChild(sender);
    message.appendChild(content);
    message.appendChild(img);
    message.appendChild(box_side);
    chatbox.appendChild(message);
    resizeBox(box_side);
    input.value = "";

    const reply = document.createElement("div");
    const replySender = document.createElement("div");
    const replyContent = document.createElement("div");
    const replyImg = document.createElement("div");
    const replybox_side = document.createElement("div");

    reply.classList.add("message");
    replySender.classList.add("sender_bot");
    replyContent.classList.add("content_bot");
    replyImg.classList.add("content_bot_img");
    replybox_side.classList.add("box_side");

    const replyId = uuid();
    replyContent.setAttribute("id", replyId);

    const replyContent_Answer = document.createElement("div");
    const content_id = uuid();
    replyContent_Answer.setAttribute("id", content_id);
    replyContent_Answer.classList.add("replycontent");
    replyContent.appendChild(replyContent_Answer);

    const cursor = document.createElement("span");
    cursor.classList.add("cursor");
    cursor.setAttribute("id", "cursor");
    replyContent.appendChild(cursor);

    reply.appendChild(replybox_side);
    reply.appendChild(replyImg);
    reply.appendChild(replyContent);
    reply.appendChild(replySender);
    chatbox.appendChild(reply);
    resizeBox(replybox_side);

    document.getElementById(replyId).scrollIntoView({ behavior: "smooth", inline: "nearest" });

    // 加载态: 发送消息后、收到回复前显示 "正在思考..."
    showThinkingIndicator(replyContent_Answer, cursor);

    // 跳过按钮: 点击回复区域可立即显示完整文本
    replyContent.addEventListener('click', () => {
        skipTyping(content_id);
    });

    document.getElementById("submit").disabled = true;
    sendQuery(question, content_id);
}

// 显示 "正在思考..." 加载态
function showThinkingIndicator(answerEl, cursorEl) {
    if (cursorEl) cursorEl.classList.add('is-hidden');
    answerEl.innerHTML = '<span class="thinking-indicator"><span class="thinking-spinner"></span>正在思考...</span>';
}

// 清除加载态
function clearThinkingIndicator(answerEl, cursorEl) {
    if (cursorEl) cursorEl.classList.remove('is-hidden');
    answerEl.innerHTML = '';
}

async function sendQuery(query, content_id) {
    try {
        const response = await fetch('/graph/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'query=' + encodeURIComponent(query)
        });

        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }

        const data = await response.json();
        var answer = data.response ? data.response.trim() : "未找到有效的回答";
        answer = escapeHTML(answer);

        // 收到回复，清除加载态并开始打字
        const cursorEl = document.getElementById("cursor");
        clearThinkingIndicator(document.getElementById(content_id), cursorEl);

        typeText(content_id, answer, 0, "");
    } catch (error) {
        console.error("请求失败:", error);
        const cursorEl = document.getElementById("cursor");
        clearThinkingIndicator(document.getElementById(content_id), cursorEl);
        typeText(content_id, "请求失败: " + error.message, 0, "");
    } finally {
        document.getElementById("submit").disabled = false;
    }
}

function clearAllMessage() {
    var chatbox = document.getElementById('chatbox');
    while (chatbox.firstChild) {
        chatbox.removeChild(chatbox.firstChild);
    }
}

// ===== 打字机效果 (requestAnimationFrame 版本) =====
// 记录当前正在进行的打字动画，便于跳过
const typingAnimations = {};

function typeText(name, givenText, currentIndex, currentHTML) {
    const outputElement = document.getElementById(name);
    if (!outputElement || givenText.length === 0) return;

    // 标记回复气泡为打字中 (可点击跳过)
    const bubble = outputElement.closest('.content_bot');
    if (bubble) bubble.classList.add('typing');

    // 初始化或更新动画状态
    typingAnimations[name] = {
        fullText: givenText,
        index: currentIndex,
        html: currentHTML,
        element: outputElement,
        bubble: bubble,
        rafId: null,
        lastTime: 0
    };

    const state = typingAnimations[name];

    function tick(timestamp) {
        if (!state.lastTime) state.lastTime = timestamp;
        // 每 30ms 推进一个字符，保持与原版节奏一致
        if (timestamp - state.lastTime >= 30) {
            state.lastTime = timestamp;
            advanceOneChar(state);
            state.element.innerHTML = state.html;
        }
        if (state.index < state.fullText.length) {
            state.rafId = requestAnimationFrame(tick);
        } else {
            finishTyping(name);
        }
    }
    state.rafId = requestAnimationFrame(tick);
}

// 推进一个字符 (保留原版转义/换行/缩进逻辑)
function advanceOneChar(state) {
    const currentChar = state.fullText.charAt(state.index);
    const nextChar = state.fullText.charAt(state.index + 1);

    if (currentChar === "<") {
        const closingTagIndex = state.fullText.indexOf(">", state.index);
        state.html += state.fullText.slice(state.index, closingTagIndex + 1);
        state.index = closingTagIndex + 1;
    } else if (currentChar === "&") {
        const closingSemicolonIndex = state.fullText.indexOf(";", state.index);
        if (closingSemicolonIndex !== -1 && closingSemicolonIndex - state.index < 10) {
            state.html += state.fullText.slice(state.index, closingSemicolonIndex + 1);
            state.index = closingSemicolonIndex + 1;
        } else {
            state.html += currentChar;
            state.index++;
        }
    } else if (currentChar === "\\" && nextChar === "n" && state.index > 5) {
        state.html += "<br>";
        state.index += 2;
    } else if (currentChar === "\\" && nextChar === "n" && state.index <= 5) {
        state.index += 2;
    } else if (currentChar === "\"") {
        state.html += "&nbsp;&nbsp;&nbsp;&nbsp;";
        state.index++;
    } else {
        state.html += currentChar;
        state.index++;
    }
}

// 正常结束打字
function finishTyping(name) {
    const state = typingAnimations[name];
    if (!state) return;
    if (state.rafId) cancelAnimationFrame(state.rafId);
    state.element.innerHTML = state.html;
    if (state.bubble) state.bubble.classList.remove('typing');
    const cursorElement = document.getElementById("cursor");
    if (cursorElement) {
        cursorElement.classList.remove("cursor");
        cursorElement.setAttribute("id", uuid());
    }
    delete typingAnimations[name];
}

// 跳过动画: 立即显示完整文本
function skipTyping(name) {
    const state = typingAnimations[name];
    if (!state) return;
    if (state.rafId) cancelAnimationFrame(state.rafId);
    // 快速推进剩余字符
    while (state.index < state.fullText.length) {
        advanceOneChar(state);
    }
    state.element.innerHTML = state.html;
    finishTyping(name);
}
