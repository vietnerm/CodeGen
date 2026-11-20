"""
DDL + seed + dữ liệu test + kiểm tra toàn vẹn cho 1 dialect.

DDL sinh TRỰC TIẾP theo bảng ánh xạ kiểu của target (không qua sqlglot — sqlglot làm sai
kiểu như JSONB/timestamptz). Biểu thức CHECK, seed, integrity viết theo dialect chuẩn rồi
chuyển bằng sqlglot như mọi SQL khác.
"""
from __future__ import annotations

import base64
import hashlib

from . import sqlgen
from .sqlgen import lit

PBKDF2_ITER = 120_000


def password_hash(user_id: str, password: str) -> str:
    """Cùng định dạng core Java kiểm tra: pbkdf2_sha256$iter$salt_b64$hash_b64.
    Salt suy từ user_id CHỈ cho dữ liệu test (để build lặp lại cho cùng kết quả)."""
    salt = hashlib.sha256(f"test-salt:{user_id}".encode()).digest()[:16]
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _coltype(f, types):
    t = f['type']
    if t == 'TEXT':
        return types['TEXT_N'].format(n=f['length']) if f['length'] else types['TEXT']
    if t == 'DECIMAL':
        return types['DECIMAL'].format(p=f['precision'], s=f['scale'])
    return types[t]


def _default(f, types):
    d = f['default']
    if d is None:
        return None
    if d == 'now':
        return types['NOW']
    return lit(d)


def _checks(e, dialect):
    t = e['name']
    out = []
    for f in e['fields']:
        c = f['name']
        if f['enum']:
            out.append((f"ck_{t}_{c}", f"{c} IN ({', '.join(lit(x) for x in f['enum'])})"))
        if f['pattern']:
            out.append((f"ck_{t}_{c}_fmt", f"{c} ~ {lit(f['pattern'])}"))
        if f['min'] is not None:
            out.append((f"ck_{t}_{c}_min", f"{c} >= {f['min']}"))
        if f['max'] is not None:
            out.append((f"ck_{t}_{c}_max", f"{c} <= {f['max']}"))
    for ck in e['checks']:
        out.append((f"ck_{t}_{ck['name']}", ck['expr']))
    return [(n, sqlgen.transpile(x, dialect, 'cond')) for n, x in out]


def schema_ddl(ir, dialect, types, header) -> str:
    out = [header, '']
    for s in sorted({e['schema'] for e in ir['entities']}):
        out.append(types['CREATE_SCHEMA'].format(s=s))
    out.append('')
    for e in ir['entities']:
        lines = []
        for f in e['fields']:
            parts = [f['name'], _coltype(f, types)]
            if f['identity']:
                parts.append(types['IDENTITY'])
            d = _default(f, types)
            if d is not None:
                parts.append(f"DEFAULT {d}")
            if not f['nullable']:
                parts.append('NOT NULL')
            if types.get('INLINE_COMMENT'):
                parts.append(f"COMMENT {lit(f['label'])}")
            lines.append('    ' + ' '.join(parts))
        lines.append(f"    CONSTRAINT pk_{e['name']} PRIMARY KEY ({', '.join(e['physical_pk'])})")
        for name, expr in _checks(e, dialect):
            lines.append(f"    CONSTRAINT {name} CHECK ({expr})")
        # index: khai báo + cột con của quan hệ (thay cho index FK); bỏ cái đã được key phủ
        idx = list(e['indexes']) + [(['tenant_id'] if r['tenant_scoped'] else []) + r['cols']
                                    for r in ir['relations'] if r['child'] == e['id']]
        done, idx_sql = [e['physical_pk']], []
        for cols in idx:
            if any(k[:len(cols)] == cols for k in done):
                continue
            done.append(cols)
            iname = f"ix_{e['name']}_{'_'.join(cols)}"[:63]
            if types.get('INLINE_INDEX'):
                lines.append(f"    INDEX {iname} ({', '.join(cols)})")
            else:
                idx_sql.append(types['CREATE_INDEX'].format(name=iname, table=e['table'], cols=', '.join(cols)))
        tail = types.get('TABLE_SUFFIX', '')
        if types.get('INLINE_COMMENT'):
            tail += f" COMMENT={lit(e['label'])}"
        kind = 'core' if e['core'] else f"function {e['function']}"
        out.append(f"-- {e['label']} ({kind})")
        out.append(f"CREATE TABLE IF NOT EXISTS {e['table']} (\n" + ',\n'.join(lines) + f"\n){tail};")
        if not types.get('INLINE_COMMENT'):
            out.append(f"COMMENT ON TABLE {e['table']} IS {lit(e['label'])};")
            for f in e['fields']:
                out.append(f"COMMENT ON COLUMN {e['table']}.{f['name']} IS {lit(f['label'])};")
        out += idx_sql
        out.append('')
    return '\n'.join(out)


