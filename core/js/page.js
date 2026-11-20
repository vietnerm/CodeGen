// devhub core: dựng trang CRUD chuẩn (tìm kiếm + bảng + form) TỪ META của api module.
// Trang sinh ra chỉ khai báo config; muốn giao diện riêng thì agent lớn viết trang mới
// dùng cùng api module — không sửa file này trong code sinh ra.
import { core, ApiError } from './core.js';

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

let seq = 0;
async function input(f, value, ref) {
  const common = { name: f.name, class: 'form-control', disabled: f.readonly };
  if (ref && !f.readonly) {                       // tham chiếu: gợi ý từ API của chức năng cha
    const id = `dl-${f.name}-${++seq}`;
    const dl = h('datalist', { id });
    const el = h('input', { ...common, type: 'text', value: value ?? '', list: id, maxlength: f.length });
    el.addEventListener('focus', async () => {
      if (dl.childElementCount) return;
      try {
        const r = await core.request('GET', ref.base, { query: { size: 100 } });
        dl.replaceChildren(...r.items.map((x) => h('option', { value: x[ref.pk] },
          ref.display.map((k) => x[k]).filter(Boolean).join(' · '))));
      } catch { /* không có quyền xem cha: vẫn nhập tay được */ }
    });
    return h('span', {}, el, dl);
  }
  if (f.codemap || f.enum) {
    const opts = f.codemap ? await core.codemap.load(f.codemap) : f.enum.map((c) => ({ code: c, label: c }));
    const sel = h('select', { ...common, class: 'form-select' }, h('option', { value: '' }, '—'),
      opts.map((o) => h('option', { value: o.code, selected: o.code === value }, `${o.code} · ${o.label}`)));
    return sel;
  }
  const type = { DATE: 'date', INT: 'number', BIGINT: 'number', DECIMAL: 'number' }[f.type] || 'text';
  return h('input', { ...common, type, value: value ?? '', maxlength: f.length, pattern: f.pattern?.replace(/^\^|\$$/g, ''),
    step: f.type === 'DECIMAL' ? 'any' : undefined });
}

const val = (f, v) => (v === '' || v == null ? null : (['INT', 'BIGINT', 'DECIMAL'].includes(f.type) ? Number(v) : v));

function readForm(form, meta) {
  const out = {};
  for (const f of meta.fields) {
    const el = form.querySelector(`[data-main][name="${f.name}"]`);
    if (!el || f.readonly) continue;
    out[f.name] = val(f, el.value.trim());
  }
  for (const d of meta.details || []) {
    out[d.as] = [...form.querySelectorAll(`tr[data-detail="${d.as}"]`)].map((tr) =>
      Object.fromEntries(d.fields.map((f) => [f.name, val(f, tr.querySelector(`[name="${f.name}"]`).value.trim())])));
  }
  return out;
}

/** Bảng chi tiết (master–detail) sửa trực tiếp; gửi cả mảng khi lưu. */
async function detailTable(d, rows) {
  const body = h('tbody');
  const addRow = async (r = {}) => {
    const cells = await Promise.all(d.fields.map(async (f) => h('td', {}, await input(f, r[f.name]))));
    const tr = h('tr', { 'data-detail': d.as }, cells,
      h('td', {}, h('button', { type: 'button', class: 'btn btn-sm btn-ghost-danger', 'data-action': 'remove-line',
        onclick: () => tr.remove() }, '✕')));
    body.append(tr);
  };
  for (const r of rows || []) await addRow(r);
  return h('div', { class: 'col-12' }, h('label', { class: 'form-label mt-2' }, `${d.label} (${d.fid})`),
    h('table', { class: 'table table-sm' },
      h('thead', {}, h('tr', {}, d.fields.map((f) => h('th', {}, f.label + (f.required ? ' *' : ''))), h('th'))), body),
    h('button', { type: 'button', class: 'btn btn-sm', 'data-action': `add-line-${d.as}`, onclick: () => addRow() }, '+ Thêm dòng'));
}

/** Trang CRUD: tìm kiếm + bảng + form dựng từ meta.
 *  opts.rights: right_mask của user với chức năng này (menu trả về) — thiếu W ẩn nút
 *  tạo/sửa, thiếu D ẩn nút xoá (giữ nguyên data-action cho test). Bỏ qua = đầy đủ (trang cũ). */
