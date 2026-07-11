# 前端页面风格统一设计文档

## 概述

以 `manage.html` 的现代设计语言为基准，统一 `index.html`（聊天页）、`use_function.html`（使用指南）、`feed_back.html`（反馈页）三个页面的视觉风格，并提取公共 CSS 以减少冗余、便于维护。

## 基准风格（来自 manage.html）

| 维度 | 规范 |
|------|------|
| 背景 | `linear-gradient(135deg, #f4f6fc 0%, #eef2fa 100%)` |
| 字体 | Google Fonts: Inter, Outfit, 回退到 -apple-system, BlinkMacSystemFont, Segoe UI |
| 品牌色 | `rgb(25, 84, 142)` (蓝), 辅助色: `#52c41a`(绿), `#ff4d4f`(红), `#fa8c16`(橙), `#722ed1`(紫) |
| 圆角 | 通用 20px, 按钮 10-16px, 卡片 12-20px |
| 侧栏 | 300px 宽, 白底, `box-shadow: 2px 0 10px rgba(0,0,0,0.02)`, 右 1px 透明分隔线 |
| Logo 区 | 50×35px, 20px 圆角, 18px 字体标题 |
| 菜单项 | 90px 高 `.func` 卡片, 20px 圆角, hover translateY(-3px) + 蓝色阴影 + 边框变色 |
| 顶栏 | 60px 高, 白底, `box-shadow: 0 2px 5px rgba(0,0,0,0.01)`, 标题居中 |
| 卡片 | `.glass_card`: 磨砂背景 `rgba(255,255,255,0.9)`, 20px 圆角, `box-shadow: 0 8px 24px rgba(31,38,135,0.03)`, `backdrop-filter: blur(8px)` |
| Toast | 右下角, 渐变背景, 3s 自动消失 |
| Loading 遮罩 | 全屏, `rgba(255,255,255,0.4)` + `backdrop-filter: blur(10px)`, 居中 spinner |
| 响应式 | `< 1024px`: 侧栏隐藏 + 汉堡按钮, 分栏变纵向堆叠 |
| 输入框 | `rgba(200,200,200,0.5)` 边框, focus 变品牌蓝色 |
| 按钮 | `linear-gradient(135deg, #19548e, #2c72b8)` 渐变, 圆角 8-10px, hover opacity 0.9 |

## 文件变更

### 新增文件

- `frontend/style.css` — 公共样式，包含上述所有基准规范的 CSS 代码

### 修改文件

- `frontend/index.html`
  - `<head>` 中 `<link href="./style.css">` 引用公共样式
  - 替换旧 `<style>` 块中侧栏/顶栏/全局基础 CSS → 移除或仅保留聊天特有样式
  - 替换侧栏 HTML：从旧的 `.menu_mid` + `.menu_font` + `.func`（旧版）改为 manage.html 同款侧栏结构
  - 替换顶栏 HTML：从旧 `.headline` 结构改为 manage.html 同款顶栏结构
  - 消息气泡样式微调：阴影和圆角统一为现代风格
  - 输入区微调：颜色统一为品牌蓝色系
  - **保留全部聊天 JS 逻辑不变**

- `frontend/use_function.html`
  - `<head>` 中 `<link href="./style.css">` 引用公共样式
  - 替换旧 `<style>` 块中侧栏/顶栏/全局基础 CSS → 移除或仅保留指南特有样式
  - 替换侧栏 HTML：统一为 manage.html 同款
  - 替换顶栏 HTML：统一为 manage.html 同款
  - 使用指南文本区用 `.glass_card` 包裹，内容居中对齐
  - **保留全部 JS 逻辑不变**

- `frontend/feed_back.html`
  - `<head>` 中 `<link href="./style.css">` 引用公共样式
  - 替换旧 `<style>` 块中侧栏/顶栏/全局基础 CSS → 移除或仅保留反馈特有样式
  - 替换侧栏 HTML：统一为 manage.html 同款
  - 替换顶栏 HTML：统一为 manage.html 同款
  - 反馈表单区用 `.glass_card` 包裹
  - **保留全部反馈 JS 逻辑不变**

- `frontend/manage.html`
  - `<head>` 中 `<link href="./style.css">` 引用公共样式
  - 从 `<style>` 块中移除已提取到 `style.css` 的公共 CSS
  - 保留页面特有样式：节点卡片（`.node_card`）、分页（`#pagination-bar`）、上传区（`.drag_zone`）、`.toast` 等

## 公共 CSS 提取清单

从 `manage.html` 的 `<style>` 块中提取以下部分到 `style.css`：

1. `@import` 字体声明
2. `*` 全局重置（box-sizing, font-family, margin, padding, font-size）
3. `body, html` 基础样式
4. `.outline` 布局容器
5. `#side_left` 侧栏 + `.side_left_flex`
6. `.head_left` / `.head_logo` / `.head_font` — Logo 区域
7. `.side_menu` + `.menu_mid` / `.menu_mid1` / `.menu_mid2` + `.func` 菜单项
8. `.menu_item_row` — 菜单行项
9. `.side_right` 右侧容器
10. `.headline` 顶栏 + `.headline_hidemenu` + `.headline_head` + `.share`
11. `.glass_card` 卡片
12. `#toast-container` + `.toast` 通知
13. 全局 `#loading-overlay` + `.spinner` + `.loading-text`
14. `.tabs_header` + `.tab_btn` + `.tab_content`（如被其他页复用）
15. 响应式 `@media` 查询
16. 汉堡按钮 JS（`button` + `div` 切换）— 需在各页面中统一脚本

## 实现顺序

1. 提取 `style.css`
2. 改造 `manage.html`（引用 `style.css`，移除冗余）
3. 改造 `index.html`
4. 改造 `use_function.html`
5. 改造 `feed_back.html`
6. 验证：逐页检查页面打开是否正常、样式是否统一、功能是否完好

## 风险与注意事项

1. **类名统一**：`index.html` 的旧菜单类名（`.menu_font`、`.menu_mid1`）与 `manage.html` 不同，HTML 结构需整体替换为现代侧栏，同时保持对应功能链接（聊天、管理、指南、反馈）指向正确的 URL
2. **相对路径**：`style.css` 与各 `.html` 同目录，引用使用 `./style.css`
3. **JS 逻辑零改动**：仅修改样式和 HTML 结构，不动任何 JavaScript 逻辑
4. **功能链接**：侧栏菜单需保留原有 4 个功能入口（管理、指南、聊天、反馈），且各页面自己的入口应有 `.active` 高亮
