# 前端页面风格统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `index.html`、`use_function.html`、`feed_back.html` 三个页面的视觉风格统一到 `manage.html` 的现代设计语言，并通过 `frontend/style.css` 提取公共样式。

**Architecture:** 提取 `manage.html` 中全局 CSS 到 `frontend/style.css`，四个页面均引用该文件；每个页面保留自己特有的内容和页面专属 CSS，但侧栏 HTML 结构、顶栏 HTML 结构、背景、字体、基础交互等完全统一。

**Tech Stack:** 纯 HTML/CSS/JS，无框架。

## Global Constraints

- 所有页面在 `frontend/` 目录下，`style.css` 引用路径为 `./style.css`
- `manage.html` 作为风格基准，不动其功能逻辑
- 其他三个页面的 JavaScript 逻辑**严格不动**
- 页面侧栏菜单的 `.active` 高亮态需匹配当前所在页面
- 顶栏标题文字按页面区分：聊天页 → "测试版小助手"，指南页 → "使用指南"，反馈页 → "问题反馈"，管理页 → "知识库管理工作台"
- 浏览器打开后目视对比确认风格统一

---

### Task 1: 提取公共 CSS 到 `frontend/style.css`

**Files:**
- Create: `frontend/style.css`

从 `manage.html` 的 `<style>` 块中提取以下公共 CSS（约 380 行）到 `style.css`：

- [ ] **Step 1: 提取公共 CSS 内容**

将 `manage.html` 的以下样式完整复制到 `style.css` 中：

