import { beforeEach, describe, expect, it } from 'vitest';
import { applyProbeResult, buildSavePayload, fillFormFromConfig } from '../src/config';

function setupDom() {
  document.body.innerHTML = `
    <input id="llm-base" value="" />
    <input id="llm-key" value="" placeholder="" autocomplete="new-password" />
    <span id="llm-key-hint"></span>
    <input id="llm-model" value="" list="llm-model-list" />
    <datalist id="llm-model-list"></datalist>
    <div id="probe-result" hidden></div>
  `;
}

beforeEach(setupDom);

describe('fillFormFromConfig', () => {
  it('回填 base/model，key 输入框保持为空并展示脱敏占位', () => {
    fillFormFromConfig({
      api_base: 'http://gw.io/v1',
      model: 'glm-5.2',
      api_key_masked: '****8888',
    });
    expect((document.getElementById('llm-base') as HTMLInputElement).value).toBe('http://gw.io/v1');
    expect((document.getElementById('llm-model') as HTMLInputElement).value).toBe('glm-5.2');
    const keyInput = document.getElementById('llm-key') as HTMLInputElement;
    expect(keyInput.value).toBe('');
    expect(keyInput.placeholder).toContain('****8888');
    expect(keyInput.placeholder).toContain('留空');
  });

  it('未配置 key 时提示必填而不是脱敏值', () => {
    fillFormFromConfig({ api_base: '', model: '', api_key_masked: '' });
    const keyInput = document.getElementById('llm-key') as HTMLInputElement;
    expect(keyInput.placeholder).toBe('尚未配置 API Key');
    expect(document.getElementById('llm-key-hint')!.textContent).toBe('尚未配置，必填');
  });
});

describe('buildSavePayload', () => {
  it('trim 各字段；key 留空时不携带 api_key（后端保留现有值）', () => {
    (document.getElementById('llm-base') as HTMLInputElement).value = ' http://gw.io/v1 ';
    (document.getElementById('llm-model') as HTMLInputElement).value = ' glm-5.2 ';
    (document.getElementById('llm-key') as HTMLInputElement).value = '   ';
    expect(buildSavePayload()).toEqual({ api_base: 'http://gw.io/v1', model: 'glm-5.2' });
  });

  it('key 有值时携带 api_key', () => {
    (document.getElementById('llm-base') as HTMLInputElement).value = 'http://gw.io/v1';
    (document.getElementById('llm-model') as HTMLInputElement).value = 'glm-5.2';
    (document.getElementById('llm-key') as HTMLInputElement).value = 'sk-new-key';
    expect(buildSavePayload()).toEqual({
      api_base: 'http://gw.io/v1',
      model: 'glm-5.2',
      api_key: 'sk-new-key',
    });
  });
});

describe('applyProbeResult', () => {
  it('成功时模型列表进 datalist，结果行显示数量与延迟', () => {
    applyProbeResult({ ok: true, models: ['model-b', 'model-a'], latency_ms: 123, error: null });
    const options = Array.from(document.querySelectorAll('#llm-model-list option'));
    expect(options.map((o) => (o as HTMLOptionElement).value)).toEqual(['model-b', 'model-a']);
    const box = document.getElementById('probe-result')!;
    expect(box.hidden).toBe(false);
    expect(box.className).toContain('probe_result--ok');
    expect(box.textContent).toContain('2 个可用模型');
    expect(box.textContent).toContain('123ms');
  });

  it('失败时结果行展示失败原因且不填模型列表', () => {
    applyProbeResult({ ok: false, models: [], latency_ms: 45, error: 'HTTP 401: bad key' });
    expect(document.querySelectorAll('#llm-model-list option').length).toBe(0);
    const box = document.getElementById('probe-result')!;
    expect(box.hidden).toBe(false);
    expect(box.className).toContain('probe_result--error');
    expect(box.textContent).toContain('HTTP 401');
  });
});
