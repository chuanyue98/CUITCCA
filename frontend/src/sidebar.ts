/**
 * 公共侧边栏组件
 * 在每个页面中通过 <div id="side_left"></div> + <script type="module" src="./src/sidebar.ts" data-active="index"></script> 引入
 * data-active 属性指定当前页面的高亮菜单项: index | manage | use_function | feed_back | config
 */

import { getApiKey, setApiKey, clearApiKey, onUnauthorized } from './utils/api';

(function () {
  // Vite 把 <script type="module"> 重写后会丢失 data-active 自定义属性，
  // 且 ES module 中 document.currentScript 为 null。改从 URL 推断当前页面。
  const _path = window.location.pathname.replace(/\/+$/, '');
  const _page = _path.slice(_path.lastIndexOf('/') + 1).replace('.html', '');
  const activePage = (_page === 'index' || _page === 'manage' || _page === 'use_function' || _page === 'feed_back' || _page === 'config')
    ? _page
    : '';

  const currentKey = getApiKey();
  const hasKey = !!currentKey;

  // ===== 导航数据与渲染 =====
  // 原来是 300 行转义字符串拼接，加一个菜单项要在三处条件表达式里复制粘贴
  // 激活态样式。改成数据驱动：NAV_ITEMS 描述"有什么"，render 函数描述
  // "长什么样"，DOM 结构与 class/内联样式与拼接版逐字一致（样式类和
  // 激活态判断有 Playwright 用例依赖）。

  const ACTIVE_BLUE = 'rgb(25, 84, 142)';

  // bootstrap-icons 的 SVG path 数据（viewBox 0 0 16 16，fill=currentColor，
  // 颜色由外层 .img 的 color 控制）
  const ICONS = {
    houseAdd:
      '<path d="M8.707 1.5a1 1 0 0 0-1.414 0L.646 8.146a.5.5 0 0 0 .708.708L2 8.207V13.5A1.5 1.5 0 0 0 3.5 15h4a.5.5 0 1 0 0-1h-4a.5.5 0 0 1-.5-.5V7.207l5-5 6.646 6.647a.5.5 0 0 0 .708-.708L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.707 1.5Z"/>' +
      '<path fill-rule="evenodd" d="M16 12.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Zm-3.5-2a.5.5 0 0 1 .5.5v1h1a.5.5 0 0 1 0 1h-1v1a.5.5 0 1 1-1 0v-1h-1a.5.5 0 1 1 0-1h1v-1a.5.5 0 0 1 .5-.5Z"/>',
    compass:
      '<path d="M8 16.016a7.5 7.5 0 0 0 1.962-14.74A1 1 0 0 0 9 0H7a1 1 0 0 0-.962 1.276A7.5 7.5 0 0 0 8 16.016zm6.5-7.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z"/>' +
      '<path d="m6.94 7.44 4.95-2.83-2.83 4.95-4.949 2.83 2.828-4.95z"/>',
    chatQuote:
      '<path d="M2.678 11.894a1 1 0 0 1 .287.801 10.97 10.97 0 0 1-.398 2c1.395-.323 2.247-.697 2.634-.893a1 1 0 0 1 .71-.074A8.06 8.06 0 0 0 8 14c3.996 0 7-2.807 7-6 0-3.192-3.004-6-7-6S1 4.808 1 8c0 1.468.617 2.83 1.678 3.894zm-.493 3.905a21.682 21.682 0 0 1-.713.129c-.2.032-.352-.176-.273-.362a9.68 9.68 0 0 0 .244-.637l.003-.01c.248-.72.45-1.548.524-2.319C.743 11.37 0 9.76 0 8c0-3.866 3.582-7 8-7s8 3.134 8 7-3.582 7-8 7a9.06 9.06 0 0 1-2.347-.306c-.52.263-1.639.742-3.468 1.105z"/>' +
      '<path d="M7.066 6.76A1.665 1.665 0 0 0 4 7.668a1.667 1.667 0 0 0 2.561 1.406c-.131.389-.375.804-.777 1.22a.417.417 0 0 0 .6.58c1.486-1.54 1.293-3.214.682-4.112zm4 0A1.665 1.665 0 0 0 8 7.668a1.667 1.667 0 0 0 2.561 1.406c-.131.389-.375.804-.777 1.22a.417.417 0 0 0 .6.58c1.486-1.54 1.293-3.214.682-4.112z"/>',
    gear:
      '<path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z"/>' +
      '<path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.291-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.291c.415.764-.42 1.6-1.185 1.184l-.291-.159a1.873 1.873 0 0 0-2.693 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.692-1.115l-.292.16c-.764.415-1.6-.42-1.184-1.185l.159-.291A1.873 1.873 0 0 0 1.945 8.93l-.319-.094c-.835-.246-.835-1.428 0-1.674l.319-.094A1.873 1.873 0 0 0 3.06 4.377l-.16-.292c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.115l.094-.319z"/>',
    stackOverflow:
      '<path d="M12.412 14.572V10.29h1.428V16H1v-5.71h1.428v4.282h9.984z"/>' +
      '<path d="M3.857 13.145h7.137v-1.428H3.857v1.428zM10.254 0 9.108.852l4.26 5.727 1.146-.852L10.254 0zm-3.54 3.377 5.484 4.567.913-1.097L7.627 2.28l-.914 1.097zM4.922 6.55l6.47 3.013.603-1.294-6.47-3.013-.603 1.294zm-.925 3.344 6.985 1.469.294-1.398-6.985-1.468-.294 1.397z"/>',
  };

  function iconSvg(name: keyof typeof ICONS, cls: string, size: number): string {
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" fill="currentColor" ` +
      `class="bi ${cls}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`
    );
  }

  interface NavItem {
    /** 与页面文件名（去 .html）一致，用于激活态判定 */
    page: string;
    href: string;
    label: string;
    title?: string;
    /** card: 顶部两个大卡片（menu_mid1/2）；row: 底部三个行式入口 */
    variant: 'card' | 'row';
    wrapperClass?: string;
    icon: { name: keyof typeof ICONS; cls: string; size: number };
  }

  const NAV_ITEMS: NavItem[] = [
    { variant: 'card', wrapperClass: 'menu_mid1', page: 'manage', href: './manage.html', title: '管理 & 增加', label: '知识库管理', icon: { name: 'houseAdd', cls: 'bi-house-add', size: 30 } },
    { variant: 'card', wrapperClass: 'menu_mid2', page: 'use_function', href: './use_function.html', title: '食用指南', label: '使用指南', icon: { name: 'compass', cls: 'bi-compass', size: 30 } },
    { variant: 'row', page: 'index', href: './index.html', label: '智能聊天', icon: { name: 'chatQuote', cls: 'bi-chat-quote', size: 22 } },
    { variant: 'row', page: 'config', href: './config.html', label: '系统配置', icon: { name: 'gear', cls: 'bi-gear', size: 22 } },
    { variant: 'row', page: 'feed_back', href: './feed_back.html', label: '问题反馈', icon: { name: 'stackOverflow', cls: 'bi-stack-overflow', size: 22 } },
  ];

  function renderCard(item: NavItem): string {
    const active = activePage === item.page;
    const activeStyle = active
      ? ' style="border-radius: 20px; box-shadow: 0 4px 15px rgba(25, 84, 142, 0.15); border-color: rgba(25, 84, 142, 0.2);"'
      : '';
    const iconColor = active ? ACTIVE_BLUE : '#666';
    const labelStyle = active
      ? `font-size: 13px; font-weight: 500; color: ${ACTIVE_BLUE};`
      : 'font-size: 13px; color: #666;';
    const svg = iconSvg(item.icon.name, item.icon.cls, item.icon.size);
    return (
      `<div class="${item.wrapperClass}">` +
      `<a href="${item.href}" title="${item.title}">` +
      `<div class="func${active ? ' func-active' : ''}"${activeStyle}>` +
      `<div class="img" style="color: ${iconColor};">${svg}</div>` +
      `<div style="${labelStyle}">${item.label}</div>` +
      '</div></a></div>'
    );
  }

  function renderRow(item: NavItem): string {
    const active = activePage === item.page;
    const svg = iconSvg(item.icon.name, item.icon.cls, item.icon.size);
    return (
      `<a href="${item.href}">` +
      `<div class="menu_item_row${active ? ' active' : ''}">` +
      `<div class="img">${svg}</div>` +
      `<div class="menu_font_row">${item.label}</div>` +
      '</div></a>'
    );
  }

  const cards = NAV_ITEMS.filter((i) => i.variant === 'card').map(renderCard).join('');
  const rows = NAV_ITEMS.filter((i) => i.variant === 'row').map(renderRow).join('');

  const sidebarHTML =
    `<div class="side_left_flex">
        <div class="head_left">
            <div class="head_logo">
                <img src="./logo.png" alt="Logo">
            </div>
            <div class="head_font">成信大校园助手</div>
        </div>
        <div class="side_menu">
            <div class="menu_mid">${cards}</div>
            ${rows}
        </div>
        <div class="side_bottom">
            <button class="side_action_btn" id="theme-toggle" type="button" title="切换深色 / 浅色模式">🌙 主题</button>
            <button class="side_action_btn" id="api-key-btn" type="button" title="设置后端访问密钥">${hasKey ? '🔑 已配置密钥' : '🔑 设置访问密钥'}</button>
        </div>
        <div class="side_footer">成信大校园助手 · 基于校园知识库</div>
    </div>`;

  const container = document.getElementById('side_left');
  if (container) {
    container.innerHTML = sidebarHTML;
  }

  // 窄屏遮罩：#side_left 在 <1024px 下被 style.css 的媒体查询改成
  // position:fixed 覆盖层（不再挤占 .outline 的 flex 布局），这里配一层
  // 半透明遮罩负责"盖住正文 + 点击关闭"。display:none/block 的折叠机制本身
  // 不动（可能有测试断言），遮罩只是叠加在其之上的独立控制。
  const backdrop = document.createElement('div');
  backdrop.className = 'sidebar_backdrop';
  document.body.appendChild(backdrop);

  // ===== 主题切换 (localStorage 记忆, 覆盖 prefers-color-scheme) =====
  const THEME_KEY = 'cuitcca_theme';
  function applyTheme(theme: 'light' | 'dark') {
    // 用 data-theme 显式覆盖 prefers-color-scheme (light 也强制设置, 避免系统暗色覆盖)
    document.documentElement.setAttribute('data-theme', theme);
  }
  // 初始应用 (优先 localStorage, 否则跟随系统)
  const savedTheme = localStorage.getItem(THEME_KEY) as 'light' | 'dark' | null;
  if (savedTheme) {
    applyTheme(savedTheme);
  }
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const isDark = current === 'dark' ||
        (!current && window.matchMedia('(prefers-color-scheme: dark)').matches);
      const next: 'light' | 'dark' = isDark ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem(THEME_KEY, next);
    });
  }

  // ===== API Key 设置弹窗 =====
  function promptApiKey(title: string, message: string) {
    const existing = document.getElementById('apikey-modal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'apikey-modal';
    modal.className = 'apikey_modal';
    modal.innerHTML = `
      <div class="apikey_dialog">
        <div class="apikey_title">${title}</div>
        <div class="apikey_message">${message}</div>
        <input type="password" id="apikey-input" class="apikey_input" placeholder="粘贴 CUITCCA_API_KEY..." autocomplete="off">
        <div class="apikey_actions">
          <button class="apikey_btn apikey_btn--ghost" id="apikey-cancel">取消</button>
          ${hasKey ? '<button class="apikey_btn apikey_btn--danger" id="apikey-clear">清除密钥</button>' : ''}
          <button class="apikey_btn apikey_btn--primary" id="apikey-save">保存</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    const input = document.getElementById('apikey-input') as HTMLInputElement;
    input.value = currentKey;
    setTimeout(() => input.focus(), 50);
    document.getElementById('apikey-cancel')?.addEventListener('click', () => modal.remove());
    document.getElementById('apikey-save')?.addEventListener('click', () => {
      const val = input.value.trim();
      if (val) {
        setApiKey(val);
      } else {
        clearApiKey();
      }
      modal.remove();
      location.reload();
    });
    if (hasKey) {
      document.getElementById('apikey-clear')?.addEventListener('click', () => {
        clearApiKey();
        modal.remove();
        location.reload();
      });
    }
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  }

  const apiKeyBtn = document.getElementById('api-key-btn');
  if (apiKeyBtn) {
    apiKeyBtn.addEventListener('click', () => {
      promptApiKey('设置访问密钥', '当后端配置了 CUITCCA_API_KEY 时，前端需要携带密钥才能调用受保护的接口。');
    });
  }

  // 注册 401 回调: 自动弹出密钥设置对话框
  onUnauthorized(() => {
    promptApiKey('检测到访问密钥未配置或失效', '管理接口返回 401，请设置正确的 CUITCCA_API_KEY 后重试。');
  });

  // 侧边栏折叠逻辑
  const button = document.getElementById('button');
  if (button && container) {
    function isOpen() {
      return container!.style.display === 'block';
    }

    function setOpen(open: boolean) {
      container!.style.display = open ? 'block' : 'none';
      // 窄屏才需要遮罩；桌面端侧栏常驻，遮罩不该出现（即使 open 状态是 true）。
      backdrop.classList.toggle('is-visible', open && window.innerWidth < 1024);
      button!.setAttribute('aria-expanded', String(open));
    }

    function adjustSidebar() {
      if (window.innerWidth < 1024) {
        button!.style.display = 'block';
        setOpen(false);
      } else {
        button!.style.display = 'none';
        setOpen(true);
        // 桌面端侧栏常驻，折叠按钮本身不可见也不该占据 tab 顺序里的
        // "已展开/已折叠"语义。
        button!.removeAttribute('aria-expanded');
      }
    }

    window.addEventListener('resize', adjustSidebar);
    button!.setAttribute('aria-label', '切换侧边栏');
    button!.addEventListener('click', function () {
      setOpen(!isOpen());
    });

    // 点遮罩关闭
    backdrop.addEventListener('click', () => setOpen(false));

    // 点侧栏内导航链接后关闭：窄屏下侧栏浮在正文上方，点完链接如果不收起，
    // 下一个页面加载出来时遮罩还盖在上面，等于卡死交互。
    container.addEventListener('click', (ev) => {
      if (window.innerWidth < 1024 && (ev.target as HTMLElement).closest('a')) {
        setOpen(false);
      }
    });

    // Esc 关闭
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && window.innerWidth < 1024 && isOpen()) {
        setOpen(false);
      }
    });

    adjustSidebar();
  }
})();
