#!/usr/bin/env python3
"""
Chạy THẬT mọi câu SQL trong catalog trên 1 DB (trong transaction rồi rollback) với tham số mẫu
lấy từ fixtures. Bắt lỗi cú pháp/kiểu theo từng dialect mà sqlglot không bắt được.

    python scripts/catalog_check.py --dialect postgresql --dsn "host=... dbname=... user=... password=..."
    python scripts/catalog_check.py --dialect mysql --dsn "host=...;port=3306;user=...;password=...;db=..."
Cần: psycopg (postgresql) hoặc pymysql (mysql).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from codegen.sqlgen import parse_catalog  # noqa: E402

PAGE = {'postgresql': ' LIMIT %(_limit)s OFFSET %(_offset)s', 'mysql': ' LIMIT %(_limit)s OFFSET %(_offset)s'}
PARAM = re.compile(r'(?<!:):([A-Za-z_][A-Za-z0-9_]*)')


def to_pyformat(sql, params):
    sql = sql.replace('%', '%%')
    out = {}

    def rep(m):
        n = m.group(1)
        v = params.get(n)
        if isinstance(v, (list, tuple)):
            if not v:
                return 'NULL'
            for i, x in enumerate(v):
                out[f"{n}_{i}"] = x
            return ', '.join(f"%({n}_{i})s" for i in range(len(v)))
        out[n] = v
        return f"%({n})s"
    return PARAM.sub(rep, sql), out


def connect(dialect, dsn):
    if dialect == 'postgresql':
        import psycopg
        return psycopg.connect(dsn)
    import pymysql
    kv = dict(x.split('=', 1) for x in dsn.split(';') if x)
    return pymysql.connect(host=kv.get('host', 'localhost'), port=int(kv.get('port', 3306)), user=kv['user'],
                           password=kv.get('password', ''), database=kv.get('db'), autocommit=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dialect', required=True)
    ap.add_argument('--dsn', required=True)
    ap.add_argument('--out', default=str(ROOT / 'out'))
    a = ap.parse_args()
    out = Path(a.out)
    fx = json.loads((out / 'tests/http/fixtures.json').read_text(encoding='utf-8'))
    u = fx['users'][0]
    base = {'_tenant': u['tenant'], '_user': u['user_id'], '_units': u['units'], 'user_id': u['user_id'],
            'group_code': 'STATUS_AI', 'code': 'A', 'lang': 'vi', 'function_id': next(iter(fx['functions'])),
            'action': 'CHECK', 'target': 'catalog_check', 'detail': '{}', '_limit': 5, '_offset': 0, 'row_version': 0}
    for f in fx['functions'].values():
        base.update({k: v for k, v in f['example'].items()})
        base.update({f"f_{s['field']}": f['example'].get(s['field']) for s in f['search']})
    cat = out / 'catalog' / a.dialect
    conn = connect(a.dialect, a.dsn)
    ok = bad = 0
    for name in (cat / 'index.txt').read_text().split():
        for s in parse_catalog((cat / name).read_text(encoding='utf-8'), name):
            sql = s['sql']
            if s['kind'] == 'cond':                       # điều kiện lọc: ghép vào câu select của function
                fid = s['name'].split('.')[0]
                sel = next(x for x in parse_catalog((cat / f"{fid}.sql").read_text(encoding='utf-8'), name)
                           if x['name'] == f"{fid}.select")
                sql = f"{sel['sql']} AND ({sql})"
            q, p = to_pyformat(sql, base)
            if s['name'].endswith('.select'):
                pk = s['meta'].get('pk', '')
                q += f" ORDER BY {pk}" + PAGE[a.dialect]
                p.update(_limit=5, _offset=0)
            cur = conn.cursor()
            try:
                cur.execute(q, p)
                if cur.description:
                    cur.fetchall()
                ok += 1
            except Exception as e:
                bad += 1
                print(f"✗ {s['name']}: {str(e).splitlines()[0]}\n    {q[:200]}")
            finally:
                conn.rollback()
    conn.close()
    print(f"{a.dialect}: {ok} câu chạy được · {bad} lỗi")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