def _insert(table, rows):
    if not rows:
        return []
    cols = list(rows[0].keys())
    vals = ',\n    '.join('(' + ', '.join(lit(r[c]) for c in cols) + ')' for r in rows)
    return [f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n    {vals}"]


def _render(stmts, dialect, types, header):
    body = [sqlgen.transpile(s, dialect) + ';' for s in stmts]
    return '\n'.join([header, '', types['BEGIN']] + body + [types['COMMIT'], ''])


def seed_sql(ir, dialect, types, header) -> str:
    import json
    groups = [g['group'] for g in ir['codemaps']]
    glist = ', '.join(lit(g) for g in groups)
    st = [
        f"DELETE FROM zz.codemap_label WHERE tenant_id = '*' AND group_code IN ({glist})",
        f"DELETE FROM zz.codemap WHERE tenant_id = '*' AND group_code IN ({glist})",
        f"DELETE FROM zz.codemap_group WHERE group_code IN ({glist})",
    ]
    st += _insert('zz.codemap_group', [
        {'group_code': g['group'], 'module_prefix': g['module'], 'group_name': g['name'],
         'parent_group': g['parent_group'],
         'attr_fields': json.dumps(g['attr_fields'], ensure_ascii=False) if g['attr_fields'] else None,
         'tenant_editable': 'Y' if g['tenant_editable'] else 'N', 'create_id': 'codegen', 'update_id': 'codegen'}
        for g in ir['codemaps']])
    codes = [(g, c) for g in ir['codemaps'] for c in g['codes']]
    st += _insert('zz.codemap', [
        {'tenant_id': '*', 'group_code': g['group'], 'code': c['code'], 'parent_code': c['parent_code'],
         'seq': c['seq'], 'attrs': json.dumps(c['attrs'], ensure_ascii=False) if c['attrs'] else None,
         'is_system': 'Y' if c['system'] else 'N', 'create_id': 'codegen', 'update_id': 'codegen'}
        for g, c in codes])
    st += _insert('zz.codemap_label', [
        {'tenant_id': '*', 'group_code': g['group'], 'code': c['code'], 'lang': 'vi', 'label': c['label']}
        for g, c in codes])
    fids = ', '.join(lit(f['id']) for f in ir['functions'])
    st += [f"DELETE FROM zz.function_tree WHERE function_id IN ({fids})",
           f"DELETE FROM zz.function WHERE function_id IN ({fids})"]
    st += _insert('zz.function', [
        {'function_id': f['id'], 'module_prefix': f['module'], 'function_name': f['name'],
         'function_type': f['type'], 'url': f['url'], 'sort_order': f['sort']} for f in ir['functions']])
    st += _insert('zz.function_tree', [
        {'function_id': f['id'], 'parent_function_id': f['parent']} for f in ir['functions'] if f['parent']])
    return _render(st, dialect, types, header)


def testdata_sql(ir, dialect, types, header) -> str:
    td = ir['testdata']
    if not td:
        return header + '\n-- (không có _testdata.yaml)\n'
    users = td.get('users') or []
    roles = td.get('roles') or []
    tenants = td.get('tenants') or []
    ulist = ', '.join(lit(u['user_id']) for u in users) or "''"
    rlist = ', '.join(lit(r['role_id']) for r in roles) or "''"
    tlist = ', '.join(lit(t) for t in tenants) or "''"
    st = []
    for e in ir['entities']:                              # dữ liệu nghiệp vụ của tenant test
        if e['tenant'] and not e['core']:
            st.append(f"DELETE FROM {e['table']} WHERE tenant_id IN ({tlist})")
    st += [f"DELETE FROM zz.codemap_label WHERE tenant_id IN ({tlist})",
           f"DELETE FROM zz.codemap WHERE tenant_id IN ({tlist})",
           f"DELETE FROM zz.user_role WHERE user_id IN ({ulist})",
           f"DELETE FROM zz.user_unit WHERE user_id IN ({ulist})",
           f"DELETE FROM zz.app_credential WHERE user_id IN ({ulist})",
           f"DELETE FROM zz.app_user WHERE user_id IN ({ulist})",
           f"DELETE FROM zz.role_function WHERE role_id IN ({rlist})",
           f"DELETE FROM zz.role WHERE role_id IN ({rlist})"]
    st += _insert('zz.role', [{'role_id': r['role_id'], 'role_name': r['role_name'],
                               'create_id': 'codegen', 'update_id': 'codegen'} for r in roles])
    bits = {'R': 1, 'W': 2, 'D': 4, 'X': 8}
    st += _insert('zz.role_function', [
        {'role_id': r['role_id'], 'function_id': fid, 'right_mask': sum(bits[c] for c in set(rights)),
         'create_id': 'codegen', 'update_id': 'codegen'}
        for r in roles for fid, rights in (r.get('grants') or {}).items()])
    st += _insert('zz.app_user', [{'user_id': u['user_id'], 'user_name': u['user_name'],
                                   'create_id': 'codegen', 'update_id': 'codegen'} for u in users])
    st += _insert('zz.app_credential', [{'user_id': u['user_id'],
                                         'password_hash': password_hash(u['user_id'], u['password'])}
                                        for u in users])
    st += _insert('zz.user_unit', [
        {'tenant_id': u['tenant'], 'user_id': u['user_id'], 'unit_code': unit,
         'is_primary': 'Y' if i == 0 else 'N'}
        for u in users for i, unit in enumerate(u.get('units') or [])])
    st += _insert('zz.user_role', [
        {'tenant_id': u['tenant'], 'user_id': u['user_id'], 'role_id': rl, 'approval_status': 'A',
         'assigner_id': 'codegen', 'approver_id': 'codegen-checker', 'create_id': 'codegen',
         'update_id': 'codegen'} for u in users for rl in u.get('roles') or []])
    ov = td.get('codemap_overrides') or []
    st += _insert('zz.codemap', [
        {'tenant_id': o['tenant'], 'group_code': o['group'], 'code': o['code'],
         'status': o.get('status', 'A'), 'create_id': 'codegen', 'update_id': 'codegen'} for o in ov])
    st += _insert('zz.codemap_label', [
        {'tenant_id': o['tenant'], 'group_code': o['group'], 'code': o['code'], 'lang': 'vi',
         'label': o['label']} for o in ov if o.get('label')])
    return _render(st, dialect, types, header)


def integrity_sql(ir, dialect, types, header) -> str:
    """1 câu SELECT: mỗi dòng trả về = 1 loại lỗi toàn vẹn (rỗng = sạch)."""
    ents = {e['id']: e for e in ir['entities']}
    parts = []
    for r in ir['relations']:
        ce, pe = ents[r['child']], ents[r['parent']]
        nn = ' AND '.join(f"c.{c} IS NOT NULL" for c in r['cols'])
        jn = ' AND '.join(f"p.{p} = c.{c}" for c, p in zip(r['cols'], r['parent_cols']))
        if r['tenant_scoped']:
            jn += ' AND p.tenant_id = c.tenant_id'
        parts.append(f"SELECT {lit('orphan ' + r['id'])} AS problem, COUNT(*) AS cnt FROM {ce['table']} c "
                     f"WHERE {nn} AND NOT EXISTS (SELECT 1 FROM {pe['table']} p WHERE {jn})")
    for e in ir['entities']:
        for f in e['fields']:
            if not f['codemap']:
                continue
            ten = "m.tenant_id IN (c.tenant_id, '*')" if e['tenant'] else "m.tenant_id = '*'"
            label = f"codemap {e['id']}.{f['name']}"
            parts.append(f"SELECT {lit(label)} AS problem, "
                         f"COUNT(*) AS cnt FROM {e['table']} c WHERE c.{f['name']} IS NOT NULL AND NOT EXISTS "
                         f"(SELECT 1 FROM zz.codemap m WHERE m.group_code = {lit(f['codemap'])} "
                         f"AND m.code = c.{f['name']} AND {ten})")
    parts.append("SELECT 'function_tree parent missing' AS problem, COUNT(*) AS cnt FROM zz.function_tree t "
                 "WHERE NOT EXISTS (SELECT 1 FROM zz.function f WHERE f.function_id = t.parent_function_id)")
    union = '\nUNION ALL\n'.join(parts)
    sql = f"SELECT problem, cnt FROM (\n{union}\n) x WHERE cnt > 0"
    return f"{header}\n\n{sqlgen.transpile(sql, dialect)};\n"
