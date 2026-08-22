// ===== 索引面板：索引列表加载 / 下拉切换 / 新建 / 删除 / 持久化 =====

import { apiFetch } from "../utils/api";
import { showToast } from "../utils/toast";
import { hideLoading, showLoading } from "../utils/loading";
import { loadIndexNodes, resetNodePanelForIndexSwitch } from "./nodesPanel";
import { loadIndexSummary, updateSummaryDisplay } from "./summary";
import { LAST_INDEX_KEY, baseURL, clearPendingEdits, hasUnsavedNodeEdits, manageState } from "./state";

export async function loadIndexes() {
    clearPendingEdits();
    resetNodePanelForIndexSwitch();
    try {
        const response = await apiFetch(`${baseURL}/list`);
        const data = await response.json();
        const select = document.getElementById('index-select') as HTMLSelectElement;
        select.innerHTML = '';

        if (!data.indexes || data.indexes.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.innerText = '-- 暂无索引 --';
            select.appendChild(option);
            manageState.currentActiveIndex = null;
            updateSummaryDisplay('暂无索引，请在上方新建索引。');

            // 清理节点展示区域，防止残留数据
            const viewport = document.getElementById('node-list-viewport') || document.getElementById('panel-right-container');
            if (viewport) {
                viewport.innerHTML = '<div class="node_empty_hint">暂无活跃索引</div>';
            }
            const pagBar = document.getElementById('pagination-bar');
            if (pagBar) {
                pagBar.style.display = 'none';
            }
            return;
        }

        data.indexes.forEach((indexName: string) => {
            const option = document.createElement('option');
            option.value = indexName;
            option.innerText = indexName;
            select.appendChild(option);
        });

        // 默认选中: 优先 localStorage 记忆的上次索引, 其次第一个
        if (!manageState.currentActiveIndex || !data.indexes.includes(manageState.currentActiveIndex)) {
            const last = localStorage.getItem(LAST_INDEX_KEY);
            manageState.currentActiveIndex = (last && data.indexes.includes(last)) ? last : data.indexes[0];
        }
        select.value = manageState.currentActiveIndex!;
        localStorage.setItem(LAST_INDEX_KEY, manageState.currentActiveIndex!);

        // 加载摘要和节点
        loadIndexSummary(manageState.currentActiveIndex!);
        loadIndexNodes(manageState.currentActiveIndex!);
    } catch (error) {
        showToast('获取索引列表失败', 'error');
    }
}

/** 绑定下拉选择事件（切换前若有未保存修改, 弹二次确认） */
export function bindIndexSelect() {
    document.getElementById('index-select')!.addEventListener('change', (e: Event) => {
        const target = e.target as HTMLSelectElement | null;
        const newValue = target ? target.value : null;

        // 切换前检查未保存修改
        if (newValue !== manageState.currentActiveIndex && hasUnsavedNodeEdits()) {
            if (!window.confirm('当前索引有未保存的修改（节点或摘要），切换会丢弃这些修改。确定切换吗？')) {
                // 用户取消, 还原 select 显示为 currentActiveIndex
                if (manageState.currentActiveIndex) (target as HTMLSelectElement).value = manageState.currentActiveIndex;
                return;
            }
        }

        clearPendingEdits();
        resetNodePanelForIndexSwitch();
        manageState.currentActiveIndex = newValue;
        if (manageState.currentActiveIndex) {
            localStorage.setItem(LAST_INDEX_KEY, manageState.currentActiveIndex);
            loadIndexSummary(manageState.currentActiveIndex);
            loadIndexNodes(manageState.currentActiveIndex);
        } else {
            updateSummaryDisplay('未选中任何活跃索引');
            const viewport = document.getElementById('node-list-viewport') || document.getElementById('panel-right-container');
            if (viewport) {
                viewport.innerHTML = '<div class="node_empty_hint">未选中任何活跃索引</div>';
            }
            const pagBar = document.getElementById('pagination-bar');
            if (pagBar) {
                pagBar.style.display = 'none';
            }
        }
    });
}

// 创建索引
export async function createNewIndex() {
    const input = document.getElementById('new-index-name') as HTMLInputElement;
    const name = input.value.trim();
    if (!name) {
        showToast('请输入新索引名称', 'error');
        return;
    }

    const sanitized = name.replace(/[^\w\-]/g, '_');
    const body = new URLSearchParams();
    body.append('index_name', sanitized);

    showLoading('正在创建索引...');
    try {
        const response = await apiFetch(`${baseURL}/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        const data = await response.json();
        if (data.status === 'success') {
            showToast(`索引 ${name} 创建成功`, 'success');
            input.value = '';
            manageState.currentActiveIndex = data.index_name; // Use returned sanitized name
            await loadIndexes();
        } else {
            showToast(data.msg || '新建失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，创建索引失败', 'error');
    } finally {
        hideLoading();
    }
}

// 删除索引
export async function deleteCurrentIndex() {
    if (!manageState.currentActiveIndex) {
        showToast('当前没有选中的活跃索引', 'error');
        return;
    }
    if (!confirm(`确定要删除知识库索引 "${manageState.currentActiveIndex}" 吗？此操作无法恢复！`)) {
        return;
    }

    const body = new URLSearchParams();
    body.append('index_name', manageState.currentActiveIndex);

    showLoading('正在删除索引...');
    try {
        const response = await apiFetch(`${baseURL}/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        if (response.ok) {
            showToast(`索引 ${manageState.currentActiveIndex} 已删除`, 'success');
            manageState.currentActiveIndex = null;
            await loadIndexes();
        } else {
            showToast('删除索引失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，删除索引失败', 'error');
    } finally {
        hideLoading();
    }
}

// 保存索引到磁盘
export async function saveCurrentIndexDisk() {
    if (!manageState.currentActiveIndex) {
        showToast('当前无选中的活跃索引', 'error');
        return;
    }
    showLoading('正在保存索引到磁盘...');
    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/save`, {
            method: 'POST'
        });
        if (response.ok) {
            showToast('索引已成功持久化至磁盘', 'success');
        } else {
            showToast('保存磁盘失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，保存磁盘失败', 'error');
    } finally {
        hideLoading();
    }
}
