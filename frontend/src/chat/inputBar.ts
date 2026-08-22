// ===== 输入框行为：自适应高度 / 窄屏 placeholder / Enter 发送 / 焦点描边 =====

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
