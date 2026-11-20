// devhub core: KHUNG WEB THỐNG NHẤT (shell) — sidebar dọc menu cây nhiều cấp + navbar + vùng nội dung.
// Viết tay, SDK chung (không fetch trực tiếp — chỉ qua core.js). Trang sinh ra KHÔNG viết logic:
// index.html chỉ gọi renderShell(app, cấu-hình-ui). Đổi layout = sửa 1 dòng spec → sinh lại.
//
//   renderShell(root, { layout, theme, brand })
//     layout: vertical-floating     — navbar tách khỏi mép (margin, bo góc, bóng, sticky)
//             vertical-transparent   — navbar trong suốt; khi cuộn thêm nền mờ (backdrop-filter)
//   Router theo hash: #/<FID> → import('/js/api/<FID>.js') → renderCrudPage vào vùng nội dung.
import { core, ApiError } from './core.js';
import { renderCrudPage, renderLogin } from './page.js';

const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) el.append(c instanceof Node ? c : document.createTextNode(c ?? ''));
  return el;
};

/** Bỏ dấu + chữ thường: lọc menu theo tên/mã không phụ thuộc dấu tiếng Việt. */
const norm = (s) => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[đĐ]/g, 'd').toLowerCase();

const OPEN_KEY = 'devhub.menu.open';        // nhóm menu đang mở
const RECENT_KEY = 'devhub.menu.recent';    // chức năng mở gần đây (trang chào)
const MOBILE = '(max-width: 991.98px)';

function loadList(key) {
  try { const v = JSON.parse(localStorage.getItem(key) || 'null'); return Array.isArray(v) ? v : null; }
  catch { return null; }
}
function saveList(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* riêng tư/đầy: bỏ qua */ }
}

/** Đọc sub/tenant từ JWT (HS256) để hiện user trên navbar — không gọi thêm API. */
function jwtUser() {
  try {
    const p = JSON.parse(atob((core.token.split('.')[1] || '').replace(/-/g, '+').replace(/_/g, '/')));
    return { user: p.sub || '', tenant: p.tenant || '' };
  } catch { return { user: '', tenant: core.session?.tenant_id || '' }; }
}

let shellSeq = 0;                            // phiên shell hiện hành: hủy listener của shell cũ

export function renderShell(root, opts = {}) {
  const ui = { layout: opts.layout || 'vertical-floating', theme: opts.theme || 'light', brand: opts.brand || 'DevHub' };
  root.classList.add('dh-shell');
  root.classList.remove('dh-sidebar-open', 'dh-sidebar-collapsed', 'dh-scrolled');
  root.dataset.theme = ui.theme;
  document.documentElement.dataset.bsTheme = ui.theme === 'dark' ? 'dark' : 'light';

  // 401 bất kỳ lúc nào → về màn đăng nhập; đăng nhập lại boot() dựng shell cho đúng hash đang mở.
  const boot = () => {
    if (!core.token) { renderLogin(root, boot); return; }
    buildShell(root, ui, boot).catch((e) => {
      if (e instanceof ApiError && e.status === 401) { core.logout(); renderLogin(root, boot); return; }
      root.replaceChildren(h('div', { class: 'alert alert-danger m-3', 'data-error': e.code || '' },
        `${e.code || ''} ${e.message}`));
    });
  };
  boot();
}

