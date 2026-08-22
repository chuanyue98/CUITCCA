// ===== 节点列表面板：加载 / 搜索过滤 / 分页渲染 / 行内编辑防抖保存 / 删除 =====

import { apiFetch } from "../utils/api";
import { showToast } from "../utils/toast";
import { escapeHtml } from "../utils/dom";
import { baseURL, manageState } from "./state";

let allNodesList: Array<{ text?: string; doc_id?: string; node_id?: string }> = [];
let filteredNodesList: Array<{ text?: string; doc_id?: string; node_id?: string }> = [];
let currentPage = 1;
// 每页条数可由用户在 #page-size-select 里改（10/20/50），不再是常量。
let pageSize = 10;
// 搜索输入防抖定时器（300ms）
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

/** 切换/重载索引前重置本面板的瞬态状态（搜索防抖 + 页码） */
export function resetNodePanelForIndexSwitch() {
    if (searchDebounceTimer) { clearTimeout(searchDebounceTimer); searchDebounceTimer = null; }
    currentPage = 1;
}

export async function loadIndexNodes(indexName: string) {
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
        const response = await apiFetch(`${baseURL}/${indexName}/info`);
        const data = await response.json();
        allNodesList = data.docs || [];

        // 执行过滤与渲染
        applyFilterAndRender();
    } catch (error) {
        viewport.innerHTML = '<div class="node_empty_hint node_empty_hint--error">数据分块加载失败</div>';
        showToast('获取索引节点数据失败', 'error');
    }
}

/** 绑定搜索输入事件（300ms 防抖） */
export function bindNodeSearch() {
    document.getElementById('node-search')!.addEventListener('input', () => {
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            currentPage = 1;
            applyFilterAndRender();
        }, 300);
    });
}

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

        // 该分块在所属文档内的位置（第 N / 共 M 块）：用 allNodesList 全量
        // 数据按 doc_id 过滤，保留后端原始返回顺序（即分块顺序）。
        const siblingNodes = allNodesList.filter(n => n.doc_id === node.doc_id);
        const posInDoc = siblingNodes.findIndex(n => n.node_id === node.node_id) + 1;
        const totalInDoc = siblingNodes.length || 1;
        const charCount = (node.text || '').length;
        const nodeIdShort = (node.node_id || '').slice(0, 8);

        card.innerHTML = `
            <div class="node_meta_row">
                <span class="node_meta_docid">Doc ID: <button type="button" class="node_doc_id"></button></span>
                <span class="node_meta_info">${charCount} 字 · 第 ${posInDoc || 1} / ${totalInDoc} 块</span>
                <button type="button" class="node_id_short" title="完整 Node ID：${escapeHtml(node.node_id)}（点击复制）">${escapeHtml(nodeIdShort)}</button>
            </div>
            <textarea class="node_editor"></textarea>
            <div class="node_actions">
                <span class="node_status_tag" id="status-${escapeHtml(node.node_id)}">未做修改</span>
                <div class="node_action_buttons">
                    <button class="btn-delete-node btn-delete-doc">删除整档</button>
                    <button class="btn-delete-node btn-delete-chunk">删除分块</button>
                </div>
            </div>
        `;

        // 安全设置文本，避免 HTML 注入或解析崩溃
        const docIdBtn = card.querySelector('.node_doc_id') as HTMLButtonElement | null;
        if (docIdBtn) {
            const docId = node.doc_id || '';
            docIdBtn.textContent = docId || '自动生成';
            if (docId) {
                // Doc ID 徽标可点击：等价于把该 doc_id 填进 #node-search 并
                // 触发筛选，方便用户在"删除整档"前先看清这份文档包含哪些分块。
                docIdBtn.title = '点击筛选该文档的所有分块';
                docIdBtn.addEventListener('click', () => filterByDocId(docId));
            } else {
                // 无 doc_id（自动生成）的分块没有可筛选目标，禁用交互
                docIdBtn.disabled = true;
            }
        }

        const nodeIdShortBtn = card.querySelector('.node_id_short') as HTMLButtonElement | null;
        nodeIdShortBtn?.addEventListener('click', () => copyNodeId(node.node_id || ''));

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
            deleteDocBtn.onclick = () => deleteDocByCard(node.doc_id!);
        }
        if (deleteChunkBtn) {
            deleteChunkBtn.onclick = () => deleteNodeByCard(node.node_id!);
        }

        viewport.appendChild(card);
    });

    // 调整分页组件显示
    pagBar.style.display = 'flex';
    (document.getElementById('page-indicator') as HTMLElement).innerText = `第 ${currentPage} / ${totalPages} 页 (共 ${totalItems} 项)`;

    const prevBtn = document.getElementById('btn-prev-page') as HTMLButtonElement | null;
    const nextBtn = document.getElementById('btn-next-page') as HTMLButtonElement | null;
    const firstBtn = document.getElementById('btn-first-page') as HTMLButtonElement | null;
    const lastBtn = document.getElementById('btn-last-page') as HTMLButtonElement | null;
    if (prevBtn) prevBtn.disabled = (currentPage === 1);
    if (nextBtn) nextBtn.disabled = (currentPage === totalPages);
    if (firstBtn) firstBtn.disabled = (currentPage === 1);
    if (lastBtn) lastBtn.disabled = (currentPage === totalPages);

    // 跳页输入框：同步页码范围提示，方便用户知道能跳到哪一页
    const jumpInput = document.getElementById('page-jump-input') as HTMLInputElement | null;
    if (jumpInput) {
        jumpInput.max = String(totalPages);
        jumpInput.placeholder = `1-${totalPages}`;
    }

    // 每页条数下拉框：保持和当前 pageSize 一致（切换索引/搜索时不会重置
    // pageSize，只有用户主动改下拉框才会变）
    const sizeSelect = document.getElementById('page-size-select') as HTMLSelectElement | null;
    if (sizeSelect && sizeSelect.value !== String(pageSize)) sizeSelect.value = String(pageSize);
}

