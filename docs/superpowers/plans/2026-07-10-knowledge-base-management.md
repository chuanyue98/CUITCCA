# 知识库管理页面实现计划 (Knowledge Base Management Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `frontend/manage.html`，建立一个兼顾美观与实用的知识库管理平台，并与现有系统的左侧菜单深度集成。

**Architecture:** 
- 在 `frontend/manage.html` 中引入与 `index.html` 相同的响应式左侧导航栏。
- 右侧主区域划分为“顶部索引控制面板”、“左侧多功能数据导入卡片”和“右侧节点浏览器卡片”三大版块。
- 仅使用原生 HTML、JavaScript (Fetch API) 与 Vanilla CSS (磨砂玻璃玻璃质感、成信大蓝色彩系及平滑微动效) 构成单文件前端，并对接后台 `/index` 现有接口。

**Tech Stack:** Native HTML5, Vanilla CSS3 (with Outfit/Inter fonts & Glassmorphism), Native JS (Fetch API).

## Global Constraints
- 无任何三方 CSS 框架依赖（不得引入 Tailwind, Bootstrap 等）。
- 保持原项目的左右双栏响应式折叠逻辑与样式命名。
- 数据添加/修改/删除动作必须带有 Toast 通知和 loading 状态遮罩。
- 文本编辑需带有防抖（debounce）提交，避免输入过程中频繁向后台发送请求。

---

### Task 1: 基础框架与侧边栏导航集成 (Basic Layout & Sidebar)

**Files:**
- Create: `frontend/manage.html` (重写)
- Test: 启动后端在浏览器中访问 `/web/manage.html`

**Interfaces:**
- Consumes: 无
- Produces: 具有双栏响应式（左侧导航，右侧工作台）的基础 `manage.html`，菜单中的聊天跳转到 `./index.html`，反馈跳转到 `./feed_back.html`，指南跳转到 `./use_function.html`，管理跳转到 `./manage.html` 且加粗高亮。

