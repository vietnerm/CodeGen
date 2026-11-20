// devhub core JS SDK — viết tay, cố định. Code sinh ra (api/*.js, trang) CHỈ gọi qua đây:
// không dùng fetch/axios trực tiếp (guard chặn). Chạy được trên trình duyệt và Node 18+.
const store = (() => {
  try { return globalThis.sessionStorage; } catch { return null; }
})();
const state = { baseUrl: '', token: store?.getItem('devhub.token') || null, codemaps: new Map(), session: null };

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `HTTP ${status}`);
    this.status = status;
    this.code = body?.code || 'E_HTTP';
    this.details = body?.details || [];
  }
  /** Lỗi của 1 trường (để hiện cạnh ô nhập) */
  field(name) { return this.details.filter((d) => d.field === name); }
}

function qs(query) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query || {})) {
    if (v !== undefined && v !== null && v !== '') p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const core = {
  configure({ baseUrl = '', token } = {}) {
    state.baseUrl = baseUrl.replace(/\/$/, '');
    if (token !== undefined) this.setToken(token);
  },
  setToken(t) {
    state.token = t || null;
    if (store) t ? store.setItem('devhub.token', t) : store.removeItem('devhub.token');
  },
  get token() { return state.token; },
  get session() { return state.session; },

  async request(method, path, { query, body } = {}) {
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(state.baseUrl + path + qs(query), {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) return null;
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) throw new ApiError(res.status, data);
    return data;
  },

  async login(userId, password, tenantId) {
    const r = await this.request('POST', '/api/v1/auth/token', {
      body: { user_id: userId, password, tenant_id: tenantId },
    });
    this.setToken(r.access_token);
    state.session = r;
    state.codemaps.clear();
    return r;
  },
  logout() { this.setToken(null); state.session = null; state.codemaps.clear(); },
  menu() { return this.request('GET', '/api/v1/menu'); },

  codemap: {
    /** Tải (có cache theo phiên) danh sách mã hiệu lực của tenant. */
    async load(group, { lang = 'vi', parent } = {}) {
      const key = `${group}|${lang}|${parent || ''}`;
      if (!state.codemaps.has(key)) {
        state.codemaps.set(key, core.request('GET', `/api/v1/codemap/${encodeURIComponent(group)}`, {
          query: { lang, parent },
        }).catch((e) => { state.codemaps.delete(key); throw e; }));
      }
      return state.codemaps.get(key);
    },
    async label(group, code, opts) {
      const items = await this.load(group, opts);
      return items.find((x) => x.code === code)?.label ?? code;
    },
  },
};
