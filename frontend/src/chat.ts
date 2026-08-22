// ===== 聊天页面逻辑 (index.html) =====
// 依赖: sidebar.ts、marked.min.js、purify.min.js 已在上方加载
//
// 本文件只是入口/装配层，实现按职责拆在 src/chat/ 下——
//   inputBar.ts     输入框行为（自适应高度、Enter 发送、焦点描边）
//   dom.ts          气泡构建、Markdown 渲染、滚动（纯 DOM，无副作用依赖）
//   history.ts      localStorage 对话持久化与回放
//   conversation.ts 发送主流程、NDJSON 流式解析、工具轨迹、建议、反馈
//   citations.ts    参考来源列表

import './chat/inputBar';
import { sendMessage, stopGenerating } from './chat/conversation';
import { clearHistory, replayHistory } from './chat/history';
import { apiFetch } from './utils/api';

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
