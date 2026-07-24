# Frontend Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Vite + TypeScript dev/build layer on top of the existing static frontend without changing runtime behavior.

**Architecture:** Keep the existing HTML/CSS/JS page structure and API contracts. Introduce Vite as a dev server and bundler, convert JS to TS for type safety, and add a production build step that outputs to `backend/app/static/` for FastAPI to serve.

**Tech Stack:** Vite, TypeScript, `@types/node`

## Global Constraints

- Do not rewrite business logic in chat.js / manage.js / feedback.js / sidebar.js.
- Keep the page structure and CSS architecture the same.
- Playwright e2e tests must continue to pass after the build tooling is added.
- The FastAPI app must continue serving the frontend with no extra runtime dependency.
- Python lint/typecheck/test (`make lint`, `make typecheck`, `make test`) must remain green.

---

### Task 1: Scaffold Vite + TypeScript in frontend/

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`

**Interfaces:**
- Consumes: None
- Produces: Vite project scaffold with dev server and build pipeline

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "cuitcca-frontend",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "@types/node": "^22.0.0"
  }
}
```

- [ ] **Step 2: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  publicDir: 'vendor',
  build: {
    outDir: resolve(__dirname, '../backend/app/static'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        manage: resolve(__dirname, 'manage.html'),
        use_function: resolve(__dirname, 'use_function.html'),
        feed_back: resolve(__dirname, 'feed_back.html'),
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
  server: {
    proxy: {
      '/graph': 'http://localhost:8522',
      '/index': 'http://localhost:8522',
      '/response': 'http://localhost:8522',
      '/manage': 'http://localhost:8522',
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
});
```

- [ ] **Step 4: Create `frontend/src/` directory and `frontend/src/types/api.ts`**

```ts
export interface QueryResponse {
  answer: string;
  source_nodes?: Array<{
    text: string;
    node_id?: string;
    doc_id?: string;
  }>;
}

export interface UploadResponse {
  status: string;
  message?: string;
}

export interface FeedbackRequest {
  email: string;
  message: string;
}

export interface IndexListResponse {
  indexes: string[];
}

export interface StatsResponse {
  total_visits: number;
  user_visits: Record<string, number>;
  endpoint_visits: Record<string, number>;
  ip_count: number;
}
```

- [ ] **Step 5: Create `frontend/index.html` (Vite entry for chat page)**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="./icon.png" type="image/x-icon">
  <link rel="stylesheet" href="./style.css">
  <title>成信大校园助手</title>
</head>
<body>
  <div class="outline">
    <nav id="side_left" aria-label="主导航"></nav>
    <main class="side_right">
      <header class="headline">
        <div class="headline_hidemenu">
          <button id="button">
            <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
            </svg>
          </button>
        </div>
        <div class="headline_head">校园问答助手</div>
        <div class="share"></div>
      </header>
      <div class="talk_outline">
        <div class="talk_outlinein">
          <div class="talk_content" id="chatbox" aria-live="polite" aria-label="对话记录">
            <div class="message bot">
              <div class="content_bot_img"></div>
              <div class="content_bot">你好！我是成信大校园助手，你可以问我关于学校的任何问题，比如：学校有哪些社团？图书馆怎么借书？</div>
            </div>
          </div>
          <div class="chat_bottom"></div>
          <footer class="foot_fix">
            <div class="chat_container">
              <button class="clear" onclick="clearAllMessage()" title="清空对话" aria-label="清空对话">
                <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-trash3" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M6.5 1h3a.5.5 0 0 1 .5.5v1H6v-1a.5.5 0 0 1 .5-.5ZM11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3A1.5 1.5 0 0 0 5 1.5v1H2.506a.58.58 0 0 0-.01 0H1.5a.5.5 0 0 0 0 1h.538l.853 10.66A2 2 0 0 0 4.885 16h6.23a2 2 0 0 0 1.994-1.84l.853-10.66h.538a.5.5 0 0 0 0-1h-.995a.59.59 0 0 0-.01 0H11Zm1.958 1-.846 10.58a1 1 0 0 1-.997.92h-6.23a1 1 0 0 1-.997-.92L3.042 3.5h9.916Zm-7.487 1a.5.5 0 0 1 .528.47l.5 8.5a.5.5 0 0 1-.998.06L5 5.03a.5.5 0 0 1 .47-.53Zm5.058 0a.5.5 0 0 1 .47.53l-.5 8.5a.5.5 0 1 1-.998-.06l.5-8.5a.5.5 0 0 1 .528-.47ZM8 4.5a.5.5 0 0 1 .5.5v8a.5.5 0 0 1-1 0V5a.5.5 0 0 1 .5-.5Z"/>
                </svg>
              </button>
              <div class="chat_talk_container" id="changeborder_div">
                <div class="chat_textarea">
                  <div class="textarea">
                    <textarea name="" id="input" cols="10" rows="1" aria-label="输入问题" placeholder="输入你的问题..."></textarea>
                  </div>
                </div>
                <button class="chat_talk_stop is-hidden" id="stop-generating" onclick="stopGenerating()" title="停止生成" aria-label="停止生成">■</button>
                <button class="chat_talk_submit" id="submit" onclick="sendMessage()" aria-label="发送">&#10140</button>
              </div>
            </div>
          </footer>
        </div>
      </div>
    </main>
  </div>

  <script type="module" src="./src/chat.ts"></script>
  <script type="module" src="./src/sidebar.ts"></script>
</body>
</html>
```

- [ ] **Step 6: Run `npm install` in `frontend/` and verify `vite` starts**

```bash
cd frontend && npm install && npm run dev
```

Expected: Vite dev server starts on `http://localhost:5173` and proxies API requests to `http://localhost:8522`.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/src/types/api.ts frontend/index.html
git commit -m "feat: scaffold Vite + TypeScript frontend build pipeline"
```

---

### Task 2: Convert JS files to TS and wire them into Vite

**Files:**
- Create: `frontend/src/sidebar.ts`
- Create: `frontend/src/chat.ts`
- Create: `frontend/src/manage.ts`
- Create: `frontend/src/feedback.ts`
- Create: `frontend/src/use_function.ts`
- Create: `frontend/src/feed_back.ts`
- Modify: `frontend/manage.html`
- Modify: `frontend/feed_back.html`
- Modify: `frontend/use_function.html`

**Interfaces:**
- Consumes: `frontend/src/types/api.ts`
- Produces: TypeScript entry points for each page

- [ ] **Step 1: Create `frontend/src/sidebar.ts` (rename from `sidebar.js`)**

```ts
/**
 * 公共侧边栏组件
 * 在每个页面中通过 <div id="side_left"></div> + <script type="module" src="./src/sidebar.ts" data-active="index"></script> 引入
 * data-active 属性指定当前页面的高亮菜单项: index | manage | use_function | feed_back
 */

(function () {
  const activePage = (document.currentScript && document.currentScript.getAttribute('data-active')) || '';

  const sidebarHTML = '\
      <div class="side_left_flex">\
          <div class="head_left">\
              <div class="head_logo">\
                  <img src="./logo.png" alt="Logo">\
              </div>\
              <div class="head_font">成信大校园助手</div>\
          </div>\
          <div class="side_menu">\
              <div class="menu_mid">\
                  <div class="menu_mid1">\
                      <a href="./manage.html" title="管理 & 增加">\
                          <div class="func"' + (activePage === 'manage' ? ' style="border-radius: 20px; box-shadow: 0 4px 15px rgba(25, 84, 142, 0.15); border-color: rgba(25, 84, 142, 0.2);"' : '') + '>\
                              <div class="img" style="color: ' + (activePage === 'manage' ? 'rgb(25, 84, 142)' : '#666') + ';">\
                                  <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-house-add" viewBox="0 0 16 16" aria-hidden="true" focusable="false">\
                                      <path d="M8.707 1.5a1 1 0 0 0-1.414 0L.646 8.146a.5.5 0 0 0 .708.708L2 8.207V13.5A1.5 1.5 0 0 0 3.5 15h4a.5.5 0 1 0 0-1h-4a.5.5 0 0 1-.5-.5V7.207l5-5 6.646 6.647a.5.5 0 0 0 .708-.708L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.707 1.5Z"/>\
                                      <path fill-rule="evenodd" d="M16 12.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Zm-3.5-2a.5.5 0 0 1 .5.5v1h1a.5.5 0 0 1 0 1h-1v1a.5.5 0 1 1-1 0v-1h-1a.5.5 0 1 1 0-1h1v-1a.5.5 0 0 1 .5-.5Z"/>\
                                  </svg>\
                              </div>\
                              <div style="font-size: 13px;' + (activePage === 'manage' ? ' font-weight: 500; color: rgb(25, 84, 142);' : ' color: #666;') + '">知识库管理</div>\
                          </div>\
                      </a>\
                  </div>\
                  <div class="menu_mid2">\
                      <a href="./use_function.html" title="食用指南">\
                          <div class="func"' + (activePage === 'use_function' ? ' style="border-radius: 20px; box-shadow: 0 4px 15px rgba(25, 84, 142, 0.15); border-color: rgba(25, 84, 142, 0.2);"' : '') + '>\
                              <div class="img" style="color: ' + (activePage === 'use_function' ? 'rgb(25, 84, 142)' : '#666') + ';">\
                                  <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-compass" viewBox="0 0 16 16" aria-hidden="true" focusable="false">\
                                      <path d="M8 16.016a7.5 7.5 0 0 0 1.962-14.74A1 1 0 0 0 9 0H7a1 1 0 0 0-.962 1.276A7.5 7.5 0 0 0 8 16.016zm6.5-7.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z"/>\
                                      <path d="m6.94 7.44 4.95-2.83-2.83 4.95-4.949 2.83 2.828-4.95z"/>\
                                  </svg>\
                              </div>\
                              <div style="font-size: 13px;' + (activePage === 'use_function' ? ' font-weight: 500; color: rgb(25, 84, 142);' : ' color: #666;') + '">使用指南</div>\
                          </div>\
                      </a>\
                  </div>\
              </div>\
  \
              <a href="./index.html">\
                  <div class="menu_item_row' + (activePage === 'index' ? ' active' : '') + '">\
                      <div class="img">\
                          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-chat-quote" viewBox="0 0 16 16" aria-hidden="true" focusable="false">\
                              <path d="M2.678 11.894a1 1 0 0 1 .287.801 10.97 10.97 0 0 1-.398 2c1.395-.323 2.247-.697 2.634-.893a1 1 0 0 1 .71-.074A8.06 8.06 0 0 0 8 14c3.996 0 7-2.807 7-6 0-3.192-3.004-6-7-6S1 4.808 1 8c0 1.468.617 2.83 1.678 3.894zm-.493 3.905a21.682 21.682 0 0 1-.713.129c-.2.032-.352-.176-.273-.362a9.68 9.68 0 0 0 .244-.637l.003-.01c.248-.72.45-1.548.524-2.319C.743 11.37 0 9.76 0 8c0-3.866 3.582-7 8-7s8 3.134 8 7-3.582 7-8 7a9.06 9.06 0 0 1-2.347-.306c-.52.263-1.639.742-3.468 1.105z"/>\
                              <path d="M7.066 6.76A1.665 1.665 0 0 0 4 7.668a1.667 1.667 0 0 0 2.561 1.406c-.131.389-.375.804-.777 1.22a.417.417 0 0 0 .6.58c1.486-1.54 1.293-3.214.682-4.112zm4 0A1.665 1.665 0 0 0 8 7.668a1.667 1.667 0 0 0 2.561 1.406c-.131.389-.375.804-.777 1.22a.417.417 0 0 0 .6.58c1.486-1.54 1.293-3.214.682-4.112z"/>\
                          </svg>\
                      </div>\
                      <div class="menu_font_row">智能聊天</div>\
                  </div>\
              </a>\
  \
              <a href="./feed_back.html">\
                  <div class="menu_item_row' + (activePage === 'feed_back' ? ' active' : '') + '">\
                      <div class="img">\
                          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-stack-overflow" viewBox="0 0 16 16" aria-hidden="true" focusable="false">\
                              <path d="M12.412 14.572V10.29h1.428V16H1v-5.71h1.428v4.282h9.984z"/>\
                              <path d="M3.857 13.145h7.137v-1.428H3.857v1.428zM10.254 0 9.108.852l4.26 5.727 1.146-.852L10.254 0zm-3.54 3.377 5.484 4.567.913-1.097L7.627 2.28l-.914 1.097zM4.922 6.55l6.47 3.013.603-1.294-6.47-3.013-.603 1.294zm-.925 3.344 6.985 1.469.294-1.398-6.985-1.468-.294 1.397z"/>\
                          </svg>\
                      </div>\
                      <div class="menu_font_row">问题反馈</div>\
                  </div>\
              </a>\
          </div>\
      </div>';

  const container = document.getElementById('side_left');
  if (container) {
    container.innerHTML = sidebarHTML;
  }

  // 侧边栏折叠逻辑
  const button = document.getElementById('button');
  if (button) {
    function adjustSidebar() {
      if (window.innerWidth < 1024) {
        button.style.display = 'block';
        container.style.display = 'none';
      } else {
        button.style.display = 'none';
        container.style.display = 'block';
      }
    }

    window.addEventListener('resize', adjustSidebar);
    button.addEventListener('click', function () {
      container.style.display = (container.style.display === 'none' || container.style.display === '') ? 'block' : 'none';
    });
    adjustSidebar();
  }
})();
```

- [ ] **Step 2: Create `frontend/src/chat.ts` (rename from `chat.js`)**

Copy `frontend/chat.js` to `frontend/src/chat.ts` with these changes:
- Change `const`/`let`/`function` declarations to be module-scoped (already are).
- Add `/// <reference types="vite/client" />` at the top if needed for asset imports (not needed here).
- No API shape changes needed; TypeScript will infer types from usage.

- [ ] **Step 3: Create `frontend/src/manage.ts` (rename from `manage.js`)**

Copy `frontend/manage.js` to `frontend/src/manage.ts`.

- [ ] **Step 4: Create `frontend/src/feedback.ts` (rename from `feedback.js`)**

Copy `frontend/feedback.js` to `frontend/src/feedback.ts`.

- [ ] **Step 5: Create `frontend/src/use_function.ts` (new, empty stub for `use_function.html`)**

```ts
// use_function.html is static content only; no JS logic needed yet.
```

- [ ] **Step 6: Create `frontend/src/feed_back.ts` (rename from inline scripts in `feed_back.html`)**

The current `feed_back.html` loads `feedback.js` globally. Move that logic to `feed_back.ts` as a module. Remove the inline `onclick="submitFeedback()"` from the HTML and wire it up in the TS file:

```ts
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('feedbackButton');
  if (btn) {
    btn.addEventListener('click', submitFeedback);
  }
});
```

- [ ] **Step 7: Update `frontend/manage.html` script tags**

Replace:
```html
<script src="./sidebar.js" data-active="manage"></script>
<script src="./manage.js"></script>
```
With:
```html
<script type="module" src="./src/sidebar.ts" data-active="manage"></script>
<script type="module" src="./src/manage.ts"></script>
```

- [ ] **Step 8: Update `frontend/feed_back.html` script tags**

Replace:
```html
<script src="./sidebar.js" data-active="feed_back"></script>
<script src="./feedback.js"></script>
```
With:
```html
<script type="module" src="./src/sidebar.ts" data-active="feed_back"></script>
<script type="module" src="./src/feed_back.ts"></script>
```

- [ ] **Step 9: Update `frontend/use_function.html` script tag**

Replace:
```html
<script src="./sidebar.js" data-active="use_function"></script>
```
With:
```html
<script type="module" src="./src/sidebar.ts" data-active="use_function"></script>
```

- [ ] **Step 10: Verify `npm run build` succeeds and `backend/app/static/` contains bundled assets**

```bash
cd frontend && npm run build
```

Expected: `backend/app/static/assets/` contains bundled JS, and `backend/app/static/*.html` contains the entry HTML files.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/ frontend/manage.html frontend/feed_back.html frontend/use_function.html
git rm --cached frontend/chat.js frontend/manage.js frontend/feedback.js frontend/sidebar.js 2>/dev/null || true
git commit -m "feat: convert frontend JS to TypeScript and wire into Vite"
```

---

### Task 3: Update FastAPI static file serving and Makefile

**Files:**
- Modify: `backend/app/main.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: Vite build output at `backend/app/static/`
- Produces: Production static serving + Makefile targets for frontend

- [ ] **Step 1: Modify `backend/app/main.py` static file mount**

Replace:
```python
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')
if os.path.isdir(frontend_dir):
    app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")
```

With:
```python
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')

if os.path.isdir(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir, html=True), name="web")
elif os.path.isdir(frontend_dir):
    app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")
```

- [ ] **Step 2: Add frontend targets to `Makefile`**

```makefile
.PHONY: frontend-install frontend-dev frontend-build

frontend-install: ## 安装前端依赖
	cd frontend && npm install

frontend-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

frontend-build: ## 构建前端生产产物
	cd frontend && npm run build
```

- [ ] **Step 3: Run `make lint`, `make typecheck`, `make test` to verify no regressions**

```bash
make lint && make typecheck && make test
```

Expected: All pass with coverage >= 90%.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py Makefile
git commit -m "feat: serve built frontend assets from backend/static and add Makefile targets"
```

---

### Task 4: Clean up Playwright git pollution

**Files:**
- Modify: `.gitignore` (if needed)
- Modify: git history (BFG or filter-branch)

**Interfaces:**
- Consumes: `tests/playwright/package.json` and its committed `node_modules`
- Produces: Clean git history without committed `node_modules`

- [ ] **Step 1: Verify `tests/playwright/package.json` is the only committed Node artifact**

```bash
git ls-files tests/playwright/ | head -20
```

- [ ] **Step 2: Add `tests/playwright/node_modules/` to `.gitignore` if not already present**

- [ ] **Step 3: Remove `node_modules` from git history using BFG or filter-repo**

```bash
# Using git filter-repo (preferred)
git filter-repo --path tests/playwright/node_modules --invert-paths
```

Or with BFG:
```bash
bfg --delete-folders tests/playwright/node_modules
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
```

- [ ] **Step 4: Commit and push the cleanup**

```bash
git add .gitignore
git commit -m "chore: remove committed playwright node_modules from git history"
```

---

## Verification Checklist

- [ ] `make lint` passes
- [ ] `make typecheck` passes
- [ ] `make test` passes with coverage >= 90%
- [ ] `make frontend-dev` starts Vite on port 5173 and chat page loads
- [ ] `make frontend-build` produces `backend/app/static/` assets
- [ ] Playwright e2e tests pass against built assets
- [ ] FastAPI serves `/web/` correctly in production mode
