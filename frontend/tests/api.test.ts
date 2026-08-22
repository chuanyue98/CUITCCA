import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, clearApiKey, getApiKey, setApiKey } from '../src/utils/api';

describe('API key 读写 localStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('未配置时 getApiKey 返回空字符串', () => {
    expect(getApiKey()).toBe('');
  });

  it('setApiKey 写入后可由 getApiKey 读回', () => {
    setApiKey('my-secret');
    expect(getApiKey()).toBe('my-secret');
    expect(localStorage.getItem('cuitcca_api_key')).toBe('my-secret');
  });

  it('clearApiKey 后 getApiKey 返回空且 localStorage 无残留', () => {
    setApiKey('tmp');
    clearApiKey();
    expect(getApiKey()).toBe('');
    expect(localStorage.getItem('cuitcca_api_key')).toBeNull();
  });
});

describe('apiFetch 鉴权头附加逻辑', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('无 key 时不附加 Authorization 头', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok'));
    await apiFetch('/graph/query');
    expect(spy).toHaveBeenCalledOnce();
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).has('Authorization')).toBe(false);
  });

  it('有 key 时附加 Authorization Bearer 头', async () => {
    setApiKey('abc123');
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok'));
    await apiFetch('/graph/query');
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer abc123');
  });

  it('不覆盖调用方显式设置的 Authorization 头', async () => {
    setApiKey('abc123');
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok'));
    await apiFetch('/graph/query', { headers: { Authorization: 'Bearer custom' } });
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer custom');
  });

  it('透传 method/body 等其它 init 字段', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok'));
    await apiFetch('/x', { method: 'POST', body: 'q=1' });
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBe('q=1');
  });

  it('fetch 抛错时 apiFetch 同步向上抛出', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));
    await expect(apiFetch('/x')).rejects.toThrow('network down');
  });
});
