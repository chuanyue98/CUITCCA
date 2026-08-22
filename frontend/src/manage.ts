// ===== 知识库管理页面逻辑 (manage.html) =====
// 依赖: sidebar.ts 已在上方加载
//
// 本文件只是入口/装配层：各功能面板的实现按职责拆在 src/manage/ 下——
//   state.ts       共享状态（当前索引、防抖定时器）
//   indexPanel.ts  索引列表 / 切换 / 新建 / 删除 / 持久化
//   summary.ts     索引摘要的加载与防抖自动保存
//   uploadPanel.ts 文件上传 / 直接文本 / QA 生成式导入
//   nodesPanel.ts  节点列表的搜索、分页、行内编辑与删除

import {
    bindIndexSelect,
    createNewIndex,
    deleteCurrentIndex,
    loadIndexes,
    saveCurrentIndexDisk,
} from "./manage/indexPanel";
import { bindSummaryInput } from "./manage/summary";
import { initDragZone, submitDirectText, submitQAGeneration } from "./manage/uploadPanel";
import {
    bindNodeSearch,
    changePageSize,
    firstPage,
    jumpToPageFromInput,
    lastPage,
    nextPage,
    prevPage,
} from "./manage/nodesPanel";

// Tab 切换逻辑
function switchTab(tabId: string) {
    document.querySelectorAll('.tab_btn').forEach((btn: Element) => btn.classList.remove('active'));
    document.querySelectorAll('.tab_content').forEach((content: Element) => content.classList.remove('active'));

    const activeBtn = Array.from(document.querySelectorAll('.tab_btn')).find(btn => btn.getAttribute('data-tab') === tabId);
    if (activeBtn) activeBtn.classList.add('active');

    const content = document.getElementById(tabId);
    if (content) content.classList.add('active');
}

// 模块脚本是 deferred 的，执行到这里时 DOM 已解析完成，但DOMContentLoaded
// 尚未触发；沿用原来的时机语义（在 DOMContentLoaded 里做初次加载与绑定）。
window.addEventListener('DOMContentLoaded', () => {
    loadIndexes();
    initDragZone();
});

document.addEventListener('DOMContentLoaded', () => {
  bindIndexSelect();
  bindNodeSearch();
  bindSummaryInput();
  document.querySelector('.btn_save_disk')?.addEventListener('click', saveCurrentIndexDisk);
  document.querySelector('.btn-success')?.addEventListener('click', createNewIndex);
  document.querySelector('.btn-danger')?.addEventListener('click', deleteCurrentIndex);
  document.querySelectorAll('.tab_btn').forEach(btn => {
    const tabId = btn.getAttribute('data-tab');
    if (tabId) btn.addEventListener('click', () => switchTab(tabId));
  });
  document.getElementById('drag-zone')?.addEventListener('click', () => {
    document.getElementById('file-input')?.click();
  });
  document.querySelector('.btn-submit')?.addEventListener('click', submitDirectText);
  document.querySelector('.btn-submit-qa')?.addEventListener('click', submitQAGeneration);
  document.getElementById('btn-prev-page')?.addEventListener('click', prevPage);
  document.getElementById('btn-next-page')?.addEventListener('click', nextPage);
  document.getElementById('btn-first-page')?.addEventListener('click', firstPage);
  document.getElementById('btn-last-page')?.addEventListener('click', lastPage);
  document.getElementById('btn-jump-page')?.addEventListener('click', jumpToPageFromInput);
  document.getElementById('page-jump-input')?.addEventListener('keydown', (e: Event) => {
    if ((e as KeyboardEvent).key === 'Enter') jumpToPageFromInput();
  });
  document.getElementById('page-size-select')?.addEventListener('change', (e: Event) => {
    const val = parseInt((e.target as HTMLSelectElement).value, 10);
    if (Number.isFinite(val) && val > 0) changePageSize(val);
  });
});
