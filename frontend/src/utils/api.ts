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

// 统一 fetch 封装: 自动附加 Bearer 鉴权头 (仅当本地已保存 key 且调用方未显式设置 Authorization 时)。
// 流式响应 (response.body.getReader()) 同样适用, 本函数仅包一层 headers。
export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const key = getApiKey();
  const headers = new Headers(init.headers || {});
  if (key && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${key}`);
  }
  return fetch(input, { ...init, headers });
}