- [ ] **Step 1: 编写完整的带有高品质 CSS 和基本 DOM 框架的 HTML 结构**
  
  用以下代码覆写 [manage.html](file:///home/cy/github/chuanyue98/CUITCCA/frontend/manage.html)：
  
  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <link rel="icon" href="./icon.png" type="image/x-icon">
      <title>成信大校园助手 - 知识库管理</title>
      <style>
          /* 核心基础样式与字体 */
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');
          
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
          
          /* 左侧边栏样式 */
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
          
          /* 右侧工作区 */
          .side_right {
              display: flex;
              flex-direction: column;
              flex-grow: 1;
              height: 100%;
              background-color: transparent;
              overflow: hidden;
              position: relative;
          }
          
          /* 头部顶栏 */
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
          
          /* 主工作面板 (一体化工作台) */
          .dashboard_container {
              display: flex;
              flex-direction: row;
              flex-grow: 1;
              width: 100%;
              padding: 20px;
              gap: 20px;
              overflow: hidden;
          }
          
          /* 分栏设计: 左侧控制与上传，右侧节点显示 */
          .panel_left {
              display: flex;
              flex-direction: column;
              width: 45%;
              min-width: 400px;
              gap: 20px;
              height: 100%;
              overflow-y: auto;
              padding-right: 5px;
          }
          
          .panel_right {
              display: flex;
              flex-direction: column;
              flex-grow: 1;
              height: 100%;
              background: white;
              border-radius: 20px;
              border: 1px solid rgba(25, 84, 142, 0.1);
              box-shadow: 0 10px 30px rgba(0, 0, 0, 0.02);
              overflow: hidden;
          }
          
          /* 磨砂玻璃卡片 */
          .glass_card {
              background: rgba(255, 255, 255, 0.9);
              border-radius: 20px;
              border: 1px solid rgba(25, 84, 142, 0.1);
              padding: 20px;
              box-shadow: 0 8px 24px rgba(31, 38, 135, 0.03);
              backdrop-filter: blur(8px);
          }
          
          /* Toast样式 */
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
          
          /* 移动端适配 */
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
      </style>
  </head>
  <body>
      <div class="outline">
          <!-- 左侧边栏 -->
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
                          <div class="menu_item_row">
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
          
          <!-- 右侧工作区 -->
          <div class="side_right">
              <div class="headline">
                  <div class="headline_hidemenu">
                      <button id="button">
                          <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" fill="currentColor" class="bi bi-arrow-bar-right" viewBox="0 0 16 16">
                              <path fill-rule="evenodd" d="M6 8a.5.5 0 0 0 .5.5h5.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L12.293 7.5H6.5A.5.5 0 0 0 6 8Zm-2.5 7a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 1 0v13a.5.5 0 0 1-.5.5Z"/>
                          </svg>
                      </button>
                  </div>
                  <div class="headline_head">知识库管理工作台</div>
                  <div class="share"></div>
              </div>
              
              <!-- 核心内容工作区 -->
              <div class="dashboard_container">
                  <div class="panel_left" id="panel-left-container">
                      <!-- 占位，Task 2 与 Task 3 将填充这里 -->
                  </div>
                  <div class="panel_right" id="panel-right-container">
                      <!-- 占位，Task 4 将填充这里 -->
                  </div>
              </div>
          </div>
      </div>
      
      <!-- Toast 通知浮层 -->
      <div id="toast-container"></div>
      
      <script>
          // 响应式菜单折叠监听
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
          
          // Toast 工具函数
          function showToast(message, type = 'info') {
              const container = document.getElementById('toast-container');
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
      </script>
  </body>
  </html>
  ```

- [ ] **Step 2: 验证基本文件能被 FastAPI 正常路由**
  
  用浏览器打开 `http://127.0.0.1:8000/web/manage.html` 观察页面渲染出双栏基本布局且链接正确。

- [ ] **Step 3: 提交代码**

  ```bash
  git add frontend/manage.html
  git commit -m "feat: init layout structure and responsive sidebar for manage.html"
  ```

---

### Task 2: 全局索引管理与摘要卡片 (Index Selection & Summary Panel)

**Files:**
- Modify: `frontend/manage.html` (向 `panel_left` 容器中注入全局索引选择区和摘要卡片，并编写对应的 JS 异步载入逻辑)

**Interfaces:**
- Consumes: `GET /index/list`, `POST /index/create`, `POST /index/delete`, `GET /index/{name}/get_summary`, `POST /index/{name}/set_summary`, `POST /index/{name}/save`
- Produces: 索引切换与管理面板，自动载入所选索引的 summary。

- [ ] **Step 1: 编写索引卡片部分的 HTML 结构**
  
  将 `manage.html` 中 `id="panel-left-container"` 节点替换为以下结构：
  
  ```html
  <div class="panel_left" id="panel-left-container">
      <!-- 索引管理 card -->
      <div class="glass_card">
          <h3 style="font-size: 16px; font-weight: 600; color: #333; margin-bottom: 15px; display: flex; align-items: center; gap: 8px;">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="rgb(25, 84, 142)" class="bi bi-database" viewBox="0 0 16 16">
                  <path d="M12.5 16a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm.5-5v1h1a.5.5 0 0 1 0 1h-1v1a.5.5 0 0 1-1 0v-1h-1a.5.5 0 0 1 0-1h1v-1a.5.5 0 0 1 1 0Z"/>
                  <path d="M8 1c-1.573 0-3 .107-4.03.284-1.018.173-1.977.48-2.693.94-.716.46-1.127 1.055-1.127 1.776v9c0 .721.411 1.316 1.127 1.776.716.46 1.675.767 2.693.94C5 15.893 6.427 16 8 16c.09 0 .18 0 .27-.002A4.989 4.989 0 0 1 7.02 14c-.33-.007-.66-.017-.98-.03-1.008-.04-1.92-.19-2.5-.47a1.642 1.642 0 0 1-.87-.79 2.22 2.22 0 0 1-.13-.71V11c0 .093.023.18.067.262.138.256.452.484.872.665.58.25 1.492.4 2.5.44.382.016.78.026 1.185.028-.109-.328-.17-.677-.17-1.04 0-.177.016-.35.046-.519-.344.004-.693.003-1.036-.005-1.008-.027-1.92-.148-2.5-.39a1.64 1.64 0 0 1-.87-.745 2.235 2.235 0 0 1-.13-.676V7c0 .093.023.18.067.262.138.256.452.484.872.665.58.25 1.492.4 2.5.44.596.024 1.2.035 1.79.032a4.994 4.994 0 0 1 1.012-1.944C9.55 6.02 8.788 6 8 6c-1.573 0-3-.107-4.03-.284-1.018-.173-1.977-.48-2.693-.94C.566 4.316 0 3.721 0 3c0-.721.411-1.316 1.127-1.776.716-.46 1.675-.767 2.693-.94C4.82 1.107 6.247 1 8 1Zm0 6c-1.573 0-3-.107-4.03-.284-1.018-.173-1.977-.48-2.693-.94C.566 2.316 0 1.721 0 1c0-.721.411-1.316 1.127-1.776.716-.46 1.675-.767 2.693-.94C4.82.107 6.247 0 8 0s3.18.107 4.203.284c1.018.173 1.977.48 2.693.94.716.46 1.127 1.055 1.127 1.776v3c0 .245-.048.483-.138.706a4.996 4.996 0 0 0-1.884-.702c.015-.027.022-.056.022-.086V4c0 .093-.023.18-.067.262-.138.256-.452.484-.872.665-.58.25-1.492.4-2.5.44-.382.016-.78.026-1.185.028-.109-.328-.17-.677-.17-1.04v-.03c0-.02-.002-.04-.002-.06 0-.33.047-.648.13-.948a4.98 4.98 0 0 1 .472.032Z"/>
              </svg>
              活跃知识库索引 (Indexes)
          </h3>
          
          <div style="display: flex; gap: 10px; margin-bottom: 15px;">
              <select id="index-select" style="flex-grow: 1; padding: 10px 15px; border-radius: 10px; border: 1px solid rgba(25, 84, 142, 0.2); outline: none; background: white; font-weight: 500;">
                  <option value="">加载中...</option>
              </select>
              <button onclick="saveCurrentIndexDisk()" class="btn-primary" style="background: linear-gradient(135deg, #2c72b8, #19548e); color: white; border: none; padding: 0 15px; border-radius: 10px; cursor: pointer; font-weight: 500; display: flex; align-items: center; gap: 5px;">
                  保存磁盘
              </button>
          </div>
          
          <div style="display: flex; gap: 10px; margin-bottom: 20px;">
              <input type="text" id="new-index-name" placeholder="输入新索引名称..." style="flex-grow: 1; padding: 10px 15px; border-radius: 10px; border: 1px solid rgba(200,200,200,0.5); outline: none;">
              <button onclick="createNewIndex()" style="background: linear-gradient(135deg, #52c41a, #73d13d); color: white; border: none; padding: 0 20px; border-radius: 10px; cursor: pointer; font-weight: 500;">
                  新建
              </button>
              <button onclick="deleteCurrentIndex()" style="background: linear-gradient(135deg, #ff4d4f, #ff7875); color: white; border: none; padding: 0 15px; border-radius: 10px; cursor: pointer; font-weight: 500;">
                  删除当前
              </button>
          </div>
          
          <!-- 索引摘要 Summary 区域 -->
          <div style="border-top: 1px dashed rgba(200,200,200,0.5); padding-top: 15px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                  <span style="font-weight: 600; color: #555;">索引摘要 (Summary)</span>
                  <button onclick="editCurrentSummary()" style="background: none; border: none; color: rgb(25, 84, 142); cursor: pointer; font-size: 13px; font-weight: 500;">
                      [ 编辑摘要 ]
                  </button>
              </div>
              <div id="index-summary-display" style="background: #f8fafc; padding: 12px; border-radius: 10px; font-size: 13px; color: #666; line-height: 1.6; border: 1px solid rgba(0,0,0,0.03); max-height: 150px; overflow-y: auto;">
                  选择一个索引以载入其摘要...
              </div>
          </div>
      </div>
      
      <!-- 数据导入 Card 占位 -->
      <div id="data-ingestion-placeholder"></div>
  </div>
  ```

- [ ] **Step 2: 在 script 部分编写加载、创建、删除索引，读取与修改 Summary 的核心 JS 代码**
  
  将以下 JS 函数追加至 `<script>` 标签内：
  
  ```javascript
  const baseURL = '/index';
  let currentActiveIndex = null;

  async function loadIndexes() {
      try {
          const response = await fetch(`${baseURL}/list`);
          const data = await response.json();
          const select = document.getElementById('index-select');
          select.innerHTML = '';
          
          if (!data.indexes || data.indexes.length === 0) {
              const option = document.createElement('option');
              option.value = '';
              option.innerText = '-- 暂无索引 --';
              select.appendChild(option);
              currentActiveIndex = null;
              updateSummaryDisplay('暂无索引，请在上方新建索引。');
              return;
          }
          
          data.indexes.forEach(indexName => {
              const option = document.createElement('option');
              option.value = indexName;
              option.innerText = indexName;
              select.appendChild(option);
          });
          
          // 默认选中第一个
          if (!currentActiveIndex || !data.indexes.includes(currentActiveIndex)) {
              currentActiveIndex = data.indexes[0];
          }
          select.value = currentActiveIndex;
          
          // 加载摘要和节点
          loadIndexSummary(currentActiveIndex);
          if (typeof loadIndexNodes === 'function') {
              loadIndexNodes(currentActiveIndex);
          }
      } catch (error) {
          showToast('获取索引列表失败', 'error');
      }
  }

  // 绑定下拉选择事件
  document.getElementById('index-select').addEventListener('change', (e) => {
      currentActiveIndex = e.target.value;
      if (currentActiveIndex) {
          loadIndexSummary(currentActiveIndex);
          if (typeof loadIndexNodes === 'function') {
              loadIndexNodes(currentActiveIndex);
          }
      } else {
          updateSummaryDisplay('未选中任何活跃索引');
      }
  });

  async function loadIndexSummary(indexName) {
      const summaryDiv = document.getElementById('index-summary-display');
      summaryDiv.innerText = '加载摘要中...';
      try {
          const response = await fetch(`${baseURL}/${indexName}/get_summary`);
          const data = await response.json();
          summaryDiv.innerText = data.summary || '该索引当前无摘要，您可点击上方[编辑]添加。';
      } catch (error) {
          summaryDiv.innerText = '读取摘要失败';
      }
  }

  function updateSummaryDisplay(text) {
      document.getElementById('index-summary-display').innerText = text;
  }

  // 创建索引
  async function createNewIndex() {
      const input = document.getElementById('new-index-name');
      const name = input.value.trim();
      if (!name) {
          showToast('请输入新索引名称', 'error');
          return;
      }
      
      const body = new URLSearchParams();
      body.append('index_name', name);
      
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
              currentActiveIndex = name; // 切到新索引
              await loadIndexes();
          } else {
              showToast(data.msg || '新建失败', 'error');
          }
      } catch (error) {
          showToast('网络错误，创建索引失败', 'error');
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
      }
  }

  // 保存索引到磁盘
  async function saveCurrentIndexDisk() {
      if (!currentActiveIndex) {
          showToast('当前无选中的活跃索引', 'error');
          return;
      }
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
      }
  }

  // 编辑摘要
  async function editCurrentSummary() {
      if (!currentActiveIndex) {
          showToast('当前无选中的活跃索引', 'error');
          return;
      }
      const oldSummary = document.getElementById('index-summary-display').innerText;
      const newSummary = prompt('请输入该索引的新 Summary:', oldSummary);
      if (newSummary === null) return;
      
      const body = new URLSearchParams();
      body.append('summary', newSummary);
      
      try {
          const response = await fetch(`${baseURL}/${currentActiveIndex}/set_summary`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: body.toString()
          });
          const data = await response.json();
          if (data.status === 'ok') {
              showToast('索引摘要更新成功', 'success');
              document.getElementById('index-summary-display').innerText = data.summary;
          } else {
              showToast('更新摘要失败', 'error');
          }
      } catch (error) {
          showToast('网络错误，更新摘要失败', 'error');
      }
  }

  // 页面初始加载
  window.addEventListener('DOMContentLoaded', () => {
      loadIndexes();
  });
  ```

- [ ] **Step 3: 运行并测试索引选择器与摘要的读写**
  
  运行 FastAPI 后，点击“新建”创建新索引测试，选择不同的索引测试 Summary 能否成功请求并拉取，编辑 Summary 查看其修改能否持久写入磁盘并在刷新后保存。

- [ ] **Step 4: 提交**

  ```bash
  git add frontend/manage.html
  git commit -m "feat: implement global index controls and summary loading inside manage.html"
  ```

---

### Task 3: 数据导入工作区卡片 (Data Ingestion Panel & Upload Workflows)

**Files:**
- Modify: `frontend/manage.html` (向 `panel_left` 下方注入 Tab 页卡，支持多文件拖拽、直接文本录入、QA 上传，编写 JS 上传逻辑)

**Interfaces:**
- Consumes: `POST /index/{name}/uploadFiles`, `POST /index/{name}/insertdoc`, `POST /index/{name}/upload_file_by_QA`
- Produces: 标签切换及不同上传管道。支持拖拽状态感知、表单数据封装和请求后重载 Node 列表。

- [ ] **Step 1: 编写多重 Tab 导入 HTML 与 CSS**
  
  在 `manage.html` 的样式中添加 Tab 页和拖拽区域的样式：
  
  ```css
  /* Tabs 样式 */
  .tabs_header {
      display: flex;
      border-bottom: 1px solid rgba(200, 200, 200, 0.3);
      margin-bottom: 15px;
      gap: 15px;
  }
  
  .tab_btn {
      padding: 10px 5px;
      border: none;
      background: none;
      cursor: pointer;
      color: #777;
      font-weight: 500;
      position: relative;
      transition: color 0.2s;
  }
  
  .tab_btn:hover {
      color: rgb(25, 84, 142);
  }
  
  .tab_btn.active {
      color: rgb(25, 84, 142);
      font-weight: 600;
  }
  
  .tab_btn.active::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      width: 100%;
      height: 2px;
      background-color: rgb(25, 84, 142);
  }
  
  .tab_content {
      display: none;
  }
  
  .tab_content.active {
      display: block;
  }
  
  /* 拖拽上传框 */
  .drag_zone {
      border: 2px dashed rgba(25, 84, 142, 0.25);
      border-radius: 15px;
      padding: 30px 20px;
      text-align: center;
      background: rgba(25, 84, 142, 0.01);
      cursor: pointer;
      transition: all 0.3s ease;
  }
  
  .drag_zone.dragover {
      border-color: rgb(25, 84, 142);
      background-color: rgba(25, 84, 142, 0.05);
  }
  
  .drag_zone svg {
      color: rgba(25, 84, 142, 0.5);
      margin-bottom: 10px;
  }
  
  .form_group {
      margin-bottom: 12px;
  }
  
  .form_group label {
      display: block;
      margin-bottom: 5px;
      font-weight: 600;
      font-size: 13px;
      color: #555;
  }
  
  .form_group input, .form_group textarea {
      width: 100%;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid rgba(200, 200, 200, 0.8);
      outline: none;
      font-size: 13px;
  }
  
  .form_group input:focus, .form_group textarea:focus {
      border-color: rgb(25, 84, 142);
  }
  
  .btn-submit {
      width: 100%;
      padding: 10px;
      border: none;
      border-radius: 8px;
      background: linear-gradient(135deg, #19548e, #2c72b8);
      color: white;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
  }
  
  .btn-submit:hover {
      opacity: 0.9;
  }
  ```
  
  在 `id="data-ingestion-placeholder"` 的位置，插入以下 Tab 卡片 HTML 结构：
  
  ```html
  <div class="glass_card" style="margin-top: 20px;">
      <div class="tabs_header">
          <button class="tab_btn active" onclick="switchTab('tab-upload')">文件上传</button>
          <button class="tab_btn" onclick="switchTab('tab-text')">文本录入</button>
          <button class="tab_btn" onclick="switchTab('tab-qa')">QA生成导入</button>
      </div>
      
      <!-- Tab 1: 文件拖拽上传 -->
      <div id="tab-upload" class="tab_content active">
          <div class="drag_zone" id="drag-zone" onclick="document.getElementById('file-input').click()">
              <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" fill="currentColor" class="bi bi-cloud-arrow-up" viewBox="0 0 16 16" style="margin: 0 auto 10px auto; display: block;">
                  <path fill-rule="evenodd" d="M7.646 5.146a.5.5 0 0 1 .708 0l2 2a.5.5 0 0 1-.708.708L8.5 6.707V10.5a.5.5 0 0 1-1 0V6.707L6.354 7.854a.5.5 0 1 1-.708-.708l2-2z"/>
                  <path d="M4.406 3.342A5.53 5.53 0 0 1 8 2c2.69 0 4.923 2 5.166 4.579C14.758 6.804 16 8.137 16 9.773 16 11.569 14.502 13 12.687 13H3.781C1.708 13 0 11.366 0 9.318c0-1.763 1.266-3.223 2.942-3.593.143-.863.698-1.723 1.464-2.383zm.653.757c-.757.653-1.153 1.44-1.153 2.056v.448l-.445.049C2.064 6.805 1 7.952 1 9.318 1 10.743 2.185 12 3.78 12h8.906c1.23 0 2.313-.984 2.313-2.227 0-1.226-1.02-2.127-2.23-2.203l-.683-.043-.058-.68C11.783 4.685 10.024 3 8 3c-1.528 0-2.88.948-3.418 2.223l-.147.348-.348.147zm.255 5.673a.5.5 0 0 1-.708-.708L6.293 7.5H4.5a.5.5 0 0 1 0-1h1.793L4.646 4.854a.5.5 0 1 1 .708-.708l2.5 2.5a.5.5 0 0 1 0 .708l-2.5 2.5z"/>
              </svg>
              <p style="font-size: 13px; color: #555; font-weight: 500;">拖拽 TXT/PDF/Markdown 文件到这里，或者点击选择</p>
              <p style="font-size: 11px; color: #999; margin-top: 5px;">支持多文件一次性上传和自动解析分块</p>
              <input type="file" id="file-input" multiple style="display: none;">
          </div>
          <div id="upload-progress-list" style="margin-top: 15px; font-size: 12px; color: #666;"></div>
      </div>
      
      <!-- Tab 2: 直接文本录入 -->
      <div id="tab-text" class="tab_content">
          <div class="form_group">
              <label for="input-doc-id">文档标识符 (Doc ID - 可选)</label>
              <input type="text" id="input-doc-id" placeholder="例如: rule_dormitory_v1 (为空则系统自动生成)">
          </div>
          <div class="form_group">
              <label for="input-doc-text">文档正文内容 (Text)</label>
              <textarea id="input-doc-text" rows="6" placeholder="请输入要索引的内容文本..."></textarea>
          </div>
          <button onclick="submitDirectText()" class="btn-submit">确认插入文档</button>
      </div>
      
      <!-- Tab 3: QA 生成式上传 -->
      <div id="tab-qa" class="tab_content">
          <div class="form_group">
              <label for="qa-file-input">选择数据源文件 (TXT / MD 等)</label>
              <input type="file" id="qa-file-input">
          </div>
          <div class="form_group">
              <label for="qa-custom-prompt">QA 问答抽取 Prompt (可选)</label>
              <textarea id="qa-custom-prompt" rows="3" placeholder="默认会将文件内容切割为多块，并为每块生成对应的标准问答对..."></textarea>
          </div>
          <button onclick="submitQAGeneration()" class="btn-submit" style="background: linear-gradient(135deg, #722ed1, #9254de);">生成 QA 并导入</button>
      </div>
  </div>
  ```

- [ ] **Step 2: 编写 Tab 切换和数据导入上传的 JavaScript 逻辑**
  
  在 `<script>` 标签中添加以下导入交互与 API 通信脚本：
  
  ```javascript
  // Tab 切换逻辑
  function switchTab(tabId) {
      document.querySelectorAll('.tab_btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab_content').forEach(content => content.classList.remove('active'));
      
      const activeBtn = Array.from(document.querySelectorAll('.tab_btn')).find(btn => btn.getAttribute('onclick').includes(tabId));
      if (activeBtn) activeBtn.classList.add('active');
      
      const content = document.getElementById(tabId);
      if (content) content.classList.add('active');
  }

  // 拖拽区域监听
  const dragZone = document.getElementById('drag-zone');
  dragZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dragZone.classList.add('dragover');
  });

  dragZone.addEventListener('dragleave', () => {
      dragZone.classList.remove('dragover');
  });

  dragZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dragZone.classList.remove('dragover');
      const files = e.dataTransfer.files;
      if (files.length > 0) {
          uploadFiles(files);
      }
  });

  document.getElementById('file-input').addEventListener('change', (e) => {
      const files = e.target.files;
      if (files.length > 0) {
          uploadFiles(files);
      }
  });

  // 多文件上传
  async function uploadFiles(files) {
      if (!currentActiveIndex) {
          showToast('请先选择或新建一个活跃索引', 'error');
          return;
      }
      
      const progressList = document.getElementById('upload-progress-list');
      progressList.innerHTML = `<p style="color: rgb(25, 84, 142); font-weight: 500;">开始上传 ${files.length} 个文件...</p>`;
      
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
              showToast(`成功解析并插入 ${files.length} 个文件`, 'success');
              progressList.innerHTML = `<p style="color: #52c41a; font-weight: 500;">✓ 全部文件上传成功！</p>`;
              // 重新载入节点列表
              if (typeof loadIndexNodes === 'function') {
                  loadIndexNodes(currentActiveIndex);
              }
          } else {
              showToast(data.message || '文件上传解析失败', 'error');
              progressList.innerHTML = `<p style="color: #ff4d4f;">✗ 上传失败: ${data.message || '未知错误'}</p>`;
          }
      } catch (error) {
          showToast('网络错误，文件上传失败', 'error');
          progressList.innerHTML = `<p style="color: #ff4d4f;">✗ 网络连接错误</p>`;
      }
  }

  // 直接文本插入
  async function submitDirectText() {
      if (!currentActiveIndex) {
          showToast('请先选择活跃索引', 'error');
          return;
      }
      const docIdInput = document.getElementById('input-doc-id');
      const docTextInput = document.getElementById('input-doc-text');
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
      }
  }

  // QA生成式上传
  async function submitQAGeneration() {
      if (!currentActiveIndex) {
          showToast('请先选择活跃索引', 'error');
          return;
      }
      
      const fileInput = document.getElementById('qa-file-input');
      const promptInput = document.getElementById('qa-custom-prompt');
      const file = fileInput.files[0];
      const prompt = promptInput.value.trim();
      
      if (!file) {
          showToast('请选择源文件', 'error');
          return;
      }
      
      showToast('正在向大模型提交QA抽取申请，请稍候...', 'info');
      
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
              fileInput.value = '';
              promptInput.value = '';
              if (typeof loadIndexNodes === 'function') {
                  loadIndexNodes(currentActiveIndex);
              }
          } else {
              showToast(data.message || 'QA 生成生成失败', 'error');
          }
      } catch (error) {
          showToast('网络错误，提交QA任务失败', 'error');
      }
  }
  ```

- [ ] **Step 3: 测试拖拽上传、直接插入以及 QA 生成上传**
  
  运行 backend 并在浏览器中试着上传一个 `.txt` 文本文件、直接插入一行文字、选择文件进行模型 QA 抽取，检查网络响应为 200。

- [ ] **Step 4: 提交**

  ```bash
  git add frontend/manage.html
  git commit -m "feat: complete data ingestion workflows (files drag-drop, direct text, QA generator) in manage.html"
  ```

---

### Task 4: 节点浏览器卡片 (Index Node Explorer & Search)

**Files:**
- Modify: `frontend/manage.html` (向 `panel_right` 注入节点显示、快速搜索框、分页控制器、删除操作及 inline 文本防抖编辑逻辑)

**Interfaces:**
- Consumes: `GET /index/{name}/info`, `POST /index/{name}/update`, `POST /index/{name}/deleteNode`, `POST /index/{name}/deleteDoc`
- Produces: 支持全文实时前端检索、修改防抖以及删除的列表卡片。

- [ ] **Step 1: 编写 Node 浏览器的 HTML 结构**
  
  将 `manage.html` 中 `id="panel-right-container"` 节点替换为以下结构：
  
  ```html
  <div class="panel_right" id="panel-right-container" style="display: flex; flex-direction: column;">
      <!-- 搜索头部栏 -->
      <div style="padding: 20px; border-bottom: 1px solid rgba(25, 84, 142, 0.1); display: flex; align-items: center; gap: 15px; flex-shrink: 0; background: #fafbfc;">
          <h3 style="font-size: 16px; font-weight: 600; color: #333; margin-right: auto; display: flex; align-items: center; gap: 8px;">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="rgb(25, 84, 142)" class="bi bi-list-check" viewBox="0 0 16 16">
                  <path fill-rule="evenodd" d="M5 11.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zM3.854 2.146a.5.5 0 0 1 0 .708l-1.5 1.5a.5.5 0 0 1-.708 0l-.5-.5a.5.5 0 1 1 .708-.708L2 3.293l1.146-1.147a.5.5 0 0 1 .708 0zm0 4a.5.5 0 0 1 0 .708l-1.5 1.5a.5.5 0 0 1-.708 0l-.5-.5a.5.5 0 1 1 .708-.708L2 7.293l1.146-1.147a.5.5 0 0 1 .708 0zm0 4a.5.5 0 0 1 0 .708l-1.5 1.5a.5.5 0 0 1-.708 0l-.5-.5a.5.5 0 0 1 .708-.708l.5.5 1.146-1.147a.5.5 0 0 1 .708 0z"/>
              </svg>
              数据分块浏览器 (Nodes)
          </h3>
          
          <input type="text" id="node-search" placeholder="搜索关键词 / Doc ID..." style="width: 200px; padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(200, 200, 200, 0.8); outline: none; font-size: 13px;">
      </div>
      
      <!-- 节点展示主区 (滚动容器) -->
      <div id="node-list-viewport" style="flex-grow: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; background-color: #fcfdfe;">
          <div style="text-align: center; color: #999; margin-top: 40px;">选择或载入索引以查看分块数据</div>
      </div>
      
      <!-- 分页控制栏 -->
      <div id="pagination-bar" style="height: 50px; border-top: 1px solid rgba(25, 84, 142, 0.1); background: #fafbfc; display: none; align-items: center; justify-content: space-between; padding: 0 20px; flex-shrink: 0;">
          <span id="page-indicator" style="font-size: 12px; color: #666; font-weight: 500;">第 1 / 1 页 (共 0 项)</span>
          <div style="display: flex; gap: 10px;">
              <button onclick="prevPage()" id="btn-prev-page" style="padding: 5px 12px; border-radius: 6px; border: 1px solid #ccc; background: white; cursor: pointer; font-size: 12px; font-weight: 500;">上一页</button>
              <button onclick="nextPage()" id="btn-next-page" style="padding: 5px 12px; border-radius: 6px; border: 1px solid #ccc; background: white; cursor: pointer; font-size: 12px; font-weight: 500;">下一页</button>
          </div>
      </div>
  </div>
  ```

- [ ] **Step 2: 编写 Node 浏览器的 CSS 样式**
  
  向 `<style>` 标签中添加节点卡片的专属样式设计：
  
  ```css
  /* 节点卡片样式 */
  .node_card {
      background: white;
      border-radius: 12px;
      border: 1px solid rgba(200, 200, 200, 0.4);
      padding: 15px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: box-shadow 0.2s, border-color 0.2s;
  }
  
  .node_card:hover {
      box-shadow: 0 4px 12px rgba(0,0,0,0.03);
      border-color: rgba(25, 84, 142, 0.2);
  }
  
  .node_meta_row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #888;
      border-bottom: 1px solid rgba(0,0,0,0.02);
      padding-bottom: 8px;
  }
  
  .node_doc_id {
      background-color: rgba(25, 84, 142, 0.05);
      color: rgb(25, 84, 142);
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
  }
  
  .node_editor {
      width: 100%;
      min-height: 80px;
      resize: vertical;
      padding: 8px;
      border-radius: 6px;
      border: 1px solid rgba(200, 200, 200, 0.6);
      font-size: 13px;
      line-height: 1.6;
      outline: none;
      transition: border-color 0.2s;
  }
  
  .node_editor:focus {
      border-color: rgb(25, 84, 142);
  }
  
  .node_actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
  }
  
  .node_status_tag {
      font-size: 11px;
      color: #999;
      font-weight: 500;
  }
  
  .btn-delete-node {
      background: none;
      border: none;
      color: #ff4d4f;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
  }
  
  .btn-delete-node:hover {
      text-decoration: underline;
  }
  ```

- [ ] **Step 3: 编写 Node 数据加载、分页、搜索和防抖更新的 JS 逻辑**
  
  在 `<script>` 内加入如下业务控制脚本：
  
  ```javascript
  let allNodesList = [];
  let filteredNodesList = [];
  let currentPage = 1;
  const pageSize = 10;
  let updateTimers = {}; // 存储各个节点的定时器

  async function loadIndexNodes(indexName) {
      const viewport = document.getElementById('node-list-viewport');
      viewport.innerHTML = '<div style="text-align: center; color: rgb(25, 84, 142); margin-top: 40px; font-weight: 500;">正在加载节点数据...</div>';
      document.getElementById('pagination-bar').style.display = 'none';
      
      try {
          const response = await fetch(`${baseURL}/${indexName}/info`);
          const data = await response.json();
          allNodesList = data.docs || [];
          
          // 执行过滤与渲染
          applyFilterAndRender();
      } catch (error) {
          viewport.innerHTML = '<div style="text-align: center; color: #ff4d4f; margin-top: 40px;">数据分块加载失败</div>';
          showToast('获取索引节点数据失败', 'error');
      }
  }

  // 绑定搜索输入事件
  document.getElementById('node-search').addEventListener('input', () => {
      currentPage = 1;
      applyFilterAndRender();
  });

  function applyFilterAndRender() {
      const keyword = document.getElementById('node-search').value.trim().toLowerCase();
      
      if (!keyword) {
          filteredNodesList = [...allNodesList];
      } else {
          filteredNodesList = allNodesList.filter(node => 
              (node.text && node.text.toLowerCase().includes(keyword)) ||
              (node.doc_id && node.doc_id.toLowerCase().includes(keyword)) ||
              (node.node_id && node.node_id.toLowerCase().includes(keyword))
          );
      }
      
      currentPage = 1;
      renderNodesPage();
  }

  function renderNodesPage() {
      const viewport = document.getElementById('node-list-viewport');
      const pagBar = document.getElementById('pagination-bar');
      
      if (filteredNodesList.length === 0) {
          viewport.innerHTML = '<div style="text-align: center; color: #999; margin-top: 40px;">无匹配的节点数据</div>';
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
                  <span>Doc ID: <span class="node_doc_id">${node.doc_id || '自动生成'}</span></span>
                  <span style="font-family: monospace;">Node ID: ${node.node_id}</span>
              </div>
              <textarea class="node_editor" oninput="debouncedUpdateNode('${node.node_id}', this.value, document.getElementById('status-${node.node_id}'))">${node.text}</textarea>
              <div class="node_actions">
                  <span class="node_status_tag" id="status-${node.node_id}">未做修改</span>
                  <div style="display: flex; gap: 15px;">
                      <button onclick="deleteDocByCard('${node.doc_id}')" class="btn-delete-node" style="color: #fa8c16;">删除整档</button>
                      <button onclick="deleteNodeByCard('${node.node_id}')" class="btn-delete-node">删除分块</button>
                  </div>
              </div>
          `;
          viewport.appendChild(card);
      });
      
      // 调整分页组件显示
      pagBar.style.display = 'flex';
      document.getElementById('page-indicator').innerText = `第 ${currentPage} / ${totalPages} 页 (共 ${totalItems} 项)`;
      
      document.getElementById('btn-prev-page').disabled = (currentPage === 1);
      document.getElementById('btn-next-page').disabled = (currentPage === totalPages);
  }

  function prevPage() {
      if (currentPage > 1) {
          currentPage--;
          renderNodesPage();
          document.getElementById('node-list-viewport').scrollTop = 0;
      }
  }

  function nextPage() {
      const totalPages = Math.ceil(filteredNodesList.length / pageSize);
      if (currentPage < totalPages) {
          currentPage++;
          renderNodesPage();
          document.getElementById('node-list-viewport').scrollTop = 0;
      }
  }

  // 节点内容的防抖保存逻辑
  function debouncedUpdateNode(nodeId, text, statusElement) {
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
  async function deleteNodeByCard(nodeId) {
      if (!confirm('确定要删除这个数据分块(Node)吗？此操作不可逆！')) {
          return;
      }
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
  async function deleteDocByCard(docId) {
      if (!docId) {
          showToast('该卡片无关联的 Doc ID，无法删除整档，请使用删除分块', 'error');
          return;
      }
      if (!confirm(`确定要彻底删除文档 "${docId}" 及其所包含的所有分块吗？`)) {
          return;
      }
      try {
          const response = await fetch(`${baseURL}/${currentActiveIndex}/deleteDoc?doc_id=${docId}`, {
              method: 'POST'
          });
          if (response.ok) {
              showToast('整档文件及其所有分块已成功清除', 'success');
              // 重新请求后端，以防有其它关联节点
              loadIndexNodes(currentActiveIndex);
          } else {
              showToast('删除整档文件失败', 'error');
          }
      } catch (error) {
          showToast('网络错误，删除整档失败', 'error');
      }
  }
  ```

- [ ] **Step 4: 自检测试**
  
  切换索引，能够加载节点列表。搜索框输入文字能瞬间过滤；修改其中一个卡片的文本内容，能看到“正在输入...”到“已自动保存”的过渡动画；点击删除能成功弹出对话框并更新列表。

- [ ] **Step 5: 提交**

  ```bash
  git add frontend/manage.html
  git commit -m "feat: implement dynamic node explorer, front-end keyword search, paging and debounced update logic"
  ```

---

### Task 5: 侧边栏按钮链接统一整合 (Sidebar Link Integration)

**Files:**
- Modify: `frontend/index.html` (将菜单增加 `a href="#"` 替换为 `a href="./manage.html"`)
- Modify: `frontend/feed_back.html` (将菜单增加 `a href="#"` 替换为 `a href="./manage.html"`)
- Modify: `frontend/use_function.html` (将菜单增加 `a href="#"` 替换为 `a href="./manage.html"`)

**Interfaces:**
- Consumes: 无
- Produces: 侧边栏“增加”项目有正确的导航链接。

- [ ] **Step 1: 修改 index.html 链接**
  
  在 [index.html](file:///home/cy/github/chuanyue98/CUITCCA/frontend/index.html#L445) 处，将：
  ```html
  <div class="menu_mid1"><a href="#" title="增加">
  ```
  改为：
  ```html
  <div class="menu_mid1"><a href="./manage.html" title="增加">
  ```

- [ ] **Step 2: 修改 feed_back.html 链接**
  
  在 [feed_back.html](file:///home/cy/github/chuanyue98/CUITCCA/frontend/feed_back.html#L462) 处，将：
  ```html
  <div class="menu_mid1"><a href="#" title="增加">
  ```
  改为：
  ```html
  <div class="menu_mid1"><a href="./manage.html" title="增加">
  ```

- [ ] **Step 3: 修改 use_function.html 链接**
  
  在 [use_function.html](file:///home/cy/github/chuanyue98/CUITCCA/frontend/use_function.html) 中搜索类似的 `<div class="menu_mid1"><a href="#"` 并同样替换为 `./manage.html`。

- [ ] **Step 4: 测试跳转的流畅度**
  
  启动后端，点击各个页面侧边栏的“知识库管理”图标和“智能聊天”等其它图标，确认跳转完整。

- [ ] **Step 5: 提交**

  ```bash
  git add frontend/index.html frontend/feed_back.html frontend/use_function.html
  git commit -m "feat: unified sidebar navigation link for knowledge management page"
  ```
