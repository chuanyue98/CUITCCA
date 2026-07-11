# 知识库管理与数据添加页面设计规范 (Knowledge Base Management Spec)

本文档规定了成信大校园助手 (CUITCCA) 知识库管理页面（重构 `frontend/manage.html`）的设计与实现细节。该页面旨在为管理员提供一个直观、美观且高效的界面，用于创建和删除索引、上传文档和文件、直接录入文本、通过 QA 生成插入数据以及搜索、编辑和删除已索引的文本节点。

---

## 1. 业务目标与使用场景 (Goals & Use Cases)

目前 CUITCCA 只有聊天对话页面有完善的 UI，而向知识库添加数据的操作缺少页面入口，原有 `manage.html` 极度简陋且功能不全。
本项目将重构 `frontend/manage.html`，实现以下业务场景：
1. **统一导航入口**：将主聊天页、使用指南页、问题反馈页等侧边栏中的“增加”按钮链接到本页面。
2. **索引管理**：可视化选择当前活跃的知识库索引、查看并编辑索引描述摘要（Summary）、创建或彻底删除索引。
3. **数据导入工作流**：
   - **多文件拖拽/选择上传**：支持将多个 txt 或 doc 文件拖拽到区域，一次性解析并写入所选索引中。
   - **直接文本录入**：通过输入 Document ID 和内容文本，直接添加单条文档数据。
   - **QA 问答对提取上传**：上传文件，提供自定义 QA 生成 Prompt，利用 LLM 将文件内容生成为结构化 QA 问答对后再进行索引。
4. **节点浏览器 (Node Explorer)**：实时从后端获取索引内包含的全部 document 和 node 详情，支持通过关键词对节点内容和 ID 进行前端实时过滤；支持 inline 文本编辑（自动防抖保存）以及单节点/单文档删除。

---

## 2. 界面布局与视觉规范 (UI Layout & Styling)

### 2.1 整体版面
界面遵循与 `index.html` 一致的双栏响应式设计：
- **左侧边栏 (`#side_left`)**：保留原版标志性的成信大蓝 (`#19548e`) 主题菜单，并高亮“增加/管理”选项。在屏幕宽度小于 `500px` 时可折叠为汉堡菜单。
- **右侧工作区 (`.side_right`)**：
  - **头部导航栏**：展示当前页面标题“知识库管理平台”。
  - **一体化主控台布局 (Integrated Dashboard)**：主工作区采用两栏网格布局 (`grid` 或 `flex`)：
    - **左侧工作面板**：承载**全局索引控制器**（下拉框、创建/删除索引按钮、摘要展示与编辑）和**数据导入卡片**（多标签 Tab 切换）。
    - **右侧节点面板**：承载**节点浏览器**（搜索框、节点列表滚动容器）。

### 2.2 视觉与动效设计 (Aesthetics & Micro-animations)
为确保界面具有高品质现代感（Wow Effect），我们将采用 Vanilla CSS 实现以下视觉规范：
- **字体与排版**：引入 Google Fonts 中的 `Outfit` 或 `Inter` 作为主字体，替代浏览器默认字体。
- **卡片质感**：使用微弱磨砂玻璃拟物化样式（Glassmorphism）：
  - 背景色：`rgba(255, 255, 255, 0.75)`
  - 边框：`1px solid rgba(25, 84, 142, 0.15)`
  - 阴影：`box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.08)`
  - 模糊：`backdrop-filter: blur(8px)`
- **按钮与交互**：
  - 按钮背景使用优雅渐变（如成信大蓝 `linear-gradient(135deg, #19548e, #2c72b8)`），悬停时产生小幅升起、阴影加深、背景微亮动效。
  - 删除等危险动作按钮采用柔和红粉色渐变 (`linear-gradient(135deg, #ff4d4f, #ff7875)`)。
- **文件拖拽区域**：虚线边框 (`border: 2px dashed #19548e`)，当文件拖拽悬停至上方时，虚线变为实线，且背景平滑变为浅蓝色 (`rgba(25, 84, 142, 0.05)`)。
- **全局 Toast 通知**：右下角弹出 Toast 提示框，包含平滑的平移进入和渐隐消失动效，支持成功、信息、错误三种状态颜色。

---

## 3. 后端 API 接口对接规范 (API Specification)

所有请求均直接面向 `/index` 路由，无需特殊的 API 密钥头部，但需具备完善的错误捕获与加载动画提示。

1. **获取索引列表**：
   - URL: `GET /index/list`
   - 返回格式: `{"indexes": ["cuit_index", "test_index"]}`

2. **创建索引**：
   - URL: `POST /index/create`
   - 参数: `index_name=名称` (Form)
   - 返回: `{"status": "success", "msg": "..."}` 或 `{"status": "error", "msg": "..."}`

3. **删除索引**：
   - URL: `POST /index/delete`
   - 参数: `index_name=名称` (Form)
   - 返回: `{"status": "deleted"}`

4. **获取索引摘要**：
   - URL: `GET /index/{index_name}/get_summary`
   - 返回: `{"summary": "摘要内容"}`

