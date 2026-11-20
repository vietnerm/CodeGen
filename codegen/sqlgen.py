"""
SQL: viết MỘT lần theo dialect chuẩn (PostgreSQL), sqlglot kiểm tra + chuyển sang dialect khác.

Quy tắc (kiểm bằng AST, áp dụng cho cả SQL do người/AI viết):
  • chỉ dùng tập SQL chạy được trên mọi DB đích
  • thao tác đặc thù DB (upsert, RETURNING, JSON, mảng, phân trang) KHÔNG viết bằng SQL
    mà gọi API của core (core cài riêng cho từng DBType)
Định dạng file catalog (FlowSQL chạy thẳng, tham số :name):
    -- name: ATA0_0110.get
    -- params: _tenant, _units, device_id
    -- <khoá>: <giá trị>            (meta tuỳ chọn: sort, pk, like…)
    SELECT …;
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

SQLGLOT_DIALECT = {'postgresql': 'postgres', 'mysql': 'mysql', 'oracle': 'oracle', 'sqlserver': 'tsql'}
CANONICAL = 'postgresql'


def _node(name):
    return getattr(exp, name, None)


FORBIDDEN = [(c, msg) for c, msg in [
    (_node('OnConflict'), "ON CONFLICT/upsert không chuyển được giữa các DB — dùng core upsert"),
    (_node('Returning'), "RETURNING không có trên MySQL — FlowSQL insert() đã trả khoá tự sinh"),
    (_node('ILike'), "ILIKE không chuyển được sang SQL Server — dùng LOWER(col) LIKE LOWER(:p)"),
    (_node('Any'), "= ANY(:mảng) chỉ có trên PostgreSQL — dùng IN (:list), core tự bung danh sách"),
    (_node('JSONExtract'), "toán tử JSON khác nhau giữa các DB — dùng hàm JSON của core"),
    (_node('JSONExtractScalar'), "toán tử JSON khác nhau giữa các DB — dùng hàm JSON của core"),
    (_node('JSONBExtract'), "toán tử JSONB chỉ có trên PostgreSQL"),
    (_node('JSONBExtractScalar'), "toán tử JSONB chỉ có trên PostgreSQL"),
    (_node('JSONBContains'), "toán tử JSONB chỉ có trên PostgreSQL"),
    (_node('ArrayContains'), "toán tử mảng chỉ có trên PostgreSQL"),
    (_node('Limit'), "LIMIT/OFFSET — phân trang do core thêm theo dialect"),
    (_node('Create'), "DDL không đặt trong catalog — khai báo entity trong spec"),
    (_node('Drop'), "DDL không đặt trong catalog"),
    (_node('Alter'), "DDL không đặt trong catalog"),
    (_node('Command'), "câu lệnh sqlglot không phân tích được"),
] if c is not None]

RE_PARAM_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


class SqlLintError(Exception):
    pass


# ─────────────────────── tham số :name (cùng ngữ nghĩa FlowSQL) ───────────────────────
def params_of(sql: str) -> list[str]:
    """Tên :param theo thứ tự xuất hiện, bỏ qua '…', "…", `…`, -- , /* */ và ::cast."""
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in "'\"`":
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:   # '' trong chuỗi
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
        elif sql.startswith('--', i):
            j = sql.find('\n', i)
            i = n if j < 0 else j
        elif sql.startswith('/*', i):
            j = sql.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif ch == ':' and i + 1 < n and sql[i + 1] == ':':
            i += 2
        elif ch == ':' and (i == 0 or sql[i - 1] != ':'):
            m = RE_PARAM_NAME.match(sql, i + 1)
            if m:
                if m.group(0) not in out:
                    out.append(m.group(0))
                i = m.end()
            else:
                i += 1
        else:
            i += 1
    return out


# ─────────────────────── lint + transpile ───────────────────────
def lint(sql: str, where: str, kind='stmt') -> list[str]:
    errs = []
    try:
        tree = sqlglot.parse_one(_wrap(sql, kind), read=SQLGLOT_DIALECT[CANONICAL])
    except Exception as e:
        return [f"{where}: sqlglot không phân tích được: {e}"]
    for node_cls, msg in FORBIDDEN:
        if tree.find(node_cls):
            errs.append(f"{where}: {msg}")
    for sel in tree.find_all(exp.Select):
        if any(isinstance(x, exp.Star) for x in sel.expressions):
            errs.append(f"{where}: không dùng SELECT * — liệt kê cột để API ổn định")
    return errs


def _wrap(sql, kind):
    return f"SELECT 1 FROM t WHERE {sql}" if kind == 'cond' else sql


def transpile(sql: str, dialect: str, kind='stmt') -> str:
    if dialect == CANONICAL:
        return sql
    tree = sqlglot.parse_one(_wrap(sql, kind), read=SQLGLOT_DIALECT[CANONICAL])
    if kind == 'cond':
        tree = tree.args['where'].this
    return tree.sql(dialect=SQLGLOT_DIALECT[dialect], unsupported_level=sqlglot.ErrorLevel.RAISE)


# ─────────────────────── statement ───────────────────────
def stmt(name, sql, kind='stmt', **meta):
    return {'name': name, 'sql': sql.strip(), 'kind': kind, 'params': params_of(sql), 'meta': meta}


def parse_catalog(text: str, where: str) -> list[dict]:
    """Đọc file catalog viết tay (core/sql/*.sql) cùng định dạng."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r'^--\s*name:\s*(\S+)\s*$', line)
        if m:
            if cur:
                out.append(cur)
            cur = {'name': m.group(1), 'meta': {}, 'lines': [], 'kind': 'stmt'}
            continue
        if cur is None:
            continue
        mm = re.match(r'^--\s*([a-z_]+):\s*(.*)$', line)
        if mm and not cur['lines']:
            k, v = mm.groups()
            if k == 'kind':
                cur['kind'] = v.strip()
            elif k != 'params':
                cur['meta'][k] = v.strip()
            continue
        cur['lines'].append(line)
    if cur:
        out.append(cur)
    res = []
    for c in out:
        sql = '\n'.join(c['lines']).strip().rstrip(';').strip()
        if not sql:
            raise SqlLintError(f"{where}: {c['name']} rỗng")
        res.append(stmt(c['name'], sql, c['kind'], **c['meta']))
    return res


def render_catalog(stmts: list[dict], dialect: str, header: str) -> str:
    parts = [header.rstrip(), '']
    for s in stmts:
        parts.append(f"-- name: {s['name']}")
        if s['kind'] != 'stmt':
            parts.append(f"-- kind: {s['kind']}")
        parts.append(f"-- params: {', '.join(s['params'])}")
        for k, v in s['meta'].items():
            parts.append(f"-- {k}: {v}")
        parts.append(transpile(s['sql'], dialect, s['kind']) + ';')
        parts.append('')
    return '\n'.join(parts)


# ─────────────────────── SQL sinh cho 1 function CRUD ───────────────────────
def function_statements(ir, fn, ent_of) -> list[dict]:
    e = ent_of(fn['entity'])
    t, fid = e['table'], fn['id']
    # Đọc dùng alias t + LEFT JOIN cho lookup (cột hiển thị của bảng cha); ghi không dùng alias.
    cols = ', '.join(f"t.{f['name']}" for f in e['base_api_fields'])
    joins, jcols = [], []
    for lf in e['lookup_fields']:
        lk = lf['lookup']
        r = next(x for x in fn['refs'] if x['slug'] == lk['rel'])
        j = lk['join']
        on = ' AND '.join(f"{j}.{p} = t.{c}" for c, p in zip(r['cols'], r['parent_cols']))
        if r['tenant_scoped']:
            on = f"{j}.tenant_id = t.tenant_id AND {on}"
        joins.append(f" LEFT JOIN {lk['parent_table']} {j} ON {on}")
        jcols.append(f"{j}.{lk['parent_field']} AS {lf['name']}")
    sel_cols = ', '.join([cols] + jcols)
    scope = []
    if e['tenant']:
        scope.append('t.tenant_id = :_tenant')
    if e['owner_unit']:
        scope.append('t.owner_unit IN (:_units)')
    where_scope = ' AND '.join(scope) if scope else '1 = 1'
    pk_t = ' AND '.join(f"t.{c} = :{c}" for c in e['pk'])
    src = f"{t} t{''.join(joins)}"
    out = [
        stmt(f"{fid}.select", f"SELECT {sel_cols} FROM {src} WHERE {where_scope}",
             sort=','.join(e['sort_fields']), pk=','.join(e['pk']), alias='t'),
        stmt(f"{fid}.count", f"SELECT COUNT(*) AS cnt FROM {t} t WHERE {where_scope}"),
    ]
    for f in e['search_fields']:
        c = f['name']
        if f['search'] == 'like':
            out.append(stmt(f"{fid}.filter.{c}", f"LOWER(t.{c}) LIKE LOWER(:f_{c})", 'cond', like='true'))
        else:
            out.append(stmt(f"{fid}.filter.{c}", f"t.{c} = :f_{c}", 'cond'))
    out.append(stmt(f"{fid}.get", f"SELECT {sel_cols} FROM {src} WHERE {where_scope} AND {pk_t}"))
    if fn['master']:                                      # bảng con: đọc các dòng của 1 bản ghi cha
        m = fn['master']
        mcond = ' AND '.join(f"t.{c} = :{c}" for c in m['cols'])
        mten = 't.tenant_id = :_tenant AND ' if e['tenant'] else ''
        order = ', '.join(f"t.{c}" for c in e['pk'])
        out.append(stmt(f"{fid}.by_master", f"SELECT {sel_cols} FROM {src} WHERE {mten}{mcond} ORDER BY {order}"))
    pk_cond = ' AND '.join(f"{c} = :{c}" for c in e['pk'])
    ten = 'tenant_id = :_tenant AND ' if e['tenant'] else ''
    ver = ' AND row_version = :row_version' if e['versioned'] else ''
    scope = (['tenant_id = :_tenant'] if e['tenant'] else []) + (['owner_unit IN (:_units)'] if e['owner_unit'] else [])
    where_scope = ' AND '.join(scope) if scope else '1 = 1'   # câu ghi (UPDATE/DELETE) không dùng alias
    out.append(stmt(f"{fid}.exists", f"SELECT COUNT(*) AS cnt FROM {t} WHERE {ten}{pk_cond}"))

    ins_c, ins_v = [], []
    for f in e['fields']:
        n = f['name']
        if n == 'tenant_id':
            ins_c.append(n), ins_v.append(':_tenant')
        elif n in ('create_id', 'update_id'):
            ins_c.append(n), ins_v.append(':_user')
        elif f['readonly'] or f['identity']:
            continue
        else:
            ins_c.append(n), ins_v.append(f":{n}")
    out.append(stmt(f"{fid}.insert", f"INSERT INTO {t} ({', '.join(ins_c)}) VALUES ({', '.join(ins_v)})"))

    sets = [f"{f['name']} = :{f['name']}" for f in e['input_fields']]
    if e['audit_cols']:
        sets += ['update_id = :_user', 'update_dt = CURRENT_TIMESTAMP']
    if e['versioned']:
        sets.append('row_version = row_version + 1')
    out.append(stmt(f"{fid}.update", f"UPDATE {t} SET {', '.join(sets)} WHERE {where_scope} AND {pk_cond}{ver}"))
    out.append(stmt(f"{fid}.delete", f"DELETE FROM {t} WHERE {where_scope} AND {pk_cond}{ver}"))

    for r in fn['refs']:                                  # mình là con → kiểm tra cha tồn tại
        pe = ent_of(r['parent'])
        cond = ' AND '.join(f"{p} = :{c}" for c, p in zip(r['cols'], r['parent_cols']))
        pten = 'tenant_id = :_tenant AND ' if r['tenant_scoped'] else ''
        out.append(stmt(f"{fid}.ref.{r['slug']}", f"SELECT COUNT(*) AS cnt FROM {pe['table']} WHERE {pten}{cond}",
                        cols=','.join(r['cols']), parent=r['parent'], label=r['label']))
    for r in fn['children']:                              # mình là cha → RESTRICT/CASCADE/NULLIFY
        ce = ent_of(r['child'])
        cond = ' AND '.join(f"{c} = :{p}" for c, p in zip(r['cols'], r['parent_cols']))
        cten = 'tenant_id = :_tenant AND ' if r['tenant_scoped'] else ''
        if r['on_delete'] == 'RESTRICT':
            out.append(stmt(f"{fid}.children.{r['slug']}",
                            f"SELECT COUNT(*) AS cnt FROM {ce['table']} WHERE {cten}{cond}",
                            child=r['child'], label=ce['label']))
        elif r['on_delete'] == 'CASCADE':
            out.append(stmt(f"{fid}.cascade.{r['slug']}", f"DELETE FROM {ce['table']} WHERE {cten}{cond}"))
        else:
            sets = ', '.join(f"{c} = NULL" for c in r['cols'])
            out.append(stmt(f"{fid}.nullify.{r['slug']}", f"UPDATE {ce['table']} SET {sets} WHERE {cten}{cond}"))
    return out


def lit(v) -> str:
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return "'Y'" if v else "'N'"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"
