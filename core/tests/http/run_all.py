#!/usr/bin/env python3
"""
Bộ test HTTP hộp đen của core contract — chỉ dùng Python stdlib.
Chạy giống hệt với mọi backend (Java, C++, …): backend nào qua hết thì tương đương.

    BASE_URL=http://localhost:8080 python tests/http/run_all.py [--only ATA0_0110] [-v]

Dữ liệu lấy từ fixtures.json (generator sinh từ spec). Exit 1 nếu có ca hỏng.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = os.environ.get('BASE_URL', 'http://localhost:8080').rstrip('/')
FX = json.loads((HERE / 'fixtures.json').read_text(encoding='utf-8'))
BITS = {'R': 1, 'W': 2, 'D': 4, 'X': 8}


# ─────────────────────────── HTTP ───────────────────────────
class Resp:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def detail(self, field, code):
        for d in (self.body or {}).get('details') or []:
            if d.get('field') == field and d.get('code') == code:
                return True
        return False

    def __repr__(self):
        return f"HTTP {self.status} {json.dumps(self.body, ensure_ascii=False)[:300]}"


def http(method, path, token=None, body=None, query=None):
    url = BASE + path + ('?' + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
                         if query else '')
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Accept', 'application/json')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return Resp(r.status, json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return Resp(e.code, json.loads(raw) if raw else None)
        except ValueError:
            return Resp(e.code, {'raw': raw.decode(errors='replace')[:200]})


def wait_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = http('POST', '/api/v1/auth/token', body={'user_id': '_probe_', 'password': 'x'})
            if r.status in (400, 401):
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    return False


# ─────────────────────────── kết quả ───────────────────────────
class T:
    def __init__(self, verbose):
        self.ok = self.fail = 0
        self.verbose = verbose
        self.failures = []
        self.section = ''

    def check(self, name, cond, info=''):
        if cond:
            self.ok += 1
            if self.verbose:
                print(f"    ✓ {name}")
        else:
            self.fail += 1
            self.failures.append(f"[{self.section}] {name} — {info}")
            print(f"    ✗ {name} — {info}")
        return cond


_tokens = {}


def token(user):
    if user['user_id'] not in _tokens:
        r = http('POST', '/api/v1/auth/token', body={'user_id': user['user_id'], 'password': user['password']})
        if r.status != 200:
            raise RuntimeError(f"Đăng nhập {user['user_id']} lỗi: {r}")
        _tokens[user['user_id']] = r.body['access_token']
    return _tokens[user['user_id']]


def pick(fid, need, *, tenant=None, not_tenant=None, lacks=None):
    for u in FX['users']:
        m = u['rights'].get(fid, 0)
        if all(m & BITS[c] for c in need) and not (lacks and m & BITS[lacks]) \
                and (tenant is None or u['tenant'] == tenant) and (not_tenant is None or u['tenant'] != not_tenant):
            return u
    return None


def same(a, b):
    if a is None or b is None:
        return a == b
    if isinstance(a, (int, float, Decimal)) or isinstance(b, (int, float, Decimal)):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except Exception:
            return False
    return str(a) == str(b)


def keypath(fx, row):
    return fx['base'] + ''.join('/' + urllib.parse.quote(str(row[c]), safe='') for c in fx['pk'])


# ─────────────────────────── test core ───────────────────────────
def test_core(t: T):
    t.section = 'core'
    print("• core: auth / codemap / menu")
    u = FX['users'][0]
    t.check('sai mật khẩu → 401', http('POST', '/api/v1/auth/token',
            body={'user_id': u['user_id'], 'password': 'sai-mat-khau'}).status == 401)
    r = http('POST', '/api/v1/auth/token', body={'user_id': u['user_id'], 'password': u['password']})
    t.check('đăng nhập → 200 + token + đơn vị', r.status == 200 and r.body.get('access_token')
            and r.body.get('units') == u['units'], r)
    t.check('token giả → 401', http('GET', '/api/v1/menu', token='a.b.c').status == 401)
    tampered = token(u)[:-3] + ('AAA' if not token(u).endswith('AAA') else 'BBB')
    t.check('token bị sửa chữ ký → 401', http('GET', '/api/v1/menu', token=tampered).status == 401)
    m = http('GET', '/api/v1/menu', token=token(u))
    t.check('menu → 200', m.status == 200 and isinstance(m.body, list), m)
    for g, codes in FX['codemap_groups'].items():
        r = http('GET', f"/api/v1/codemap/{g}", token=token(u))
        got = {x['code'] for x in r.body or []} if r.status == 200 else set()
        hidden = {o['code'] for o in FX['codemap_overrides'] if o['group'] == g and o['tenant'] == u['tenant']
                  and o.get('status') == 'I'}
        t.check(f"codemap {g} có đủ mã chuẩn của tenant {u['tenant']}", set(codes) - hidden <= got, r)
    for o in FX['codemap_overrides']:
        owner = next((x for x in FX['users'] if x['tenant'] == o['tenant']), None)
        other = next((x for x in FX['users'] if x['tenant'] != o['tenant']), None)
        if not owner or not other:
            continue
        mine = {x['code'] for x in http('GET', f"/api/v1/codemap/{o['group']}", token=token(owner)).body}
        theirs = {x['code'] for x in http('GET', f"/api/v1/codemap/{o['group']}", token=token(other)).body}
        if o.get('status') == 'I':
            t.check(f"tenant {o['tenant']} ẩn {o['group']}.{o['code']}", o['code'] not in mine and o['code'] in theirs)
        else:
            t.check(f"tenant {o['tenant']} có mã riêng {o['group']}.{o['code']}", o['code'] in mine and o['code'] not in theirs)
    t.check('codemap nhóm không tồn tại → 404', http('GET', '/api/v1/codemap/NO_SUCH', token=token(u)).status == 404)
    t.check('API thiếu token → 401', http('GET', '/api/v1/codemap/STATUS_AI').status == 401)


# ─────────────────────────── test 1 function ───────────────────────────
def ensure_parents(fx, body, maker):
    for r in fx['refs']:
        pfx = FX['functions'][r['parent_fid']]
        pbody = dict(pfx['example'])
        for c, p in zip(r['cols'], r['parent_cols']):
            pbody[p] = body[c]
        http('POST', pfx['base'], token=token(maker), body=pbody)       # 201 hoặc 409 đều được


def test_function(t: T, fid):
    fx = FX['functions'][fid]
    t.section = fid
    print(f"• {fid} {fx['name']}  ({fx['base']})")
    maker = pick(fid, 'RWD')
    if not maker:
        t.check('có user test với quyền RWD', False, 'thêm vào _testdata.yaml')
        return
    viewer = pick(fid, 'R', tenant=maker['tenant'], lacks='W')
    other = pick(fid, 'RWD', not_tenant=maker['tenant'])
    tk = token(maker)
    ex = dict(fx['example'])
    if fx['owner_unit']:
        ex.setdefault('owner_unit', maker['units'][0])
    path = keypath(fx, ex)

    ensure_parents(fx, ex, maker)
    cur = http('GET', path, token=tk)                                      # dọn dữ liệu lần chạy trước
    if cur.status == 200:
        http('DELETE', path, token=tk, query={'row_version': cur.body.get('row_version')})

    t.check('không token → 401', http('GET', fx['base']).status == 401)
    if viewer:
        t.check('viewer SEARCH → 200', http('GET', fx['base'], token=token(viewer)).status == 200)
        r = http('POST', fx['base'], token=token(viewer), body=ex)
        t.check('viewer CREATE → 403 E_FORBIDDEN', r.status == 403 and r.body.get('code') == 'E_FORBIDDEN', r)

    r = http('POST', fx['base'], token=tk, body=ex)
    if not t.check('CREATE ví dụ → 201', r.status == 201, r):
        return
    created = r.body
    t.check('CREATE trả đúng dữ liệu', all(same(created.get(k), v) for k, v in ex.items()),
            {k: (created.get(k), v) for k, v in ex.items() if not same(created.get(k), v)})
    if fx['versioned']:
        t.check('row_version khởi tạo = 0', created.get('row_version') == 0, created.get('row_version'))
    r = http('POST', fx['base'], token=tk, body=ex)
    t.check('CREATE trùng khoá → 409 E_DUPLICATE', r.status == 409 and r.body.get('code') == 'E_DUPLICATE', r)

    for case in fx['invalid']:
        b = dict(ex)
        b[case['field']] = case['value']
        for c in fx['pk']:
            if c != case['field']:
                b[c] = ex[c]
        r = http('POST', fx['base'], token=tk, body=b)
        t.check(f"{case['field']}={case['value']!r} → 400 {case['code']}",
                r.status == 400 and r.body.get('code') == 'E_VALIDATION' and r.detail(case['field'], case['code']), r)
    for ref in fx['refs']:
        b = dict(ex)
        for c in ref['cols']:
            b[c] = 'NOPE' + '0' * 4
        r = http('POST', fx['base'], token=tk, body=b)
        t.check(f"tham chiếu {ref['parent_fid']} không tồn tại → 400 REFERENCE",
                r.status == 400 and r.detail(ref['cols'][0], 'REFERENCE'), r)
    if fx['owner_unit']:
        b = dict(ex, owner_unit='ZZ99')
        r = http('POST', fx['base'], token=tk, body=b)
        t.check('đơn vị ngoài phạm vi → 403 E_SCOPE', r.status == 403 and r.body.get('code') == 'E_SCOPE', r)
    r = http('POST', fx['base'], token=tk, body='{bad json')
    t.check('body không phải JSON object → 400', r.status == 400, r)

    r = http('GET', path, token=tk)
    t.check('GET → 200', r.status == 200, r)
    for s in fx['search']:
        v = ex.get(s['field'])
        if v is None:
            continue
        q = str(v)[1:-1].lower() if s['kind'] == 'like' and len(str(v)) > 2 else v
        r = http('GET', fx['base'], token=tk, query={s['field']: q, 'size': 200})
        found = r.status == 200 and any(all(same(it.get(c), ex[c]) for c in fx['pk']) for it in r.body['items'])
        t.check(f"SEARCH lọc {s['field']} ({s['kind']}) tìm thấy", found, r)
    r = http('GET', fx['base'], token=tk, query={'sort': 'nope'})
    t.check('sort không cho phép → 400', r.status == 400, r)
    r = http('GET', fx['base'], token=tk, query={'size': 1, 'page': 0})
    t.check('phân trang size=1', r.status == 200 and len(r.body['items']) <= 1 and r.body['total'] >= 1, r)

    if other and fx['tenant']:
        t.check('tenant khác GET → 404', http('GET', path, token=token(other)).status == 404)
        r = http('GET', fx['base'], token=token(other), query={'size': 200})
        t.check('tenant khác SEARCH không thấy', r.status == 200 and not any(
            all(same(it.get(c), ex[c]) for c in fx['pk']) for it in r.body['items']), r)

    rv = created.get('row_version')
    if 'UPDATE' in fx['actions'] and fx['update_field']:
        uf = fx['update_field']
        b = dict(created, **{uf: str(ex.get(uf) or 'x')[:40] + ' (sửa)'})
        r = http('PUT', path, token=tk, body=b)
        ok = t.check('UPDATE → 200', r.status == 200, r)
        if ok:
            t.check('UPDATE đổi giá trị', r.body.get(uf) == b[uf], r.body.get(uf))
            if fx['versioned']:
                t.check('UPDATE tăng row_version', r.body.get('row_version') == rv + 1, r.body.get('row_version'))
            r2 = http('PUT', path, token=tk, body=b)                        # vẫn row_version cũ
            t.check('UPDATE row_version cũ → 409 E_CONFLICT',
                    r2.status == 409 and r2.body.get('code') == 'E_CONFLICT', r2)
            rv = r.body.get('row_version')
        if fx['versioned']:
            b2 = dict(b)
            b2.pop('row_version', None)
            r = http('PUT', path, token=tk, body=b2)
            t.check('UPDATE thiếu row_version → 400', r.status == 400 and r.detail('row_version', 'REQUIRED'), r)

    for case in fx['tests']:                                              # test do spec khai báo (hook…)
        b = dict(ex, **case.get('patch', {}))
        if case['action'] == 'CREATE':
            ensure_parents(fx, b, maker)
            r = http('POST', fx['base'], token=tk, body=b)
        else:
            r = http('PUT', keypath(fx, b), token=tk, body=dict(b, row_version=rv))
        exp = case['expect']
        good = r.status == exp['status'] and (not exp.get('field') or r.detail(exp['field'], exp['code']))
        t.check(case['name'], good, r)
        if r.status == 201:
            http('DELETE', keypath(fx, b), token=tk, query={'row_version': r.body.get('row_version')})

    for ch in fx['children']:
        cfx = FX['functions'][ch['child_fid']]
        cb = dict(cfx['example'])
        for c, p in zip(ch['cols'], ch['parent_cols']):
            cb[c] = ex[p]
        if cfx['owner_unit']:
            cb.setdefault('owner_unit', maker['units'][0])
        cpath = keypath(cfx, cb)
        old = http('GET', cpath, token=tk)
        if old.status == 200:
            http('DELETE', cpath, token=tk, query={'row_version': old.body.get('row_version')})
        cr = http('POST', cfx['base'], token=tk, body=cb)
        if not t.check(f"tạo dữ liệu con {ch['child_fid']} → 201", cr.status == 201, cr):
            continue
        if ch['on_delete'] == 'RESTRICT':
            r = http('DELETE', path, token=tk, query={'row_version': rv})
            t.check(f"xoá khi còn {ch['child_fid']} → 409 E_RESTRICT",
                    r.status == 409 and r.body.get('code') == 'E_RESTRICT', r)
        http('DELETE', cpath, token=tk, query={'row_version': cr.body.get('row_version')})

    if viewer:
        r = http('DELETE', path, token=token(viewer), query={'row_version': rv})
        t.check('viewer DELETE → 403', r.status == 403, r)
    if fx['versioned']:
        r = http('DELETE', path, token=tk, query={'row_version': (rv or 0) + 99})
        t.check('DELETE row_version sai → 409 E_CONFLICT', r.status == 409 and r.body.get('code') == 'E_CONFLICT', r)
    r = http('DELETE', path, token=tk, query={'row_version': rv})
    t.check('DELETE → 204', r.status == 204, r)
    t.check('GET sau xoá → 404', http('GET', path, token=tk).status == 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only')
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    print(f"Backend: {BASE}")
    if not wait_ready():
        print("✗ backend không lên sau 120s")
        sys.exit(2)
    t = T(a.verbose)
    if not a.only:
        test_core(t)
    # cha trước con: function không tham chiếu ai chạy trước
    order = sorted(FX['functions'], key=lambda f: (len(FX['functions'][f]['refs']), f))
    for fid in order:
        if a.only and fid != a.only:
            continue
        test_function(t, fid)
    print(f"\n{t.ok} đạt · {t.fail} hỏng")
    for f in t.failures:
        print(f"  ✗ {f}")
    sys.exit(1 if t.fail else 0)


if __name__ == '__main__':
    main()