5. **设置/保存索引摘要**：
   - URL: `POST /index/{index_name}/set_summary`
   - 参数: `summary=新摘要` (Form)
   - 返回: `{"status": "ok", "summary": "新摘要"}`

6. **直接文本插入**：
   - URL: `POST /index/{index_name}/insertdoc`
   - 参数: `text=内容&doc_id=可选文档ID` (Form)
   - 返回: `{"status": "ok"}`

7. **多文件上传**：
   - URL: `POST /index/{index_name}/uploadFiles`
   - 参数: `files` (Multipart File Array)
   - 返回: `{"status": "inserted"}`

8. **QA 生成式上传**：
   - URL: `POST /index/{index_name}/upload_file_by_QA`
   - 参数: `file` (Multipart File), `prompt=自定义提示词` (Form, 可选)
   - 返回: `{"status": "ok"}`

9. **获取节点详情**：
   - URL: `GET /index/{index_name}/info`
   - 返回格式: `{"docs": [{"doc_id": "...", "node_id": "...", "text": "..."}]}`

10. **更新节点内容**：
    - URL: `POST /index/{index_name}/update?nodeId=节点ID`
    - 参数: `text=修改后文本` (Form)
    - 返回: `{"status": "updated"}`

11. **删除节点**：
    - URL: `POST /index/{index_name}/deleteNode?node_id=节点ID`
    - 返回: `{"status": "deleted"}`

12. **删除整个文档**：
    - URL: `POST /index/{index_name}/deleteDoc?doc_id=文档ID`
    - 返回: `{"status": "deleted"}`

13. **保存索引到磁盘**：
    - URL: `POST /index/{index_name}/save`
    - 返回: `{"status": "ok"}`

---

## 4. 关键前端逻辑设计 (Core Frontend Logic)

### 4.1 状态管理
页面使用全局状态变量保持当前会话的数据：
```javascript
let currentActiveIndex = null; // 当前选中的索引名
let allNodesList = [];          // 当前索引下的所有节点缓存（用于前端快速检索过滤）
```

### 4.2 标签页切换 (Tab Management)
通过给不同的 `Tab Header` 绑定点击事件，切换内容区域 of different tabs, 并添加 `.active` 类名控制标签下划线滑过动画。

### 4.3 节点内容编辑与防抖更新 (Debounce Node Update)
当用户在节点卡片中的 Textarea 进行修改时，触发防抖：
```javascript
let updateTimer = null;
function debouncedUpdateNode(nodeId, text, statusElement) {
    statusElement.innerText = "输入中...";
    statusElement.style.color = "#ffa940";
    
    clearTimeout(updateTimer);
    updateTimer = setTimeout(async () => {
        try {
            statusElement.innerText = "正在保存...";
            const response = await fetch(`/index/${currentActiveIndex}/update?nodeId=${nodeId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `text=${encodeURIComponent(text)}`
            });
            if (response.ok) {
                statusElement.innerText = "已自动保存";
                statusElement.style.color = "#52c41a";
            } else {
                statusElement.innerText = "保存失败";
                statusElement.style.color = "#ff4d4f";
            }
        } catch (error) {
            statusElement.innerText = "连接出错";
            statusElement.style.color = "#ff4d4f";
        }
    }, 800); // 800ms 无输入后提交
}
```

### 4.4 搜索过滤与分页加载
由于知识库节点可能很多（几百条），我们将获取到的节点数据存入本地数组 `allNodesList`。
- **快速过滤**：监听搜索框的 `input` 事件，利用 `allNodesList.filter()` 实时匹配 `text`、`doc_id` 或 `node_id`，将匹配到的节点渲染回 DOM。
- **分页展示**：若过滤后的节点数较多（例如超过 10 条），可展示简单的分页控件（"上一页" / "下一页" / 节点总数展示），避免一次渲染数百个卡片导致浏览器卡顿。

### 4.5 拖拽文件上传事件监听
```javascript
const dropzone = document.getElementById('drag-drop-zone');
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});
dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    handleFilesUpload(files);
});
```

---

## 5. 开发顺序与计划 (Implementation Steps)

1. **备份当前文件**：将现有的 `frontend/manage.html` 重命名或备份。
2. **编写结构框架**：将主界面的侧边栏结构和右侧基本工作区容器写入 `frontend/manage.html`。
3. **补充 CSS 样式**：将 Glassmorphism 卡片、酷炫渐变按钮、虚线拖拽区、Toast 浮层等所有 UI 样式加入其 `<style>` 标签或外部样式中（统一写入 `manage.html` 便于独立维护）。
4. **实现核心逻辑 JS**：编写 API 交互、状态管理、Tab 切换、拖拽上传、防抖更新、前端搜索与分页代码。
5. **更新各页面链接**：遍历 `index.html`, `feed_back.html`, `use_function.html` 并将“增加”按钮的链接更新为 `./manage.html`。
6. **运行和自检测试**：验证索引的创建、多文件上传、QA 生成式提取、节点防抖保存与过滤。