```css
/* 全局基础样式与字体 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght:300;400;500;600;700&family=Outfit:wght:300;400;500;600;700&display=swap');

* {
    box-sizing: border-box;
    font-family: 'Inter', 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    margin: 0;
    padding: 0;
    font-size: 15px;
}

body, html {
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: linear-gradient(135deg, #f4f6fc 0%, #eef2fa 100%);
}

.outline {
    display: flex;
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: flex-start;
}

#side_left {
    display: none;
    border-right: 1px solid rgba(25, 84, 142, 0.1);
    width: 300px;
    height: 100%;
    background-color: white;
    flex-shrink: 0;
    box-shadow: 2px 0 10px rgba(0, 0, 0, 0.02);
    transition: all 0.3s ease;
}

.side_left_flex {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
}

.head_left {
    display: flex;
    align-items: center;
    flex-wrap: nowrap;
    border-bottom: 1px solid rgba(209, 209, 209, 0.3);
    background-color: #fafbfc;
    width: 100%;
    height: 60px;
    padding: 10px 20px;
}

.head_logo {
    border-radius: 10px;
    width: 50px;
    height: 35px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}

.head_logo img {
    width: 100%;
    height: auto;
}

.head_font {
    flex-grow: 1;
    font-size: 18px;
    font-weight: 700;
    color: rgb(25, 84, 142);
    padding-left: 15px;
}

.side_menu {
    display: flex;
    flex-grow: 1;
    width: 100%;
    flex-direction: column;
    background-color: white;
    overflow-y: auto;
    padding: 20px 10px;
}

.menu_mid {
    display: flex;
    flex-wrap: nowrap;
    width: 100%;
    margin-bottom: 15px;
    gap: 10px;
}

.menu_mid1, .menu_mid2 {
    flex: 1;
}

.menu_mid a {
    text-decoration: none;
    display: block;
}

.func {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 90px;
    border-radius: 16px;
    background-color: white;
    border: 1px solid rgba(25, 84, 142, 0.1);
    transition: all 0.3s ease;
    cursor: pointer;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.02);
}

.func:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(25, 84, 142, 0.1);
    border-color: rgba(25, 84, 142, 0.3);
}

.func .img {
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.side_menu a {
    text-decoration: none;
    margin-bottom: 10px;
    display: block;
}

.menu_item_row {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 12px 18px;
    border-radius: 12px;
    color: #555;
    transition: all 0.2s ease;
    border: 1px solid transparent;
}

.menu_item_row:hover {
    background-color: rgba(25, 84, 142, 0.05);
    color: rgb(25, 84, 142);
}

.menu_item_row.active {
    background-color: rgba(25, 84, 142, 0.1);
    color: rgb(25, 84, 142);
    font-weight: 600;
    border: 1px solid rgba(25, 84, 142, 0.15);
}

.menu_item_row .img {
    margin-right: 15px;
    display: flex;
    align-items: center;
}

.menu_font_row {
    font-size: 15px;
}

.side_right {
    display: flex;
    flex-direction: column;
    flex-grow: 1;
    height: 100%;
    background-color: transparent;
    overflow: hidden;
    position: relative;
}

.headline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    height: 60px;
    background-color: white;
    border-bottom: 1px solid rgba(209, 209, 209, 0.3);
    padding: 0 20px;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.01);
    flex-shrink: 0;
}

.headline_hidemenu button {
    background: none;
    border: none;
    cursor: pointer;
    color: rgb(25, 84, 142);
    display: flex;
    align-items: center;
    padding: 5px;
    border-radius: 8px;
    transition: background-color 0.2s;
}

.headline_hidemenu button:hover {
    background-color: #f0f2f5;
}

.headline_head {
    font-size: 18px;
    font-weight: 700;
    color: #333;
}

.share {
    width: 50px;
}

.glass_card {
    background: rgba(255, 255, 255, 0.9);
    border-radius: 20px;
    border: 1px solid rgba(25, 84, 142, 0.1);
    padding: 20px;
    box-shadow: 0 8px 24px rgba(31, 38, 135, 0.03);
    backdrop-filter: blur(8px);
}

/* Toast 样式 */
#toast-container {
    position: fixed;
    bottom: 25px;
    right: 25px;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.toast {
    padding: 15px 25px;
    border-radius: 12px;
    color: white;
    font-weight: 500;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
    transform: translateY(20px);
    opacity: 0;
    transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    display: flex;
    align-items: center;
    min-width: 250px;
}

.toast.show {
    transform: translateY(0);
    opacity: 1;
}

.toast-success { background: linear-gradient(135deg, #52c41a, #73d13d); }
.toast-error { background: linear-gradient(135deg, #ff4d4f, #ff7875); }
.toast-info { background: linear-gradient(135deg, #1890ff, #40a9ff); }

/* 全局加载遮罩 */
#loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 99999;
    flex-direction: column;
    gap: 15px;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.3s ease, visibility 0.3s ease;
}

.spinner {
    width: 50px;
    height: 50px;
    border: 5px solid rgba(25, 84, 142, 0.1);
    border-top: 5px solid rgb(25, 84, 142);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.loading-text {
    font-size: 16px;
    font-weight: 600;
    color: rgb(25, 84, 142);
}

/* 响应式 */
@media (max-width: 1024px) {
    .dashboard_container {
        flex-direction: column;
        overflow-y: auto;
    }
    .panel_left, .panel_right {
        width: 100%;
        height: auto;
        overflow: visible;
    }
    .panel_right {
        height: 500px;
    }
}
```

- [ ] **Step 2: 验证文件创建**
  - 检查 `frontend/style.css` 是否存在，CSS 语法是否正确

- [ ] **Step 3: Commit**
  ```bash
  git add frontend/style.css
  git commit -m "style: extract common CSS from manage.html to shared style.css"
  ```

---

### Task 2: 更新 `manage.html` 引用 `style.css`

**Files:**
- Modify: `frontend/manage.html`

- [ ] **Step 1: 在 `<head>` 中添加 `style.css` 引用**

在 `<link rel="icon" href="./icon.png" type="image/x-icon">` 之后添加：
```html
<link rel="stylesheet" href="./style.css">
```

- [ ] **Step 2: 从 `<style>` 块中移除已提取到 `style.css` 的公共 CSS**

