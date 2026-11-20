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

async function input(f, value) {
  const common = { name: f.name, class: 'form-control', disabled: f.readonly };
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

function readForm(form, meta) {
  const out = {};
  for (const f of meta.fields) {
    const el = form.elements[f.name];
    if (!el || f.readonly) continue;
    const v = el.value.trim();
    out[f.name] = v === '' ? null : (['INT', 'BIGINT', 'DECIMAL'].includes(f.type) ? Number(v) : v);
  }
  return out;
}

export async function renderCrudPage(root, api) {
  const meta = api.meta;
  const state = { page: 0, size: 20, filters: {}, editing: null };
  const msg = h('div');
  const table = h('table', { class: 'table table-vcenter card-table' });
  const pager = h('div', { class: 'card-footer d-flex align-items-center' });
  const formBox = h('div', { class: 'card mt-3', hidden: true });

  const show = (e) => {
    msg.replaceChildren(e ? h('div', { class: 'alert alert-danger' },
      `${e.code || ''} ${e.message}`, e instanceof ApiError && e.details.length
        ? h('ul', {}, e.details.map((d) => h('li', {}, `${d.field}: ${d.message}`))) : '') : '');
  };

  async function load() {
    try {
      const r = await api.search({ ...state.filters, page: state.page, size: state.size });
      table.replaceChildren(
        h('thead', {}, h('tr', {}, meta.list.map((n) => h('th', {}, meta.fields.find((f) => f.name === n).label)), h('th'))),
        h('tbody', {}, r.items.map((row) => h('tr', {},
          meta.list.map((n) => h('td', {}, String(row[n] ?? ''))),
          h('td', { class: 'text-end' },
            h('button', { class: 'btn btn-sm', onclick: () => edit(row) }, 'Sửa'), ' ',
            h('button', { class: 'btn btn-sm btn-outline-danger', onclick: () => remove(row) }, 'Xoá'))))));
      pager.replaceChildren(`Tổng ${r.total} · trang ${r.page + 1}`, h('div', { class: 'ms-auto' },
        h('button', { class: 'btn btn-sm', disabled: state.page === 0, onclick: () => { state.page--; load(); } }, '‹'),
        h('button', { class: 'btn btn-sm', disabled: (state.page + 1) * state.size >= r.total,
          onclick: () => { state.page++; load(); } }, '›')));
      show(null);
    } catch (e) { show(e); }
  }

  async function edit(row) {
    state.editing = row;
    const form = h('form', { class: 'card-body row g-2' });
    for (const f of meta.fields) {
      if (f.system && f.name !== 'row_version') continue;
      const el = await input({ ...f, readonly: f.readonly || (row && meta.pk.includes(f.name)) }, row?.[f.name]);
      form.append(h('div', { class: 'col-md-4' }, h('label', { class: 'form-label' }, f.label, f.required ? ' *' : ''), el));
    }
    form.append(h('div', { class: 'col-12' },
      h('button', { class: 'btn btn-primary', type: 'submit' }, row ? 'Lưu' : 'Tạo'), ' ',
      h('button', { class: 'btn', type: 'button', onclick: () => { formBox.hidden = true; } }, 'Đóng')));
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = readForm(form, meta);
      try {
        if (row) await api.update(...meta.pk.map((k) => row[k]), { ...body, row_version: row.row_version });
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

  const search = h('form', { class: 'row g-2 mb-3' },
    await Promise.all(meta.search.map(async (n) => {
      const f = meta.fields.find((x) => x.name === n);
      return h('div', { class: 'col-md-3' }, await input({ ...f, readonly: false }, ''));
    })),
    h('div', { class: 'col-auto' }, h('button', { class: 'btn', type: 'submit' }, 'Tìm'), ' ',
      h('button', { class: 'btn btn-primary', type: 'button', onclick: () => edit(null) }, 'Tạo mới')));
  search.addEventListener('submit', (ev) => {
    ev.preventDefault();
    state.filters = Object.fromEntries(meta.search.map((n) => [n, search.elements[n].value || undefined]));
    state.page = 0;
    load();
  });

  root.replaceChildren(h('h2', { class: 'page-title mb-3' }, `${meta.id} · ${meta.name}`), msg, search,
    h('div', { class: 'card' }, h('div', { class: 'table-responsive' }, table), pager), formBox);
  await load();
}

/** Ô đăng nhập tối giản cho trang sinh ra. */
export function renderLogin(root, onDone) {
  const form = h('form', { class: 'card card-md mx-auto mt-5', style: 'max-width:24rem' },
    h('div', { class: 'card-body' }, h('h2', { class: 'mb-3' }, 'Đăng nhập'),
      h('input', { class: 'form-control mb-2', name: 'u', placeholder: 'user_id' }),
      h('input', { class: 'form-control mb-2', name: 'p', type: 'password', placeholder: 'password' }),
      h('button', { class: 'btn btn-primary w-100' }, 'Vào')));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try { await core.login(form.elements.u.value, form.elements.p.value); onDone(); } catch (e) { alert(e.message); }
  });
  root.replaceChildren(form);
}