async function buildShell(root, ui, boot) {
  const seq = ++shellSeq;
  const ac = new AbortController();
  const menu = await core.menu();            // chỉ gồm chức năng user có quyền R + tổ tiên của nó

  // ── chỉ mục cây: fid → {node, path tổ tiên (từ gốc, không chứa chính nó)} ──
  const index = new Map();
  const walk = (nodes, path) => (nodes || []).forEach((n) => {
    index.set(n.function_id, { node: n, path });
    walk(n.children, [...path, n]);
  });
  walk(menu, []);

  const savedOpen = loadList(OPEN_KEY);
  const openSet = new Set(savedOpen ?? menu.filter((n) => n.children?.length).map((n) => n.function_id));
  let recents = loadList(RECENT_KEY) ?? [];

  // ── sidebar: cây menu đệ quy, không giới hạn cấp ──
  const liById = new Map();
  const setGroupOpen = (fid, open, persist = true) => {
    const li = liById.get(fid);
    if (!li) return;
    li.classList.toggle('dh-open', open);
    li.classList.toggle('dh-closed', !open);
    li.querySelector(':scope > [data-menu]')?.setAttribute('aria-expanded', open ? 'true' : 'false');
    open ? openSet.add(fid) : openSet.delete(fid);
    if (persist) saveList(OPEN_KEY, [...openSet]);
  };
  const icon = (n) => n.icon
    ? h('i', { class: `ti ti-${n.icon}`, 'aria-hidden': 'true' })
    : h('span', { class: 'dh-dot', 'aria-hidden': 'true' }, '•');

  const build = (nodes, level) => {
    const ul = h('ul', { class: level === 1 ? 'dh-list' : 'dh-list dh-sub' });
    for (const n of nodes || []) {
      const kids = n.children || [];
      if (kids.length) {                     // nhóm: thu/mở được (cấp 1 = tiêu đề, cấp ≥2 thụt lề)
        const btn = h('button', { type: 'button', class: 'dh-group', 'data-menu': n.function_id,
          'data-level': String(level), 'aria-expanded': openSet.has(n.function_id) ? 'true' : 'false',
          onclick: () => setGroupOpen(n.function_id, !openSet.has(n.function_id)) },
          h('span', { class: 'dh-caret', 'aria-hidden': 'true' }), icon(n),
          h('span', { class: 'dh-name' }, n.function_name),
          h('span', { class: 'dh-fid', title: n.function_id }, n.function_id));
        const li = h('li', { 'data-fid': n.function_id }, btn, build(kids, level + 1));
        li.classList.add(openSet.has(n.function_id) ? 'dh-open' : 'dh-closed');
        liById.set(n.function_id, li);
        ul.append(li);
      } else if (n.url) {                    // mục bấm được; không url và không con thì bỏ
        ul.append(h('li', {}, h('a', { class: 'dh-item', 'data-menu': n.function_id,
          'data-level': String(level), href: `#/${n.function_id}`, title: n.function_id },
          icon(n), h('span', { class: 'dh-name' }, n.function_name),
          h('span', { class: 'dh-fid' }, n.function_id))));
      }
    }
    return ul;
  };
  const nav = h('nav', { class: 'dh-menu', 'aria-label': 'Menu chức năng' }, build(menu, 1));

  // Ô lọc menu: giữ mục khớp (tên/mã đã bỏ dấu) + tổ tiên của mục khớp
  const filter = h('input', { class: 'dh-filter form-control form-control-sm', 'data-action': 'menu-filter',
    type: 'search', placeholder: 'Lọc menu…', 'aria-label': 'Lọc menu', autocomplete: 'off' });
  filter.addEventListener('input', () => {
    const q = norm(filter.value).trim();
    const lis = [...nav.querySelectorAll('li[data-fid]')];
    const vis = new Map();                   // tính từ dưới lên: mục hiện nếu tự khớp hoặc có cháu khớp
    for (let i = lis.length - 1; i >= 0; i--) {
      const li = lis[i];
      const self = q && norm(li.querySelector(':scope > [data-menu]')?.textContent).includes(q);
      vis.set(li, !q || self || [...li.querySelectorAll('ul li[data-fid]')].some((c) => vis.get(c)));
    }
    for (const li of lis) {
      li.hidden = !vis.get(li);
      const fid = li.getAttribute('data-fid');
      if (q) setGroupOpen(fid, true, false); // đang lọc: mở hết để thấy mục khớp
      else setGroupOpen(fid, openSet.has(fid), false); // xoá lọc: trả lại đúng trạng thái đã nhớ
    }
  });

  const sidebar = h('aside', { class: 'dh-sidebar' },
    h('div', { class: 'dh-brand' }, h('span', { class: 'dh-brand-name' }, ui.brand)),
    filter, nav);

  // ── navbar ──
  const navTitle = h('span', { class: 'dh-nav-title' });
  const me = jwtUser();
  const navbar = h('header', { class: 'dh-navbar' },
    h('button', { type: 'button', class: 'dh-toggle', 'data-action': 'sidebar-toggle',
      'aria-label': 'Đóng/mở menu', onclick: () => root.classList.toggle(matchMedia(MOBILE).matches
        ? 'dh-sidebar-open' : 'dh-sidebar-collapsed') },
      h('i', { class: 'ti ti-menu-2', 'aria-hidden': 'true' })),
    navTitle,
    h('div', { class: 'dh-nav-user' },
      h('span', { class: 'dh-user', title: 'user' }, me.user || '—'),
      h('span', { class: 'dh-tenant', title: 'tenant' }, me.tenant || '—'),
      h('button', { type: 'button', class: 'dh-logout', 'data-action': 'logout',
        onclick: () => { core.logout(); renderLogin(root, boot); } }, 'Thoát')));

  // ── vùng nội dung: breadcrumb + nơi route nạp trang chức năng ──
  const breadcrumb = h('div', { class: 'dh-breadcrumb', 'data-breadcrumb': '' });
  const body = h('div', { class: 'dh-body', 'data-content': '' });
  const content = h('div', { class: 'dh-content' }, breadcrumb, body);
  const backdrop = h('div', { class: 'dh-backdrop', onclick: () => root.classList.remove('dh-sidebar-open') });
  const main = h('main', { class: 'dh-main' }, navbar, content);
  root.replaceChildren(backdrop, sidebar, main);

  window.addEventListener('scroll', () => root.classList.toggle('dh-scrolled', window.scrollY > 8),
    { passive: true, signal: ac.signal });
  window.addEventListener('hashchange', () => { if (body.isConnected) route(); }, { signal: ac.signal });
  nav.addEventListener('click', (e) => {   // mobile: bấm mục menu → đóng drawer
    if (e.target.closest('a.dh-item')) root.classList.remove('dh-sidebar-open');
  }, { signal: ac.signal });

  const crumbs = (path, leaf) => [
    ...path.flatMap((n) => [h('span', { class: 'dh-crumb' }, n.function_name),
      h('span', { class: 'dh-crumb-sep', 'aria-hidden': 'true' }, '›')]),
    h('span', { class: 'dh-crumb dh-crumb-leaf' }, `${leaf.function_id} · ${leaf.function_name}`),
  ];
  const setActive = (fid) => nav.querySelectorAll('a[data-menu]').forEach((a) => {
    a.dataset.menu === fid ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current');
  });
  const expandPath = (path) => path.forEach((n) => setGroupOpen(n.function_id, true, false));
  const remember = (fid) => {              // chức năng gần đây (trang chào)
    recents = [fid, ...recents.filter((x) => x !== fid)].slice(0, 8);
    saveList(RECENT_KEY, recents);
  };
  const head = (title, crumbPath, leaf) => {
    document.title = title;
    navTitle.textContent = crumbPath.length ? crumbPath[crumbPath.length - 1].function_name : '';
    breadcrumb.replaceChildren(...(leaf ? crumbs(crumbPath, leaf) : []));
  };

  const welcome = () => {
    head(ui.brand, []);
    const s = core.session || {};
    const me2 = jwtUser();
    const rec = recents.filter((f) => index.has(f)).slice(0, 6);
    body.replaceChildren(h('div', { class: 'card dh-welcome' }, h('div', { class: 'card-body' },
      h('h2', { class: 'mb-2' }, `Xin chào ${me2.user || 'bạn'}`),
      h('p', { class: 'text-muted mb-0' },
        `tenant ${s.tenant_id || me2.tenant || '—'} · đơn vị ${(s.units || []).join(', ') || '—'}`),
      rec.length ? h('div', { class: 'mt-3' }, h('h3', { class: 'h5' }, 'Chức năng gần đây'),
        h('ul', { class: 'mb-0' }, rec.map((f) =>
          h('li', {}, h('a', { href: `#/${f}` }, `${f} · ${index.get(f).node.function_name}`))))) : '')));
  };
  const notRoutable = (fid) => {
    const hit = index.get(fid);
    if (hit) expandPath(hit.path);          // nhóm menu: chỉ mở tổ tiên cho user bấm tiếp
    head(ui.brand, hit?.path ?? [], null);
    navTitle.textContent = hit ? hit.node.function_name : '';
    body.replaceChildren(hit
      ? h('div', { class: 'dh-welcome' }, h('h2', {}, hit.node.function_name),
          h('p', { class: 'text-muted' }, 'Đây là nhóm menu — chọn một chức năng trong cây bên trái.'))
      : h('div', { class: 'alert alert-danger', 'data-error': 'E_FORBIDDEN' },
          `E_FORBIDDEN · không có quyền hoặc không tồn tại chức năng ${fid}`));
  };

  let routeId = 0;                          // route mới sẽ hủy kết quả route cũ nếu import chưa xong
  const route = async () => {
    if (seq !== shellSeq || !body.isConnected) return;   // shell cũ: bỏ qua
    const myId = ++routeId;
    const fid = decodeURIComponent(location.hash.replace(/^#\/?/, '')).trim();
    setActive(fid);
    if (!fid) return welcome();
    const hit = index.get(fid);
    if (!hit || !hit.node.url) return notRoutable(fid);  // không có trong menu = không quyền → KHÔNG import
    const { node, path } = hit;
    expandPath(path);
    head(`${fid} · ${node.function_name}`, path, node);
    body.replaceChildren(h('div', { class: 'dh-loading' }, 'Đang nạp…'));
    try {
      const mod = await import(`/js/api/${fid}.js`);
      if (myId !== routeId) return;                     // đổi hash giữa chừng
      const api = mod[fid];
      if (!api?.meta) throw new Error(`module /js/api/${fid}.js không đúng định dạng (thiếu export ${fid})`);
      remember(fid);
      await renderCrudPage(body, api, { rights: node.right_mask });
    } catch (e) {
      if (myId !== routeId) return;
      if (e instanceof ApiError && e.status === 401) { core.logout(); renderLogin(root, boot); return; }
      body.replaceChildren(h('div', { class: 'alert alert-danger', 'data-error': e.code || 'E_ROUTE' },
        `${e.code || 'E_ROUTE'} ${e.message}`));
    }
  };
  route();
}
