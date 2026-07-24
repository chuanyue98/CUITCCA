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
  if (button && container) {
    function adjustSidebar() {
      if (!button || !container) return;
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
