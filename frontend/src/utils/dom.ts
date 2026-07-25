// ===== DOM 安全工具 =====

// 转义 HTML 特殊字符, 用于把不可信文本安全拼入 innerHTML。
// 优先建议直接使用 textContent; 当必须用 innerHTML 拼接时调用本函数。
export function escapeHtml(s: unknown): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}