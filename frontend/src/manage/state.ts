// ===== manage 页各面板共享的可变状态 =====
// 拆分前这些都是 manage.ts 里的模块级 let/对象；拆分后由本模块统一持有，
// 各面板 import 同一对象实例读写，避免出现两份各自漂移的副本。

export const baseURL = '/index';
export const LAST_INDEX_KEY = 'cuitcca_last_index_v1';

export const manageState = {
    /** 当前选中的活跃索引（null = 无） */
    currentActiveIndex: null as string | null,
    /** 摘要编辑的防抖保存定时器 */
    summaryUpdateTimer: null as ReturnType<typeof setTimeout> | null,
    /** 各节点编辑的防抖保存定时器（key = node_id） */
    updateTimers: {} as Record<string, ReturnType<typeof setTimeout>>,
};

// 检查是否有未保存的节点编辑（用于切换索引前的二次确认）
export function hasUnsavedNodeEdits(): boolean {
    return Object.keys(manageState.updateTimers).length > 0 || !!manageState.summaryUpdateTimer;
}

/** 清掉摘要/节点所有挂起的防抖保存（切换索引、重载列表前调用，
 *  原来这段 clear 循环在 loadIndexes 和 select change 里复制了两份）。 */
export function clearPendingEdits() {
    if (manageState.summaryUpdateTimer) {
        clearTimeout(manageState.summaryUpdateTimer);
        manageState.summaryUpdateTimer = null;
    }
    for (const timerId in manageState.updateTimers) {
        clearTimeout(manageState.updateTimers[timerId]);
    }
    manageState.updateTimers = {};
}