移除以下部分（已在 `style.css` 中）：
- 全局基础样式（`@import`、`*`、`body, html`、`.outline`）
- 侧栏样式（`#side_left`、`.side_left_flex`、`.head_left`、`.head_logo`、`.head_font`、`.side_menu`、`.menu_mid`、`.menu_mid1`、`.menu_mid2`、`.func`、`.menu_item_row`、`.menu_font_row`）
- 右侧容器（`.side_right`）
- 顶栏（`.headline`、`.headline_hidemenu`、`.headline_head`、`.share`）
- `.glass_card`
- Toast 样式（`#toast-container`、`.toast` 及其变体）
- Loading 遮罩（`#loading-overlay`、`.spinner`、`.loading-text`）
- 响应式 `@media`

保留 `<style>` 块中页面特有的部分：
- `.dashboard_container`、`.panel_left`、`.panel_right`（工作区布局）
- `.tabs_header`、`.tab_btn`、`.tab_content`（Tab 切换）
- `.drag_zone`（拖拽上传区）
- `.form_group`、`.btn-submit`（表单元素）
- `.node_card`、`.node_meta_row`、`.node_doc_id`、`.node_editor`、`.node_actions`、`.node_status_tag`、`.btn-delete-node`、`#pagination-bar`（节点管理）
- `#loading-overlay` 相关已在公共 CSS 中

- [ ] **Step 3: 验证 `manage.html` 页面正常**
  - 在浏览器中打开 `http://127.0.0.1:8001/web/manage.html` 确认样式未丢失

- [ ] **Step 4: Commit**
  ```bash
  git add frontend/manage.html
  git commit -m "style: update manage.html to reference shared style.css"
  ```

---

### Task 3: 更新 `index.html`（聊天页）统一风格

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 添加 `style.css` 引用**

在 `<head>` 中添加 `<link rel="stylesheet" href="./style.css">`，并移除旧 `<style>` 块中已提取到 `style.css` 的公共 CSS。

- [ ] **Step 2: 替换侧栏 HTML 为现代结构**

将旧侧栏（`<div id="side_left">` 下的内容）替换为以下结构：

