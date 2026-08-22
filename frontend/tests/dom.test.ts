import { describe, expect, it } from 'vitest';
import { escapeHtml } from '../src/utils/dom';

describe('escapeHtml', () => {
  it('转义 < > & " 五个特殊字符', () => {
    expect(escapeHtml('<a href="x">Tom & Jerry</a>')).toBe(
      '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&lt;/a&gt;',
    );
  });

  it("单引号转义为 &#39;", () => {
    expect(escapeHtml("it's")).toBe('it&#39;s');
  });

  it('& 必须最先转义，避免二次转义', () => {
    expect(escapeHtml('&lt;')).toBe('&amp;lt;');
  });

  it('非字符串输入先 String() 再转义', () => {
    expect(escapeHtml(123)).toBe('123');
    expect(escapeHtml(null)).toBe('null');
    expect(escapeHtml(undefined)).toBe('undefined');
  });

  it('空字符串原样返回', () => {
    expect(escapeHtml('')).toBe('');
  });

  it('无特殊字符时原样返回（含中文）', () => {
    expect(escapeHtml('hello 你好')).toBe('hello 你好');
  });
});
