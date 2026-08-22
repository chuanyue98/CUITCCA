// vitest setupFiles：补齐测试环境里的 localStorage。
//
// node >= 22.4 会在 globalThis 上挂一个实验性的 localStorage getter（未加
// --localstorage-file 启动参数时求值为 undefined），vitest 装载 happy-dom
// 环境时不会覆盖已存在的全局键，于是测试里拿到的是 undefined 而不是
// happy-dom 的实现。CI runner 与本地新版 node 都会命中。这里在环境装载后
// 补一个语义等价的内存实现（Storage 接口）。
if (typeof globalThis.localStorage === 'undefined' || globalThis.localStorage === null) {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(String(key), String(value));
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage,
    configurable: true,
    writable: true,
  });
}