```html
<div id="side_left">
    <div class="side_left_flex">
        <div class="head_left">
            <div class="head_logo">
                <img src="./logo.png" alt="Logo">
            </div>
            <div class="head_font">成信大校园助手</div>
        </div>
        <div class="side_menu">
            <div class="menu_mid">
                <div class="menu_mid1">
                    <a href="./manage.html" title="管理 & 增加">
                        <div class="func" style="border-radius: 20px; box-shadow: 0 4px 15px rgba(25, 84, 142, 0.15); border-color: rgba(25, 84, 142, 0.2);">
                            <div class="img" style="color: rgb(25, 84, 142);">
                                <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-house-add" viewBox="0 0 16 16">
                                    <path d="M8.707 1.5a1 1 0 0 0-1.414 0L.646 8.146a.5.5 0 0 0 .708.708L2 8.207V13.5A1.5 1.5 0 0 0 3.5 15h4a.5.5 0 1 0 0-1h-4a.5.5 0 0 1-.5-.5V7.207l5-5 6.646 6.647a.5.5 0 0 0 .708-.708L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.707 1.5Z"/>
                                    <path fill-rule="evenodd" d="M16 12.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Zm-3.5-2a.5.5 0 0 1 .5.5v1h1a.5.5 0 0 1 0 1h-1v1a.5.5 0 1 1-1 0v-1h-1a.5.5 0 1 1 0-1h1v-1a.5.5 0 0 1 .5-.5Z"/>
                                </svg>
                            </div>
                            <div style="font-size: 13px; font-weight: 500; color: rgb(25, 84, 142);">知识库管理</div>
                        </div>
                    </a>
                </div>
                <div class="menu_mid2">
                    <a href="./use_function.html" title="食用指南">
                        <div class="func">
                            <div class="img" style="color: #666;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-compass" viewBox="0 0 16 16">
                                    <path d="M8 16.016a7.5 7.5 0 0 0 1.962-14.74A1 1 0 0 0 9 0H7a1 1 0 0 0-.962 1.276A7.5 7.5 0 0 0 8 16.016zm6.5-7.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z"/>
                                    <path d="m6.94 7.44 4.95-2.83-2.83 4.95-4.949 2.83 2.828-4.95z"/>
                                </svg>
                            </div>
                            <div style="font-size: 13px; color: #666;">使用指南</div>
                        </div>
                    </a>
                </div>
            </div>
            
            <a href="./index.html">
                <div class="menu_item_row active">
                    <div class="img">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-chat-quote" viewBox="0 0 16 16">
                            <path d="M2.678 11.894a1 1 0 0 1 .287.801 10.97 10.97 0 0 1-.398 2c1.395-.323 2.247-.697 2.634-.893a1 1 0 0 1 .71-.074A8.06 8.06 0 0 0 8 14c3.996 0 7-2.807 7-6 0-3.192-3.004-6-7-6S1 4.808 1 8c0 1.468.617 2.83 1.678 3.894zm-.493 3.905a21.682 21.682 0 0 1-.713.129c-.2.032-.352-.176-.273-.362a9.68 9.68 0 0 0 .244-.637l.003-.01c.248-.72.45-1.548.524-2.319C.743 11.37 0 9.76 0 8c0-3.866 3.582-7 8-7s8 7-3.582 7-8 7a9.06 9.06 0 0 1-2.347-.306c-.52.263-1.639.742-3.468 1.105z"/>
                        </svg>
                    </div>
                    <div class="menu_font_row">智能聊天</div>
                </div>
            </a>
            
            <a href="./feed_back.html">
                <div class="menu_item_row">
                    <div class="img">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" class="bi bi-stack-overflow" viewBox="0 0 16 16">
                            <path d="M12.412 14.572V10.29h1.428V16H1v-5.71h1.428v4.282h9.984z"/>
                            <path d="M3.857 13.145h7.137v-1.428H3.857v1.428zM10.254 0 9.108.852l4.26 5.727 1.146-.852L10.254 0zm-3.54 3.377 5.484 4.567.913-1.097L7.627 2.28l-.914 1.097zM4.922 6.55l6.47 3.013.603-1.294-6.47-3.013-.603 1.294zm-.925 3.344 6.985 1.469.294-1.398-6.985-1.468-.294 1.397z"/>
                        </svg>
                    </div>
                    <div class="menu_font_row">问题反馈</div>
                </div>
            </a>
        </div>
    </div>
</div>
```

- [ ] **Step 3: 替换顶栏 HTML 为现代结构**

将旧顶栏（`<div class="headline">` 下的内容）替换为：

```html
<div class="headline">
    <div class="headline_hidemenu">
        <button id="button">
            <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
            </svg>
        </button>
    </div>
    <div class="headline_head">测试版小助手</div>
    <div class="share"></div>
</div>
```

- [ ] **Step 4: 更新 `<style>` 块**

保留聊天页面特有样式：`.talk_outline`、`.talk_outlinein`、`.talk_content`、`.foot_fix`、`.chat_container`、`.clear`、`.chat_talk_container`、`.chat_talk_submit`、`.chat_textarea`、`.textarea`、`textarea` 样式、`.message`、`.content_man`、`.content_bot`、`.content_man_img`、`.content_bot_img`、流式输出相关（`#chatbox`、`.cursor`、`@keyframes blink`、`.replycontent`）。

移除已公共化的：`*`、`.outline`、`#side_left`、`.side_left_flex`、`.side_right`、`.head_left`、`.head_logo`、`.head_font`、`.side_menu`、`.side_menu .img`、`.menu_bot_cuit`、`.side_menu::-webkit-scrollbar`、`.menu_mid`、`.menu_mid1`、`.menu_mid2`、`.menu_font`、`.func`、`.headline`、`.headline_hidemenu`、`#button`、`.headline_head`、`.headline_headin`、`.share`。

- [ ] **Step 5: 更新侧栏切换脚本**

将旧脚本替换为 manage.html 中的现代版本：

