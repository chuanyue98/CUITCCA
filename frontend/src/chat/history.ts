// ===== 对话持久化 (localStorage) 与历史回放 =====

import { appendBotBubble, appendUserBubble, renderMarkdown, scrollToBottom } from './dom';

const HISTORY_KEY = 'cuitcca_chat_history_v1';
const HISTORY_MAX = 50;

export function loadHistory(): Array<{ role: string; content: string; ts: number }> {
    try {
        const raw = localStorage.getItem(HISTORY_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

export function saveHistory(history: Array<{ role: string; content: string; ts: number }>) {
    const trimmed = history.slice(-HISTORY_MAX);
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
    } catch (e) {
        // localStorage 不可用（隐私模式等）时静默跳过持久化
    }
}

export function appendHistory(role: string, content: string) {
    const history = loadHistory();
    history.push({ role, content, ts: Date.now() });
    saveHistory(history);
}

export function clearHistory() {
    try {
        localStorage.removeItem(HISTORY_KEY);
    } catch (e) {
        // 忽略
    }
}

export function replayHistory() {
    const history = loadHistory();
    const chatbox = document.getElementById('chatbox') as HTMLElement;
    if (history.length === 0) return;
    // 有历史记录时，移除默认欢迎语与首屏引导，改为回放真实历史
    chatbox.innerHTML = '';
    history.forEach(entry => {
        if (entry.role === 'user') {
            appendUserBubble(entry.content);
        } else {
            const { answerEl } = appendBotBubble();
            answerEl.innerHTML = renderMarkdown(entry.content);
        }
    });
    scrollToBottom();
}
