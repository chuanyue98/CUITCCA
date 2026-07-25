// ===== Toast 通知工具 =====
// 依赖页面中存在 <div id="toast-container"></div> 容器。
// manage.html / feed_back.html 均已提供该容器。

export function showToast(message: string, type: string = 'info'): void {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerText = message;
  container.appendChild(toast);

  // 触发淡入动画
  setTimeout(() => toast.classList.add('show'), 50);

  // 3 秒后移除
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}