```javascript
const button = document.getElementById("button");
const div = document.getElementById("side_left");

function adjustSidebar() {
    if (window.innerWidth < 1024) {
        button.style.display = "block";
        div.style.display = "none";
    } else {
        button.style.display = "none";
        div.style.display = "block";
    }
}

window.addEventListener("resize", adjustSidebar);
button.addEventListener("click", function() {
    if (div.style.display === "none" || div.style.display === "") {
        div.style.display = "block";
    } else {
        div.style.display = "none";
    }
});
adjustSidebar();
```

- [ ] **Step 6: 验证 `index.html` 页面正常**
  - 聊天功能、侧栏切换、顶栏均正常

- [ ] **Step 7: Commit**
  ```bash
  git add frontend/index.html
  git commit -m "style: unify index.html (chat page) with modern design language"
  ```

---

### Task 4: 更新 `use_function.html`（使用指南页）统一风格

**Files:**
- Modify: `frontend/use_function.html`

- [ ] **Step 1: 添加 `style.css` 引用**

在 `<head>` 中添加 `<link rel="stylesheet" href="./style.css">`。

- [ ] **Step 2: 替换侧栏 HTML 为现代结构**

侧栏 HTML 结构同 Task 3 中的侧栏，但将 `.menu_item_row` 的 `active` 类移除（当前不在指南页），保留 `.menu_item_row` 不带 `active`。注意所有页面侧栏的 `active` 高亮只在本页面所在菜单项上添加。

- [ ] **Step 3: 替换顶栏 HTML 为现代结构**

```html
<div class="headline">
    <div class="headline_hidemenu">
        <button id="button">
            <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
            </svg>
        </button>
    </div>
    <div class="headline_head">使用指南</div>
    <div class="share"></div>
</div>
```

- [ ] **Step 4: 更新内容区**

使用指南文本区（当前在 `.feedback_textarea` 内）改为用 `.glass_card` 包裹，内容居中：

```html
<div class="talk_outline" style="flex-grow: 1; overflow-y: auto; padding: 30px;">
    <div class="glass_card">
        <!-- 原有内容保持不变，仅替换容器 -->
        <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;欢迎使用成信大校园助手！以下是一些简单的指南，帮助你更好地利用这个智能聊天机器人：</p>
        <p>1 . 温馨提示：当前版本属于 <strong>内测</strong> 阶段</p>
        <ul>
            <li>仅供成信大校内用户学习使用</li>
            <li>账号系统未完善，聊天页面清除即刷新页面，页面不会保留任何数据，后期会完善</li>
            <li>上下文关联未完善，聊天时一段对话相当于新回话，若想继续之前话题可将前面的对话内容复制作为新对话内容</li>
        </ul>
        <p>2 . 提问方式：</p>
        <ul>
            <li>您可以直接输入问题，如："学校有哪些社团？"、"如何申请图书馆借阅权限？"。</li>
            <li>您也可以使用关键词，如："社团"、"图书馆借阅"，助手会尽力理解你的需求并给出相关信息。</li>
            <li>若想继续对话，如第一段：提问"你是谁？" 回复:"我叫成信大校园助手。"，想要继续对话，输入："你是谁？我叫成信大校园助手。谁给你取的名字？"</li>
        </ul>
        <p>3 . 问题反馈</p>
        <ul>
            <li>如果有什么问题的话，请您一定要将问题反馈给我们</li>
        </ul>
        <br>
        <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;在后期规划中，成信大校园助手将会逐渐完善信息并增加功能。</p>
        <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;成信大校园助手将不断更新和完善，为您提供更好的服务。感谢您选择成信大校园助手，希望它能成为你校园生活中的得力助手！</p>
    </div>
</div>
```

- [ ] **Step 5: 更新 `<style>` 块**

保留页面特有样式，移除已公共化的样式（同 Task 3）。指南页的特有样式相对较少，主要是 `.talk_outline`、`.talk_outlinein`、`.feedback`、`.side`、`.feedback_textarea` 这些容器类——部分会被 `.glass_card` 替代。

- [ ] **Step 6: 更新侧栏切换脚本**（同 Task 3）

