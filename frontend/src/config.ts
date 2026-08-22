// ===== 系统配置页面逻辑 (config.html) =====
// LLM 连接配置的查看 / 探测 / 保存（写 .env + 热生效）。

import { apiFetch } from "./utils/api";
import { showToast } from "./utils/toast";

const baseURL = '/manage';

export interface LLMConfig {
  api_base: string;
  model: string;
  api_key_masked: string;
  warning?: string | null;
}

export interface ProbeResult {
  ok: boolean;
  models: string[];
  latency_ms: number | null;
  error?: string | null;
}

/** 把后端返回的配置填进表单；key 输入框只放脱敏提示，不回填假值。 */
export function fillFormFromConfig(config: LLMConfig): void {
  const baseInput = document.getElementById('llm-base') as HTMLInputElement | null;
  const keyInput = document.getElementById('llm-key') as HTMLInputElement | null;
  const keyHint = document.getElementById('llm-key-hint');
  const modelInput = document.getElementById('llm-model') as HTMLInputElement | null;
  if (baseInput) baseInput.value = config.api_base || '';
  if (modelInput) modelInput.value = config.model || '';
  if (keyInput) {
    keyInput.value = '';
    keyInput.placeholder = config.api_key_masked
      ? `已配置 ${config.api_key_masked}，留空保持不变`
      : '尚未配置 API Key';
  }
  if (keyHint) {
    keyHint.textContent = config.api_key_masked
      ? `已配置 ${config.api_key_masked}，更换时才需要填写`
      : '尚未配置，必填';
  }
}

/** 组装保存请求体：key 输入框留空 → 不传（后端保留现有 key）。
 *  以 **** 开头的值是回显的脱敏占位符，不能当新 key 存回去（后端也有同样防呆）。 */
export function buildSavePayload() {
  const base = (document.getElementById('llm-base') as HTMLInputElement).value.trim();
  const key = (document.getElementById('llm-key') as HTMLInputElement).value.trim();
  const model = (document.getElementById('llm-model') as HTMLInputElement).value.trim();
  const payload: { api_base: string; model: string; api_key?: string } = { api_base: base, model };
  if (key && !key.startsWith('****')) payload.api_key = key;
  return payload;
}

/** 探测结果渲染：模型列表进 datalist 供下拉选择，状态行展示延迟或失败原因。 */
export function applyProbeResult(result: ProbeResult): void {
  const datalist = document.getElementById('llm-model-list');
  const box = document.getElementById('probe-result');
  if (datalist) {
    datalist.innerHTML = '';
    result.models.forEach((name) => {
      const option = document.createElement('option');
      option.value = name;
      datalist.appendChild(option);
    });
  }
  if (!box) return;
  box.hidden = false;
  if (result.ok) {
    box.textContent = `连接成功 · ${result.models.length} 个可用模型 · ${result.latency_ms}ms（模型列表已填入下拉框）`;
    box.className = 'probe_result probe_result--ok';
  } else {
    box.textContent = `连接失败：${result.error || '未知错误'}`;
    box.className = 'probe_result probe_result--error';
  }
}

async function handleApiError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

async function loadConfig(): Promise<void> {
  try {
    const response = await apiFetch(`${baseURL}/llm-config`);
    if (!response.ok) {
      showToast(await handleApiError(response, '读取配置失败'), 'error');
      return;
    }
    fillFormFromConfig(await response.json());
  } catch {
    showToast('网络错误，无法读取当前配置', 'error');
  }
}

async function probe(): Promise<void> {
  const button = document.getElementById('btn-probe') as HTMLButtonElement | null;
  if (button) button.disabled = true;
  try {
    const payload = buildSavePayload();
    const body: Record<string, string> = { api_base: payload.api_base };
    if (payload.api_key) body.api_key = payload.api_key;
    const response = await apiFetch(`${baseURL}/llm-probe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      showToast(await handleApiError(response, '探测请求失败'), 'error');
      return;
    }
    applyProbeResult(await response.json());
  } catch {
    showToast('网络错误，探测请求未发出', 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function save(): Promise<void> {
  const payload = buildSavePayload();
  if (!payload.api_base || !payload.model) {
    showToast('Base URL 和模型不能为空', 'warning');
    return;
  }
  const button = document.getElementById('btn-save') as HTMLButtonElement | null;
  if (button) button.disabled = true;
  try {
    const response = await apiFetch(`${baseURL}/llm-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      showToast(await handleApiError(response, '保存失败'), 'error');
      return;
    }
    const config: LLMConfig = await response.json();
    fillFormFromConfig(config);
    showToast(config.warning || '已保存并热生效', config.warning ? 'warning' : 'success');
  } catch {
    showToast('网络错误，保存未完成', 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

// 仅在配置页面（存在对应 DOM）时绑定事件，便于测试环境复用本模块。
if (document.getElementById('btn-save')) {
  loadConfig();
  document.getElementById('btn-probe')?.addEventListener('click', probe);
  document.getElementById('btn-save')?.addEventListener('click', save);
}
