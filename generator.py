#!/usr/bin/env python3
"""
CodeGen — spec YAML → IR → target packs.

    python generator.py validate            # kiểm tra spec + SQL (exit 1 nếu lỗi) — dùng trong CI
    python generator.py build [-o out]      # sinh toàn bộ dự án vào out/
    python generator.py ir                  # in IR (JSON) — đầu vào cho agent / target mới
    python generator.py context "mô tả"     # phần IR liên quan tới mô tả (ngữ cảnh cho AI)
    python generator.py impact ATA0_0110    # đổi chức năng này ảnh hưởng tới đâu
    python generator.py schema              # JSON schema động cho AI (chỉ nhận giá trị đang có)

Cache build (PR-16 — dùng để BỎ QUA bước nặng mvn/test, không phải sinh tách phần):
    python generator.py changes             # bảng FID | trạng thái | lý do (so state xanh trước)
          [--base <ref>] [--state <file>] [--json]
    python generator.py ghash               # in G (phần nền) — làm key actions/cache ở CI
    python generator.py skip-build          # in "skip|build + lý do" — pipeline dùng trước mvn
    python generator.py save-state          # ghi .cache/build-state.json (pipeline gọi sau khi xanh)
    python generator.py clear-cache         # xoá .cache/
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from codegen import ai, fingerprint, model, render, sqlgen  # noqa: E402


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
    ap.add_argument('command',
                    choices=['validate', 'build', 'ir', 'context', 'impact', 'schema',
                             'changes', 'ghash', 'skip-build', 'save-state', 'clear-cache'])
    ap.add_argument('arg', nargs='?', help='mô tả (context) hoặc mã chức năng (impact)')
    ap.add_argument('--spec', type=Path, default=ROOT / 'spec')
    ap.add_argument('-o', '--out', type=Path, default=ROOT / 'out')
    ap.add_argument('--base', help='changes: so với ref git (vd origin/main) thay vì state')
    ap.add_argument('--state', type=Path, default=None,
                    help='changes: file state để so (mặc định .cache/build-state.json nếu có)')
    ap.add_argument('--json', action='store_true', help='in JSON thay vì bảng (cho script/comment PR)')
    args = ap.parse_args()

    # ── nhóm lệnh KHÔNG cần IR (nhanh, dùng trước mọi việc nặng) ──
    if args.command == 'ghash':
        print(fingerprint.g_hash(ROOT))
        return
    if args.command == 'skip-build':
        do, why = fingerprint.skip_build(ROOT)
        print(('skip' if do else 'build') + '\t' + why)
        return
    if args.command == 'clear-cache':
        removed = fingerprint.clear_cache(ROOT)
        print('đã xoá: ' + (', '.join(removed) or '(trống — chưa có cache)'))
        return

    ir, rep = model.build_ir(args.spec)
    if args.command in ('changes', 'save-state'):                # cache build (PR-16)
        if rep.errors:
            print('\n'.join(rep.errors), file=sys.stderr)
            sys.exit(1)
        if args.command == 'save-state':
            st = fingerprint.save_state(ROOT, ir)
            print(f"✓ ghi {fingerprint.state_path(ROOT)} (G={st['G'][:12]}…, {len(st['fp'])} FID, "
                  f"sha out/app={st['out_app_sha'][:12]}…)")
            return
        state = None
        if args.base:
            state = fingerprint.fingerprints_at_ref(ROOT, args.base)
        else:
            sp = args.state or fingerprint.state_path(ROOT)
            if sp.exists():
                state = json.loads(sp.read_text(encoding='utf-8'))
            elif args.state is not None:
                sys.exit(f"không có file state: {sp}")
            else:
                sys.exit('chưa có .cache/build-state.json (pipeline ghi sau lần chạy xanh) '
                         '— dùng --base <ref> để so với nhánh gốc')
        res = fingerprint.diff(state, fingerprint.fingerprints(ROOT, args.spec, ir), ir)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        mark = {'moi': 'mới', 'doi': 'đổi', 'xoa': 'xoá', 'giu': 'giữ'}
        if res['all']:
            print(f"ALL — {res['reason_all']}")
            print('(không so từng chức năng khi phần nền đổi)')
            return
        w = max((len(r['fid']) for r in res['rows']), default=3)
        print(f"{'FID'.ljust(w)}  trạng thái  lý do")
        for r in res['rows']:
            print(f"{r['fid'].ljust(w)}  {mark[r['status']]:10}  {r['reason']}")
        if res['affected']:
            print('bị ảnh hưởng: ' + ', '.join(res['affected']))
        elif res['rows']:
            print('không có gì đổi về IR — có thể bỏ qua các bước nặng')
        return
    if args.command in ('context', 'impact', 'schema'):          # công cụ cho agent: in JSON, không ồn
        if rep.errors:
            print('\n'.join(rep.errors), file=sys.stderr)
            sys.exit(1)
        if args.command == 'context':
            res = ai.context(ir, args.arg or '')
        elif args.command == 'impact':
            try:
                res = ai.impact(ir, args.arg or '')
            except KeyError:
                sys.exit(f"không có chức năng {args.arg}")
        else:
            res = ai.dynamic_schema(ir, json.loads((ROOT / 'schema/function-spec.schema.json').read_text(encoding='utf-8')))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
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
    # UI_LAYOUT: môi trường đè ui.layout khi sinh lại (pipeline dùng để test layout thứ hai)
    env_layout = os.environ.get('UI_LAYOUT')
    if env_layout:
        if env_layout not in model.UI_LAYOUTS:
            sys.exit(f"UI_LAYOUT không hợp lệ: {env_layout} (chỉ {sorted(model.UI_LAYOUTS)})")
        ir['project']['ui']['layout'] = env_layout
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
