// ===== 索引摘要面板：加载 / 展示 / 防抖自动保存 =====

import { apiFetch } from "../utils/api";
import { showToast } from "../utils/toast";
import { baseURL, manageState } from "./state";

export async function loadIndexSummary(indexName: string) {
    const textarea = document.getElementById('index-summary-textarea') as HTMLTextAreaElement | null;
    const statusTag = document.getElementById('summary-status-tag') as HTMLElement | null;

    if (textarea) {
        textarea.disabled = true;
        textarea.value = '加载摘要中...';
    }
    if (statusTag) {
        statusTag.innerText = '加载中...';
        statusTag.style.color = '#fa8c16';
    }
    try {
        const response = await apiFetch(`${baseURL}/${indexName}/get_summary`);
        const data = await response.json();
        if (textarea) {
            textarea.value = data.summary || '';
            textarea.disabled = false;
        }
        if (statusTag) {
            statusTag.innerText = '已加载';
            statusTag.style.color = '#52c41a';
        }
    } catch (error) {
        if (textarea) {
            textarea.value = '读取摘要失败';
        }
        if (statusTag) {
            statusTag.innerText = '错误';
            statusTag.style.color = '#ff4d4f';
        }
    }
}

export function updateSummaryDisplay(text: string) {
    const textarea = document.getElementById('index-summary-textarea') as HTMLTextAreaElement | null;
    if (textarea) {
        textarea.value = text;
        textarea.disabled = true;
    }
    const statusTag = document.getElementById('summary-status-tag') as HTMLElement | null;
    if (statusTag) {
        statusTag.innerText = '';
    }
}

// 索引摘要防抖保存
export function debouncedUpdateSummary(text: string) {
    if (!manageState.currentActiveIndex) {
        showToast('当前无选中的活跃索引', 'error');
        return;
    }

    const statusTag = document.getElementById('summary-status-tag') as HTMLElement | null;
    if (statusTag) {
        statusTag.innerText = "正在输入...";
        statusTag.style.color = "#fa8c16";
    }

    if (manageState.summaryUpdateTimer) {
        clearTimeout(manageState.summaryUpdateTimer);
    }

    manageState.summaryUpdateTimer = setTimeout(async () => {
        manageState.summaryUpdateTimer = null; // 触发后清空, 避免 hasUnsavedNodeEdits 误报
        if (statusTag) {
            statusTag.innerText = "保存中...";
            statusTag.style.color = "rgb(25, 84, 142)";
        }

        try {
            const body = new URLSearchParams();
            body.append('summary', text);

            const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/set_summary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body.toString()
            });
            const data = await response.json();
            if (data.status === 'ok') {
                if (statusTag) {
                    statusTag.innerText = "✓ 已自动保存";
                    statusTag.style.color = "#52c41a";
                }
            } else {
                if (statusTag) {
                    statusTag.innerText = "✗ 保存失败";
                    statusTag.style.color = "#ff4d4f";
                }
            }
        } catch (error) {
            if (statusTag) {
                statusTag.innerText = "✗ 网络保存异常";
                statusTag.style.color = "#ff4d4f";
            }
        }
    }, 1000);
}

/** 绑定摘要输入框的自动保存（页面入口调用一次） */
export function bindSummaryInput() {
    const summaryTextarea = document.getElementById('index-summary-textarea');
    if (summaryTextarea) {
        summaryTextarea.addEventListener('input', (e) => {
            debouncedUpdateSummary((e.target as HTMLTextAreaElement).value);
        });
    }
}
