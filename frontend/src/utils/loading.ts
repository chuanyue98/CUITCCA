// 全局加载遮罩控制（manage 等多步骤操作页面共用）

export function showLoading(text = '正在处理中...') {
    const overlay = document.getElementById('loading-overlay') as HTMLElement;
    const textEl = overlay.querySelector('.loading-text') as HTMLElement | null;
    if (textEl) textEl.innerText = text;
    overlay.style.opacity = '1';
    overlay.style.visibility = 'visible';
}

export function hideLoading() {
    const overlay = document.getElementById('loading-overlay') as HTMLElement;
    overlay.style.opacity = '0';
    overlay.style.visibility = 'hidden';
}
