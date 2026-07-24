// ===== 知识库管理页面逻辑 (manage.html) =====
// 依赖: sidebar.ts 已在上方加载

// Toast 工具函数
function showToast(message: string, type: string = 'info') {
    const container = document.getElementById('toast-container') as HTMLElement;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerText = message;
    container.appendChild(toast);

    // 触发淡入动画
    setTimeout(() => toast.classList.add('show'), 50);

    // 3秒后移除
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

const baseURL = '/index';
let currentActiveIndex: string | null = null;
let summaryUpdateTimer: ReturnType<typeof setTimeout> | null = null;
let updateTimers: Record<string, ReturnType<typeof setTimeout>> = {}; // 存储各个节点的定时器

// 全局加载遮罩控制
function showLoading(text = '正在处理中...') {
    const overlay = document.getElementById('loading-overlay') as HTMLElement;
    const textEl = overlay.querySelector('.loading-text') as HTMLElement | null;
    if (textEl) textEl.innerText = text;
    overlay.style.opacity = '1';
    overlay.style.visibility = 'visible';
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay') as HTMLElement;
    overlay.style.opacity = '0';
    overlay.style.visibility = 'hidden';
}

async function loadIndexes() {
    if (summaryUpdateTimer) {
        clearTimeout(summaryUpdateTimer);
    }
    for (let timerId in updateTimers) {
        clearTimeout(updateTimers[timerId]);
    }
    updateTimers = {};
    try {
        const response = await fetch(`${baseURL}/list`);
        const data = await response.json();
        const select = document.getElementById('index-select') as HTMLSelectElement;
        select.innerHTML = '';

        if (!data.indexes || data.indexes.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.innerText = '-- 暂无索引 --';
            select.appendChild(option);
            currentActiveIndex = null;
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

        // 默认选中第一个
        if (!currentActiveIndex || !data.indexes.includes(currentActiveIndex)) {
            currentActiveIndex = data.indexes[0];
        }
        select.value = currentActiveIndex!;

        // 加载摘要和节点
        loadIndexSummary(currentActiveIndex!);
        if (typeof loadIndexNodes === 'function') {
            loadIndexNodes(currentActiveIndex!);
        }
    } catch (error) {
        showToast('获取索引列表失败', 'error');
    }
}

// 绑定下拉选择事件
document.getElementById('index-select')!.addEventListener('change', (e: Event) => {
    if (summaryUpdateTimer) {
        clearTimeout(summaryUpdateTimer);
    }
    for (let timerId in updateTimers) {
        clearTimeout(updateTimers[timerId]);
    }
    updateTimers = {};
    const target = e.target as HTMLSelectElement | null;
    currentActiveIndex = target ? target.value : null;
    if (currentActiveIndex) {
        loadIndexSummary(currentActiveIndex);
        if (typeof loadIndexNodes === 'function') {
            loadIndexNodes(currentActiveIndex);
        }
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

async function loadIndexSummary(indexName: string) {
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
        const response = await fetch(`${baseURL}/${indexName}/get_summary`);
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

function updateSummaryDisplay(text: string) {
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
function debouncedUpdateSummary(text: string) {
    if (!currentActiveIndex) {
        showToast('当前无选中的活跃索引', 'error');
        return;
    }

    const statusTag = document.getElementById('summary-status-tag') as HTMLElement | null;
    if (statusTag) {
        statusTag.innerText = "正在输入...";
        statusTag.style.color = "#fa8c16";
    }

    if (summaryUpdateTimer) {
        clearTimeout(summaryUpdateTimer);
    }

    summaryUpdateTimer = setTimeout(async () => {
        if (statusTag) {
            statusTag.innerText = "保存中...";
            statusTag.style.color = "rgb(25, 84, 142)";
        }

        try {
            const body = new URLSearchParams();
            body.append('summary', text);

            const response = await fetch(`${baseURL}/${currentActiveIndex}/set_summary`, {
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

// 创建索引
async function createNewIndex() {
    const input = document.getElementById('new-index-name') as HTMLInputElement;
    const name = input.value.trim();
    if (!name) {
        showToast('请输入新索引名称', 'error');
        return;
    }

    const sanitized = name.replace(/[^\w\-]/g, '_');
    const body = new URLSearchParams();
    body.append('index_name', name);

    showLoading('正在创建索引...');
    try {
        const response = await fetch(`${baseURL}/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        const data = await response.json();
        if (data.status === 'success') {
            showToast(`索引 ${name} 创建成功`, 'success');
            input.value = '';
            currentActiveIndex = data.index_name; // Use returned sanitized name
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
async function deleteCurrentIndex() {
    if (!currentActiveIndex) {
        showToast('当前没有选中的活跃索引', 'error');
        return;
    }
    if (!confirm(`确定要删除知识库索引 "${currentActiveIndex}" 吗？此操作无法恢复！`)) {
        return;
    }

    const body = new URLSearchParams();
    body.append('index_name', currentActiveIndex);

    showLoading('正在删除索引...');
    try {
        const response = await fetch(`${baseURL}/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        if (response.ok) {
            showToast(`索引 ${currentActiveIndex} 已删除`, 'success');
            currentActiveIndex = null;
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
async function saveCurrentIndexDisk() {
    if (!currentActiveIndex) {
        showToast('当前无选中的活跃索引', 'error');
        return;
    }
    showLoading('正在保存索引到磁盘...');
    try {
        const response = await fetch(`${baseURL}/${currentActiveIndex}/save`, {
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

// Tab 切换逻辑
function switchTab(tabId: string) {
    document.querySelectorAll('.tab_btn').forEach((btn: Element) => btn.classList.remove('active'));
    document.querySelectorAll('.tab_content').forEach((content: Element) => content.classList.remove('active'));

    const activeBtn = Array.from(document.querySelectorAll('.tab_btn')).find(btn => btn.getAttribute('onclick') && btn.getAttribute('onclick')!.includes(tabId));
    if (activeBtn) activeBtn.classList.add('active');

    const content = document.getElementById(tabId);
    if (content) content.classList.add('active');
}

// 拖拽区域监听
let dragZoneInitialized = false;
function initDragZone() {
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
async function uploadFiles(files: FileList) {
    if (!currentActiveIndex) {
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
        const response = await fetch(`${baseURL}/${currentActiveIndex}/uploadFiles`, {
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
            if (typeof loadIndexNodes === 'function') {
            await loadIndexNodes(currentActiveIndex!);
            }
            showToast(`成功解析并插入 ${files.length} 个文件`, 'success');
            progressList.innerHTML = `<p class="upload_progress_msg upload_progress_msg--success">✓ 全部文件上传成功！</p>`;
        } else {
            showToast(data.message || '文件上传解析失败', 'error');
            progressList.innerHTML = `<p class="upload_progress_msg upload_progress_msg--error">✗ 上传失败: ${data.message || '未知错误'}</p>`;
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
async function submitDirectText() {
    if (!currentActiveIndex) {
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
        const response = await fetch(`${baseURL}/${currentActiveIndex}/insertdoc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });
        if (response.ok) {
            showToast('文档插入成功', 'success');
            docIdInput.value = '';
            docTextInput.value = '';
            if (typeof loadIndexNodes === 'function') {
                loadIndexNodes(currentActiveIndex);
            }
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
async function submitQAGeneration() {
    if (!currentActiveIndex) {
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
        const response = await fetch(`${baseURL}/${currentActiveIndex}/upload_file_by_QA`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            showToast('大模型 QA 数据生成并索引成功', 'success');
            promptInput.value = '';
            if (typeof loadIndexNodes === 'function') {
                loadIndexNodes(currentActiveIndex);
            }
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

let allNodesList: Array<{ text?: string; doc_id?: string; node_id?: string }> = [];
let filteredNodesList: Array<{ text?: string; doc_id?: string; node_id?: string }> = [];
let currentPage = 1;
const pageSize = 10;
// updateTimers is declared at the top of the script block

async function loadIndexNodes(indexName: string) {
    if (!indexName) {
        const viewport = document.getElementById('node-list-viewport');
        if (viewport) {
            viewport.innerHTML = '<div class="node_empty_hint">选择或载入索引以查看分块数据</div>';
        }
        const pagBar = document.getElementById('pagination-bar');
        if (pagBar) {
            pagBar.style.display = 'none';
        }
        return;
    }

    const viewport = document.getElementById('node-list-viewport') as HTMLElement;
    viewport.innerHTML = '<div class="node_empty_hint node_empty_hint--primary">正在加载节点数据...</div>';
    const pagBar = document.getElementById('pagination-bar');
    if (pagBar) pagBar.style.display = 'none';

    try {
        const response = await fetch(`${baseURL}/${indexName}/info`);
        const data = await response.json();
        allNodesList = data.docs || [];

        // 执行过滤与渲染
        applyFilterAndRender();
    } catch (error) {
        viewport.innerHTML = '<div class="node_empty_hint node_empty_hint--error">数据分块加载失败</div>';
        showToast('获取索引节点数据失败', 'error');
    }
}

// 绑定搜索输入事件 (300ms 防抖)
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
document.getElementById('node-search')!.addEventListener('input', () => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        currentPage = 1;
        applyFilterAndRender();
    }, 300);
});

function applyFilterAndRender() {
    const keyword = (document.getElementById('node-search') as HTMLInputElement).value.trim().toLowerCase();

    if (!keyword) {
        filteredNodesList = [...allNodesList];
    } else {
        filteredNodesList = allNodesList.filter(node =>
            (node.text && String(node.text).toLowerCase().includes(keyword)) ||
            (node.doc_id && String(node.doc_id).toLowerCase().includes(keyword)) ||
            (node.node_id && String(node.node_id).toLowerCase().includes(keyword))
        );
    }

    currentPage = 1;
    renderNodesPage();
}

function renderNodesPage() {
    const viewport = document.getElementById('node-list-viewport') as HTMLElement;
    const pagBar = document.getElementById('pagination-bar') as HTMLElement;

    if (filteredNodesList.length === 0) {
        viewport.innerHTML = '<div class="node_empty_hint">无匹配的节点数据</div>';
        pagBar.style.display = 'none';
        return;
    }

    const totalItems = filteredNodesList.length;
    const totalPages = Math.ceil(totalItems / pageSize);

    // 分页区间
    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, totalItems);
    const pageItems = filteredNodesList.slice(startIdx, endIdx);

    viewport.innerHTML = '';
    pageItems.forEach(node => {
        const card = document.createElement('div');
        card.className = 'node_card';

        card.innerHTML = `
            <div class="node_meta_row">
                <span>Doc ID: <span class="node_doc_id"></span></span>
                <span class="node_id_text">Node ID: ${node.node_id}</span>
            </div>
            <textarea class="node_editor"></textarea>
            <div class="node_actions">
                <span class="node_status_tag" id="status-${node.node_id}">未做修改</span>
                <div class="node_action_buttons">
                    <button class="btn-delete-node btn-delete-doc">删除整档</button>
                    <button class="btn-delete-node btn-delete-chunk">删除分块</button>
                </div>
            </div>
        `;

        // 安全设置文本，避免 HTML 注入或解析崩溃
        const docIdSpan = card.querySelector('.node_doc_id') as HTMLElement | null;
        if (docIdSpan) docIdSpan.textContent = node.doc_id || '自动生成';

        const textarea = card.querySelector('.node_editor') as HTMLTextAreaElement | null;
        if (textarea) textarea.value = node.text || '';

        // 绑定输入事件 (防抖)
        const statusTag = card.querySelector('.node_status_tag') as HTMLElement;
        textarea?.addEventListener('input', (e: Event) => {
            const target = e.target as HTMLTextAreaElement;
            debouncedUpdateNode(node.node_id!, target.value, statusTag);
        });

        // 绑定按钮事件
        const deleteDocBtn = card.querySelector('.btn-delete-doc') as HTMLElement | null;
        const deleteChunkBtn = card.querySelector('.btn-delete-chunk') as HTMLElement | null;
        if (deleteDocBtn) {
            (deleteDocBtn as HTMLElement).onclick = () => deleteDocByCard(node.doc_id!);
        }
        if (deleteChunkBtn) {
            (deleteChunkBtn as HTMLElement).onclick = () => deleteNodeByCard(node.node_id!);
        }

        viewport.appendChild(card);
    });

    // 调整分页组件显示
    pagBar.style.display = 'flex';
    (document.getElementById('page-indicator') as HTMLElement).innerText = `第 ${currentPage} / ${totalPages} 页 (共 ${totalItems} 项)`;

    const prevBtn = document.getElementById('btn-prev-page') as HTMLButtonElement | null;
    const nextBtn = document.getElementById('btn-next-page') as HTMLButtonElement | null;
    if (prevBtn) prevBtn.disabled = (currentPage === 1);
    if (nextBtn) nextBtn.disabled = (currentPage === totalPages);
}

function prevPage() {
    if (currentPage > 1) {
        currentPage--;
        renderNodesPage();
        (document.getElementById('node-list-viewport') as HTMLElement).scrollTop = 0;
    }
}

function nextPage() {
    const totalPages = Math.ceil(filteredNodesList.length / pageSize);
    if (currentPage < totalPages) {
        currentPage++;
        renderNodesPage();
        (document.getElementById('node-list-viewport') as HTMLElement).scrollTop = 0;
    }
}

// 节点内容的防抖保存逻辑
function debouncedUpdateNode(nodeId: string, text: string, statusElement: HTMLElement) {
    statusElement.innerText = "正在输入...";
    statusElement.style.color = "#fa8c16";

    if (updateTimers[nodeId]) {
        clearTimeout(updateTimers[nodeId]);
    }

    updateTimers[nodeId] = setTimeout(async () => {
        statusElement.innerText = "正在自动保存...";
        statusElement.style.color = "rgb(25, 84, 142)";

        try {
            const body = new URLSearchParams();
            body.append('text', text);

            const response = await fetch(`${baseURL}/${currentActiveIndex}/update?nodeId=${nodeId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body.toString()
            });

            if (response.ok) {
                statusElement.innerText = "✓ 已自动保存";
                statusElement.style.color = "#52c41a";
                // 同步更新本地缓存数据中的text值
                const node = allNodesList.find(n => n.node_id === nodeId);
                if (node) node.text = text;
            } else {
                statusElement.innerText = "✗ 保存失败";
                statusElement.style.color = "#ff4d4f";
            }
        } catch (error) {
            statusElement.innerText = "✗ 网络保存异常";
            statusElement.style.color = "#ff4d4f";
        }
    }, 1000); // 用户停止录入 1 秒后自动提交
}

// 删除单节点分块
async function deleteNodeByCard(nodeId: string) {
    if (!confirm('确定要删除这个数据分块(Node)吗？此操作不可逆！')) {
        return;
    }
    if (updateTimers[nodeId]) {
        clearTimeout(updateTimers[nodeId]);
        delete updateTimers[nodeId];
    }
    const statusEl = document.getElementById(`status-${nodeId}`) as HTMLElement | null;
    if (statusEl) statusEl.innerText = '删除中...';
    try {
        const response = await fetch(`${baseURL}/${currentActiveIndex}/deleteNode?node_id=${nodeId}`, {
            method: 'POST'
        });
        const data = await response.json();
        if (response.ok && data.status === 'deleted') {
            showToast('数据分块已成功删除', 'success');
            // 从本地缓存中踢出并重绘
            allNodesList = allNodesList.filter(n => n.node_id !== nodeId);
            applyFilterAndRender();
        } else {
            showToast(data.message || '删除节点失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，删除节点失败', 'error');
    }
}

// 删除整档
async function deleteDocByCard(docId: string) {
    if (!docId) {
        showToast('该卡片无关联的 Doc ID，无法删除整档，请使用删除分块', 'error');
        return;
    }
    if (!confirm(`确定要彻底删除文档 "${docId}" 及其所包含的所有分块吗？`)) {
        return;
    }
    const docNodes = allNodesList.filter(n => n.doc_id === docId);
    docNodes.forEach(node => {
        if (updateTimers[node.node_id!]) {
            clearTimeout(updateTimers[node.node_id!]);
            delete updateTimers[node.node_id!];
        }
    });
    try {
        const response = await fetch(`${baseURL}/${currentActiveIndex}/deleteDoc?doc_id=${docId}`, {
            method: 'POST'
        });
        const data = await response.json();
        if (response.ok && data.status === 'deleted') {
            showToast('整档文件及其所有分块已成功清除', 'success');
            // 重新请求后端，以防有其它关联节点
            await loadIndexNodes(currentActiveIndex!);
        } else {
            showToast(data.message || '删除整档文件失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，删除整档失败', 'error');
    }
}

// 页面初始加载
window.addEventListener('DOMContentLoaded', () => {
    loadIndexes();
    initDragZone();
});