export async function renderCrudPage(root, api, opts = {}) {
  const rights = opts.rights == null ? 7 : opts.rights;   // R=1 W=2 D=4 — hợp đồng core
  const can = { w: (rights & 2) !== 0, d: (rights & 4) !== 0 };
  const meta = api.meta;
  const state = { page: 0, size: 20, filters: {}, editing: null };
  const msg = h('div');
  const table = h('table', { class: 'table table-vcenter card-table' });
  const pager = h('div', { class: 'card-footer d-flex align-items-center' });
  const formBox = h('div', { class: 'card mt-3', hidden: true });

  const show = (e) => {
    msg.replaceChildren(e ? h('div', { class: 'alert alert-danger', 'data-error': e.code || '' },
      `${e.code || ''} ${e.message}`, e instanceof ApiError && e.details.length
        ? h('ul', {}, e.details.map((d) => h('li', {}, `${d.field}: ${d.message}`))) : '') : '');
  };

  async function load() {
    try {
      const r = await api.search({ ...state.filters, page: state.page, size: state.size });
      table.replaceChildren(
        h('thead', {}, h('tr', {}, meta.list.map((n) => h('th', {}, meta.fields.find((f) => f.name === n).label)), h('th'))),
        h('tbody', {}, r.items.map((row) => h('tr', { 'data-key': meta.pk.map((k) => row[k]).join('/') },
          meta.list.map((n) => h('td', {}, String(row[n] ?? ''))),
          h('td', { class: 'text-end' },
            ...(can.w ? [h('button', { class: 'btn btn-sm', 'data-action': 'edit', onclick: () => edit(row) }, 'Sửa')] : []),
            ...(can.d ? [h('button', { class: 'btn btn-sm btn-outline-danger', 'data-action': 'delete', onclick: () => remove(row) }, 'Xoá')] : []))))));
      pager.replaceChildren(h('span', { 'data-total': r.total }, `Tổng ${r.total} · trang ${r.page + 1}`), h('div', { class: 'ms-auto' },
        h('button', { class: 'btn btn-sm', 'data-action': 'prev', disabled: state.page === 0, onclick: () => { state.page--; load(); } }, '‹'),
        h('button', { class: 'btn btn-sm', 'data-action': 'next', disabled: (state.page + 1) * state.size >= r.total,
          onclick: () => { state.page++; load(); } }, '›')));
      show(null);
    } catch (e) { show(e); }
  }

  async function edit(row) {
    if (row && (meta.details || []).length) {      // tải đủ bản ghi kèm chi tiết
      try { row = await api.get(...meta.pk.map((k) => row[k])); } catch (e) { show(e); return; }
    }
    state.editing = row;
    const form = h('form', { class: 'card-body row g-2', 'data-form': row ? 'edit' : 'create' });
    for (const f of meta.fields) {
      if (f.system || f.name === 'row_version') continue;        // row_version gửi ngầm khi lưu
      if (!row && f.readonly) continue;                           // cột chỉ đọc (lookup…) chỉ hiện khi sửa
      const ref = (meta.refs || []).find((r) => r.col === f.name);
      const el = await input({ ...f, readonly: f.readonly || (row && meta.pk.includes(f.name)) }, row?.[f.name], ref);
      for (const x of el.matches?.('input,select') ? [el] : el.querySelectorAll('input,select')) x.dataset.main = '1';
      form.append(h('div', { class: 'col-md-4' }, h('label', { class: 'form-label' }, f.label, f.required ? ' *' : ''), el));
    }
    for (const d of meta.details || []) form.append(await detailTable(d, row?.[d.as]));
    form.append(h('div', { class: 'col-12' },
      h('button', { class: 'btn btn-primary', type: 'submit', 'data-action': 'save' }, row ? 'Lưu' : 'Tạo'), ' ',
      h('button', { class: 'btn', type: 'button', 'data-action': 'close', onclick: () => { formBox.hidden = true; } }, 'Đóng')));
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = readForm(form, meta);
      try {
        if (row) await api.update(...meta.pk.map((k) => row[k]), { ...row, ...body, row_version: row.row_version });
        else await api.create(body);
        formBox.hidden = true;
        await load();
      } catch (e) { show(e); }
    });
    formBox.replaceChildren(h('div', { class: 'card-header' }, h('h3', { class: 'card-title' }, row ? 'Sửa' : 'Tạo mới')), form);
    formBox.hidden = false;
  }

  async function remove(row) {
    if (!globalThis.confirm?.(`Xoá ${meta.pk.map((k) => row[k]).join('/')}?`)) return;
    try { await api.remove(...meta.pk.map((k) => row[k]), row.row_version); await load(); } catch (e) { show(e); }
  }

  const search = h('form', { class: 'row g-2 mb-3', 'data-form': 'search' },
    await Promise.all(meta.search.map(async (n) => {
      const f = meta.fields.find((x) => x.name === n);
      const el = await input({ ...f, readonly: false }, '');
      for (const x of el.matches?.('input,select') ? [el] : el.querySelectorAll('input,select')) {
        x.setAttribute('placeholder', f.label);
        x.setAttribute('aria-label', f.label);
        if (x.tagName === 'SELECT') x.options[0].textContent = `— ${f.label} —`;
      }
      return h('div', { class: 'col-md-3' }, el);
    })),
    h('div', { class: 'col-auto' }, h('button', { class: 'btn', type: 'submit', 'data-action': 'search' }, 'Tìm'),
      ...(can.w ? [' ', h('button', { class: 'btn btn-primary', type: 'button', 'data-action': 'create',
        onclick: () => edit(null) }, 'Tạo mới')] : [])));
  search.addEventListener('submit', (ev) => {
    ev.preventDefault();
    state.filters = Object.fromEntries(meta.search.map((n) => [n, search.elements[n].value || undefined]));
    state.page = 0;
    load();
  });

  root.replaceChildren(h('h2', { class: 'page-title mb-3', 'data-page': meta.id }, `${meta.id} · ${meta.name}`), msg, search,
    h('div', { class: 'card' }, h('div', { class: 'table-responsive' }, table), pager), formBox);
  await load();
}

/** Ô đăng nhập tối giản cho trang sinh ra. */
export function renderLogin(root, onDone) {
  const form = h('form', { class: 'card card-md mx-auto mt-5', style: 'max-width:24rem', 'data-form': 'login' },
    h('div', { class: 'card-body' }, h('h2', { class: 'mb-3' }, 'Đăng nhập'),
      h('input', { class: 'form-control mb-2', name: 'u', placeholder: 'user_id' }),
      h('input', { class: 'form-control mb-2', name: 'p', type: 'password', placeholder: 'password' }),
      h('button', { class: 'btn btn-primary w-100', 'data-action': 'login' }, 'Vào')));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try { await core.login(form.elements.u.value, form.elements.p.value); onDone(); } catch (e) { alert(e.message); }
  });
  root.replaceChildren(form);
}