- [ ] **Step 7: 验证 `use_function.html` 页面正常**

- [ ] **Step 8: Commit**
  ```bash
  git add frontend/use_function.html
  git commit -m "style: unify use_function.html (guide page) with modern design language"
  ```

---

### Task 5: 更新 `feed_back.html`（反馈页）统一风格

**Files:**
- Modify: `frontend/feed_back.html`

- [ ] **Step 1: 添加 `style.css` 引用**

在 `<head>` 中添加 `<link rel="stylesheet" href="./style.css">`。

- [ ] **Step 2: 替换侧栏 HTML 为现代结构**

侧栏 HTML 结构同 Task 3，但 `active` 类应位于"问题反馈"菜单项上。

```html
<!-- 聊天菜单项 -->
<a href="./index.html">
    <div class="menu_item_row">
        ...
    </div>
</a>
<!-- 反馈菜单项（active） -->
<a href="./feed_back.html">
    <div class="menu_item_row active">
        ...
    </div>
</a>
```

- [ ] **Step 3: 替换顶栏 HTML 为现代结构**

```html
<div class="headline">
    <div class="headline_hidemenu">
        <button id="button">
            <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
            </svg>
        </button>
    </div>
    <div class="headline_head">问题反馈</div>
    <div class="share"></div>
</div>
```

- [ ] **Step 4: 更新反馈表单区**

将反馈表单包裹在 `.glass_card` 中，调整布局：

```html
<div style="flex-grow: 1; overflow-y: auto; padding: 30px; display: flex; flex-direction: column; align-items: center;">
    <div class="glass_card" style="width: 600px; max-width: 100%;">
        <input type="email" id="email" class="feedback_email" placeholder="请输入您的邮箱地址..." required style="width: 100%; height: 40px; margin-bottom: 15px; padding: 10px; font-size: 16px; border: 1px solid rgba(25, 84, 142, 0.2); border-radius: 8px; outline: none; box-sizing: border-box;">
        <textarea name="" id="feedback" cols="10" rows="10" class="feedback_textarea" placeholder="请输入您的宝贵意见..." style="width: 100%; height: 300px; padding: 15px; font-size: 14px; border: 1px solid rgba(25, 84, 142, 0.2); border-radius: 8px; outline: none; resize: vertical; box-sizing: border-box;"></textarea>
        <div style="display: flex; justify-content: center; margin-top: 20px;">
            <button class="button" id="feedbackButton" onclick="feedback()" style="width: 150px; padding: 12px 0; border: none; border-radius: 10px; background: linear-gradient(135deg, #19548e, #2c72b8); color: white; font-size: 15px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; box-shadow: 0 4px 15px rgba(25, 84, 142, 0.15);">
                提交反馈
            </button>
        </div>
    </div>
</div>
```

- [ ] **Step 5: 更新 `<style>` 块**

保留反馈页面特有样式（如 `.feedback_buttom .button::before` 的波纹效果），移除已公共化的样式。

- [ ] **Step 6: 更新侧栏切换脚本**（同 Task 3）

- [ ] **Step 7: 验证 `feed_back.html` 页面正常**
  - 反馈表单可用、侧栏切换正常

- [ ] **Step 8: Commit**
  ```bash
  git add frontend/feed_back.html
  git commit -m "style: unify feed_back.html (feedback page) with modern design language"
  ```

---

### Task 6: 最终验证

- [ ] **Step 1: 逐页打开确认风格统一**
  - `http://127.0.0.1:8001/web/index.html` — 聊天页
  - `http://127.0.0.1:8001/web/manage.html` — 管理页
  - `http://127.0.0.1:8001/web/use_function.html` — 指南页
  - `http://127.0.0.1:8001/web/feed_back.html` — 反馈页

- [ ] **Step 2: 检查项目**
  - 背景渐变、字体、侧栏样式、顶栏样式、颜色方案四页一致
  - 各页面自己的功能逻辑未受损
  - `style.css` 引用路径正确，无 404
