import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { showToast } from '../src/utils/toast';

describe('showToast', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="toast-container"></div>';
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('容器不存在时静默返回不抛错', () => {
    document.body.innerHTML = '';
    expect(() => showToast('hi')).not.toThrow();
  });

  it('默认类型 info，元素 class 含 toast-info 且文本为消息', () => {
    showToast('消息内容');
    const toast = document.querySelector('#toast-container .toast') as HTMLElement;
    expect(toast).not.toBeNull();
    expect(toast.className).toContain('toast-info');
    expect(toast.textContent).toBe('消息内容');
  });

  it('指定 type 时 class 含对应类型', () => {
    showToast('出错啦', 'error');
    const toast = document.querySelector('#toast-container .toast') as HTMLElement;
    expect(toast.className).toContain('toast-error');
  });

  it('50ms 后添加 show class，3000ms 后移除', () => {
    showToast('x');
    const toast = document.querySelector('#toast-container .toast') as HTMLElement;
    expect(toast.classList.contains('show')).toBe(false);
    vi.advanceTimersByTime(50);
    expect(toast.classList.contains('show')).toBe(true);
    vi.advanceTimersByTime(3000);
    expect(toast.classList.contains('show')).toBe(false);
  });

  it('完整动画结束后元素从 DOM 移除', () => {
    showToast('y');
    expect(document.querySelector('#toast-container .toast')).not.toBeNull();
    vi.advanceTimersByTime(50 + 3000 + 300);
    expect(document.querySelector('#toast-container .toast')).toBeNull();
  });
});