// 跳转到指定页，越界自动夹到 [1, totalPages] 区间——154 页时用户手输的页码
// 很容易输错（0、负数、超过总页数、非数字），这里统一兜底，不会崩也不会
// 出现空白页。
function goToPage(page: number) {
    const totalPages = Math.max(1, Math.ceil(filteredNodesList.length / pageSize));
    const safePage = Number.isFinite(page) ? Math.floor(page) : 1;
    currentPage = Math.min(Math.max(1, safePage), totalPages);
    renderNodesPage();
    (document.getElementById('node-list-viewport') as HTMLElement).scrollTop = 0;
}

export function prevPage() { goToPage(currentPage - 1); }
export function nextPage() { goToPage(currentPage + 1); }
export function firstPage() { goToPage(1); }
export function lastPage() { goToPage(Math.ceil(filteredNodesList.length / pageSize)); }

// 跳页输入框的提交：允许空输入/非数字，这时候只是不动，不弹错误打断操作
export function jumpToPageFromInput() {
    const input = document.getElementById('page-jump-input') as HTMLInputElement | null;
    if (!input) return;
    const val = parseInt(input.value, 10);
    if (!Number.isFinite(val)) {
        showToast('请输入有效页码', 'error');
        return;
    }
    goToPage(val);
    input.value = '';
}

// 切换每页条数：尽量保持用户正在看的那批数据不跳变——记录当前页第一项的
// 绝对下标，换算成新页码下能包含该项的页，而不是粗暴地跳回第 1 页。
export function changePageSize(newSize: number) {
    const firstItemIndex = (currentPage - 1) * pageSize;
    pageSize = newSize;
    currentPage = Math.floor(firstItemIndex / pageSize) + 1;
    renderNodesPage();
}

// 点击 Doc ID 徽标：等价于把该 doc_id 填进搜索框并触发筛选
function filterByDocId(docId: string) {
    const searchInput = document.getElementById('node-search') as HTMLInputElement | null;
    if (!searchInput) return;
    if (searchDebounceTimer) { clearTimeout(searchDebounceTimer); searchDebounceTimer = null; }
    searchInput.value = docId;
    currentPage = 1;
    applyFilterAndRender();
    searchInput.focus();
}

// 点击 Node ID 短标记：复制完整 ID 到剪贴板
async function copyNodeId(nodeId: string) {
    if (!nodeId) return;
    try {
        await navigator.clipboard.writeText(nodeId);
        showToast('Node ID 已复制', 'success');
    } catch (error) {
        showToast('复制失败，请手动选择复制', 'error');
    }
}

// 节点内容的防抖保存逻辑
function debouncedUpdateNode(nodeId: string, text: string, statusElement: HTMLElement) {
    statusElement.innerText = "正在输入...";
    statusElement.style.color = "#fa8c16";

    if (manageState.updateTimers[nodeId]) {
        clearTimeout(manageState.updateTimers[nodeId]);
    }

    manageState.updateTimers[nodeId] = setTimeout(async () => {
        delete manageState.updateTimers[nodeId]; // 触发后清空, 避免 hasUnsavedNodeEdits 误报
        statusElement.innerText = "正在自动保存...";
        statusElement.style.color = "rgb(25, 84, 142)";

        try {
            const body = new URLSearchParams();
            body.append('text', text);

            const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/update?nodeId=${nodeId}`, {
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
    if (manageState.updateTimers[nodeId]) {
        clearTimeout(manageState.updateTimers[nodeId]);
        delete manageState.updateTimers[nodeId];
    }
    const statusEl = document.getElementById(`status-${nodeId}`) as HTMLElement | null;
    if (statusEl) statusEl.innerText = '删除中...';
    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/deleteNode?node_id=${nodeId}`, {
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
    // 先算出这份文档一共关联多少个分块，把数字放进确认文案——原来这行在
    // confirm() 之后才执行，用户点确认时根本看不到即将删除的规模，而
    // "删除整档"恰恰是一次性清空一份文档所有分块的高风险操作，最需要这个
    // 数字。
    const docNodes = allNodesList.filter(n => n.doc_id === docId);
    if (!confirm(`确定要彻底删除文档 "${docId}" 吗？这会删掉它的全部 ${docNodes.length} 个分块，此操作不可逆！`)) {
        return;
    }
    docNodes.forEach(node => {
        if (manageState.updateTimers[node.node_id!]) {
            clearTimeout(manageState.updateTimers[node.node_id!]);
            delete manageState.updateTimers[node.node_id!];
        }
    });
    try {
        const response = await apiFetch(`${baseURL}/${manageState.currentActiveIndex}/deleteDoc?doc_id=${docId}`, {
            method: 'POST'
        });
        const data = await response.json();
        if (response.ok && data.status === 'deleted') {
            showToast('整档文件及其所有分块已成功清除', 'success');
            // 重新请求后端，以防有其它关联节点
            await loadIndexNodes(manageState.currentActiveIndex!);
        } else {
            showToast(data.message || '删除整档文件失败', 'error');
        }
    } catch (error) {
        showToast('网络错误，删除整档失败', 'error');
    }
}
