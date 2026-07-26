// ===== Toast 通知工具 =====
// 依赖页面中存在 <div id="toast-container"></div> 容器。
// manage.html / feed_back.html 均已提供该容器。

export type ToastType = 'info' | 'success' | 'error' | 'warning';

// 不同类型的停留时长 (毫秒)
const DURATION: Record<ToastType, number> = {
  info: 3000,
  success: 2500, // 成功反馈快进快出
  error: 6000,   // 错误需用户读完
  warning: 4500,
};

export function showToast(message: string, type: ToastType | string = 'info'): void {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toastType = (['info', 'success', 'error', 'warning'].includes(type) ? type : 'info') as ToastType;
  const toast = document.createElement('div');
  toast.className = `toast toast-${toastType}`;
  toast.innerText = message;
  container.appendChild(toast);

  // 错误/警告: 加手动关闭按钮, 避免被覆盖
  if (toastType === 'error' || toastType === 'warning') {
    const closeBtn = document.createElement('span');
    closeBtn.className = 'toast_close';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('role', 'button');
    closeBtn.setAttribute('aria-label', '关闭');
    toast.appendChild(closeBtn);
    const dismiss = () => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    };
    closeBtn.addEventListener('click', dismiss);
  }

  // 触发淡入动画
  setTimeout(() => toast.classList.add('show'), 50);

  // 类型对应时长后自动移除
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, DURATION[toastType]);
}
