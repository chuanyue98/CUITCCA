// ===== 引用来源（参考来源列表）：流式回答结束后向 /graph/query_sources 取证 =====

import { apiFetch } from '../utils/api';

export async function loadCitations(citationsEl: HTMLElement) {
    try {
        const response = await apiFetch('/graph/query_sources', { method: 'POST' });
        if (!response.ok) return;
        const data = await response.json();
        const nodes = (data.source_nodes || []).filter((n: { text?: string }) => n && n.text);
        if (nodes.length === 0) return;

        citationsEl.innerHTML = '';
        const toggle = document.createElement('button');
        toggle.className = 'citations_toggle';
        toggle.type = 'button';
        toggle.textContent = `参考来源 (${nodes.length})`;
        const list = document.createElement('div');
        list.className = 'citations_list is-hidden';
        nodes.forEach((node: { text: string; file_name?: string | null; score?: number | null }) => {
            const item = document.createElement('div');
            item.className = 'citation_item';
            // 头部：来源文件名 + 相关度分数（/graph/query_sources 返回的
            // score 是重排后的 cross-encoder 分数，能直观看出"这条依据有多
            // 可信"；检索质量的透明是 RAG demo 的核心看点）。
            const head = document.createElement('div');
            head.className = 'citation_head';
            const source = node.file_name || '未知来源';
            const scoreText =
                typeof node.score === 'number' && Number.isFinite(node.score)
                    ? '相关度 ' + node.score.toFixed(3)
                    : '';
            head.textContent = [source, scoreText].filter(Boolean).join(' · ');
            item.appendChild(head);
            const snippet = document.createElement('div');
            snippet.textContent = node.text.length > 200 ? node.text.slice(0, 200) + '…' : node.text;
            item.appendChild(snippet);
            // 复制按钮：复制的是**完整**原文，不是上面截断到 200 字的展示片段
            // ——核对信息时要的是全文。
            const copyBtn = document.createElement('button');
            copyBtn.className = 'citation_copy_btn';
            copyBtn.type = 'button';
            copyBtn.title = '复制';
            copyBtn.textContent = '📋';
            copyBtn.addEventListener('click', () => {
                navigator.clipboard?.writeText(node.text).then(() => {
                    copyBtn.textContent = '✓';
                    setTimeout(() => { copyBtn.textContent = '📋'; }, 1200);
                }).catch(() => { /* 静默 */ });
            });
            item.appendChild(copyBtn);
            list.appendChild(item);
        });
        toggle.addEventListener('click', () => list.classList.toggle('is-hidden'));
        citationsEl.appendChild(toggle);
        citationsEl.appendChild(list);
        citationsEl.classList.remove('is-hidden');
    } catch (e) {
        // 引用来源是增强信息，静默失败不影响主对话
    }
}
