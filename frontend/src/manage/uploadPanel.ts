// ===== 内容上传面板：拖拽上传 / 多文件 / 直接文本 / QA 生成式导入 =====

import { apiFetch } from "../utils/api";
import { showToast } from "../utils/toast";
import { escapeHtml } from "../utils/dom";
import { hideLoading, showLoading } from "../utils/loading";
import { loadIndexNodes } from "./nodesPanel";
import { baseURL, manageState } from "./state";

// 拖拽区域监听
let dragZoneInitialized = false;
export function initDragZone() {
    const dragZone = document.getElementById('drag-zone') as HTMLElement | null;
    if (!dragZone || dragZoneInitialized) return;

    dragZone.addEventListener('dragover', (e: DragEvent) => {
        e.preventDefault();
        dragZone.classList.add('dragover');
    });

    dragZone.addEventListener('dragleave', () => {
        dragZone.classList.remove('dragover');
    });

    dragZone.addEventListener('drop', (e: DragEvent) => {
        e.preventDefault();
        dragZone.classList.remove('dragover');
        const dt = e.dataTransfer;
        if (!dt) return;
        const files = dt.files;
        if (files.length > 0) {
            uploadFiles(files);
        }
    });

    const fileInput = document.getElementById('file-input') as HTMLInputElement | null;
    fileInput?.addEventListener('change', (e: Event) => {
        const target = e.target as HTMLInputElement | null;
        const files = target?.files;
        if (files && files.length > 0) {
            uploadFiles(files);
        }
    });
    dragZoneInitialized = true;
}

// 多文件上传
export async function uploadFiles(files: FileList) {
    if (!manageState.currentActiveIndex) {
        showToast('请先选择或新建一个活跃索引', 'error');
        return;
    }

    const progressList = document.getElementById('upload-progress-list') as HTMLElement;
    progressList.innerHTML = `
        <div class="upload_progress_item upload_progress_item--primary">
            <div class="inline-spinner"></div>
            <span>正在上传并解析 ${files.length} 个文件，请稍候...</span>
        </div>`;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/uploadFiles`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok && data.status === 'inserted') {
            // 先显示成功信息，再重新加载节点
            progressList.innerHTML = `
                <div class="upload_progress_item upload_progress_item--success">
                    <div class="inline-spinner"></div>
                    <span>✓ 上传成功，正在刷新节点列表...</span>
                </div>`;
            // 等待节点加载完成
            await loadIndexNodes(manageState.currentActiveIndex!);
            showToast(`成功解析并插入 ${files.length} 个文件`, 'success');
            progressList.innerHTML = `<p class="upload_progress_msg upload_progress_msg--success">✓ 全部文件上传成功！</p>`;
        } else {
            showToast(data.message || '文件上传解析失败', 'error');
            progressList.innerHTML = `<p class="upload_progress_msg upload_progress_msg--error">✗ 上传失败: ${escapeHtml(data.message || '未知错误')}</p>`;
        }
    } catch (error) {
        showToast('网络错误，文件上传失败', 'error');
        progressList.innerHTML = `<p class="upload_progress_msg upload_progress_msg--error">✗ 网络连接错误</p>`;
    } finally {
        const fileInput = document.getElementById('file-input') as HTMLInputElement | null;
        if (fileInput) fileInput.value = '';
    }
}

// 直接文本插入
export async function submitDirectText() {
    if (!manageState.currentActiveIndex) {
        showToast('请先选择活跃索引', 'error');
        return;
    }
    const docIdInput = document.getElementById('input-doc-id') as HTMLInputElement;
    const docTextInput = document.getElementById('input-doc-text') as HTMLTextAreaElement;
    const docId = docIdInput.value.trim();
    const text = docTextInput.value.trim();

    if (!text) {
        showToast('请输入文档内容文本', 'error');
        return;
    }

    const body = new URLSearchParams();
    body.append('text', text);
    if (docId) {
        body.append('doc_id', docId);
    }

    showLoading('正在插入文档...');
    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/insertdoc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        if (response.ok) {
            showToast('文档插入成功', 'success');
            docIdInput.value = '';
            docTextInput.value = '';
            loadIndexNodes(manageState.currentActiveIndex);
        } else {
            showToast('文档插入失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，插入文档失败', 'error');
    } finally {
        hideLoading();
    }
}

// QA生成式上传
export async function submitQAGeneration() {
    if (!manageState.currentActiveIndex) {
        showToast('请先选择活跃索引', 'error');
        return;
    }

    const fileInput = document.getElementById('qa-file-input') as HTMLInputElement;
    const promptInput = document.getElementById('qa-custom-prompt') as HTMLTextAreaElement;
    const file = fileInput.files?.[0];
    const prompt = promptInput.value.trim();

    if (!file) {
        showToast('请选择源文件', 'error');
        return;
    }

    showToast('正在向大模型提交QA抽取申请，请稍候...', 'info');
    showLoading('正在生成 QA 并导入，大模型处理可能需要较长时间，请稍候...');

    const formData = new FormData();
    formData.append('file', file);
    if (prompt) {
        formData.append('prompt', prompt);
    }

    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/upload_file_by_QA`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            showToast('大模型 QA 数据生成并索引成功', 'success');
            promptInput.value = '';
            loadIndexNodes(manageState.currentActiveIndex);
        } else {
            showToast(data.message || 'QA 生成失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，提交QA任务失败', 'error');
    } finally {
        hideLoading();
        (document.getElementById('qa-file-input') as HTMLInputElement).value = '';
    }
}
