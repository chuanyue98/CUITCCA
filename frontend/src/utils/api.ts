// ===== 统一 API 请求封装 (附带鉴权头) =====
// 约定: 后端 require_configured_api_key 读取 Authorization: Bearer <CUITCCA_API_KEY>。
// 本地 localStorage key 为 cuitcca_api_key; 未配置时不附加 Authorization 头,
// 由后端依据是否配置 CUITCCA_API_KEY 决定放行或拒绝。

const API_KEY_STORAGE = 'cuitcca_api_key';

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) || '';
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE);
}

// 监听 401 事件: 由 sidebar.ts 注册回调, 弹出"设置访问密钥"对话框。
let onUnauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(handler: () => void): void {
  onUnauthorizedHandler = handler;
}

// 触发 401 事件 (供测试或外部调用)
export function triggerUnauthorized(): void {
  if (onUnauthorizedHandler) onUnauthorizedHandler();
}

// 统一 fetch 封装: 自动附加 Bearer 鉴权头 (仅当本地已保存 key 且调用方未显式设置 Authorization 时)。
// 流式响应 (response.body.getReader()) 同样适用, 本函数仅包一层 headers。
// 401 时触发 onUnauthorized 回调, 让 sidebar.ts 引导用户设置密钥。
export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const key = getApiKey();
  const headers = new Headers(init.headers || {});
  if (key && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${key}`);
  }
  const response = await fetch(input, { ...init, headers });
  // 拦截 401: 引导用户设置访问密钥（仅触发一次/会话, 避免雪崩）
  if (response.status === 401 && onUnauthorizedHandler) {
    // 防抖: 同一会话内 3 秒内只触发一次
    if (!sessionStorage.getItem('cuitcca_401_prompted')) {
      sessionStorage.setItem('cuitcca_401_prompted', '1');
      onUnauthorizedHandler();
      setTimeout(() => sessionStorage.removeItem('cuitcca_401_prompted'), 3000);
    }
  }
  return response;
}