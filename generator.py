#!/usr/bin/env python3
"""
CodeGen — spec YAML → IR → target packs.

    python generator.py validate            # kiểm tra spec + SQL (exit 1 nếu lỗi) — dùng trong CI
    python generator.py build [-o out]      # sinh toàn bộ dự án vào out/
    python generator.py ir                  # in IR (JSON) — đầu vào cho agent / target mới
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from codegen import model, render, sqlgen  # noqa: E402


def check_sql(ir) -> list[str]:
    """Lint toàn bộ SQL (sinh ra + core viết tay) và thử chuyển sang mọi dialect."""
    errs = []
    ents = {e['id']: e for e in ir['entities']}
    stmts = []
    for fn in model.crud_functions(ir):
        stmts += sqlgen.function_statements(ir, fn, ents.get)
    for p in sorted((ROOT / 'core' / 'sql').glob('*.sql')):
        try:
            stmts += sqlgen.parse_catalog(p.read_text(encoding='utf-8'), str(p.relative_to(ROOT)))
        except sqlgen.SqlLintError as e:
            errs.append(str(e))
    names = [s['name'] for s in stmts]
    errs += [f"trùng tên câu SQL: {n}" for n in sorted({n for n in names if names.count(n) > 1})]
    for s in stmts:
        errs += sqlgen.lint(s['sql'], s['name'], s['kind'])
        for d in ir['dialects'][1:]:
            try:
                sqlgen.transpile(s['sql'], d, s['kind'])
            except Exception as e:
                errs.append(f"{s['name']}: không chuyển được sang {d}: {e}")
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['validate', 'build', 'ir'])
    ap.add_argument('--spec', type=Path, default=ROOT / 'spec')
    ap.add_argument('-o', '--out', type=Path, default=ROOT / 'out')
    args = ap.parse_args()

    ir, rep = model.build_ir(args.spec)
    if not rep.errors:
        rep.errors += [f"✗ sql {e}" for e in check_sql(ir)]
    for w in rep.warnings:
        print(w)
    for e in rep.errors:
        print(e)
    crud = model.crud_functions(ir)
    print(f"{len(ir['functions'])} function ({len(crud)} CRUD) · {len(ir['entities'])} entity · "
          f"{len(ir['relations'])} quan hệ · {len(ir['codemaps'])} nhóm codemap · "
          f"dialect {', '.join(ir['dialects'])} · {len(rep.errors)} lỗi · {len(rep.warnings)} cảnh báo")
    if rep.errors:
        sys.exit(1)
    if args.command == 'validate':
        return
    if args.command == 'ir':
        print(json.dumps(ir, ensure_ascii=False, indent=2, default=str))
        return

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    (args.out / 'ir.json').write_text(json.dumps(ir, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"→ build vào {args.out}")
    res = render.run(ir, ROOT, args.out)
    for c in res['custom_created']:
        print(f"  + tạo mới (sửa tiếp được): {c}")
    print(f"✓ {len(res['written'])} file")


if __name__ == '__main__':
    main()
