#!/usr/bin/env python3
"""
Guard: chặn code viết tay/AI phá chuẩn. Đọc luật từ targets/*/target.yaml (không hard-code ngôn ngữ).

  1. Hook viết tay chỉ import được API core (forbidden_imports của target backend)
  2. Hook phải đúng tên và implements interface sinh ra của chính function đó
  3. JS sinh ra không gọi HTTP trực tiếp (forbidden_calls) — chỉ qua core.js
  4. Chế độ bot (GUARD_BASE=<git ref>): PR chỉ được sửa file trong editable_globs,
     không được sửa spec/_*.yaml, core/, targets/, codegen/, scripts/, .github/

    python scripts/guard.py                     # luôn chạy trong pipeline
    GUARD_BASE=origin/main python scripts/guard.py   # PR do AI tạo
"""
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
errors = []


def targets():
    for t in sorted((ROOT / 'targets').glob('*/target.yaml')):
        yield yaml.safe_load(t.read_text(encoding='utf-8'))


# Hook nghiệp vụ là chỗ DUY NHẤT viết tay — vùng API cho phép hẹp nhất định (T2):
# chỉ Ctx/Errors/Conv/P + java.time + @Component; CẤM SQL/IO/mạng/reflection trong cả import lẫn thân.
RE_HOOK_IMPORT_OK = re.compile(
    r'^(java\.time(\.[\w.]+)?|vn\.io\.devhub\.core\.(Ctx|Errors|Conv|P)(\.[\w.]+)?|'
    r'org\.springframework\.stereotype\.Component)$')
RE_HOOK_FORBIDDEN_BODY = re.compile(
    r'\b(java\.sql|javax\.sql|java\.net|reflect|Class\.forName|Runtime|ProcessBuilder|System\.|'
    r'Thread|Files|new\s+File|Socket|HttpClient|Statement|ResultSet|Connection|InputStream|OutputStream)\b')


def check_java_hooks(forbidden):
    for p in sorted((ROOT / 'custom').rglob('*.java')):
        rel = p.relative_to(ROOT)
        src = p.read_text(encoding='utf-8')
        m = re.match(r'([A-Z]{2}[A-Z0-9]{2}_\d{4})_hookImpl\.java$', p.name)
        if not m:
            errors.append(f"{rel}: custom/ chỉ chứa <FUNCTION>_hookImpl.java")
            continue
        if not re.search(rf'class\s+{m.group(1)}_hookImpl\s+implements\s+{m.group(1)}_hook\b', src):
            errors.append(f"{rel}: phải là 'class {m.group(1)}_hookImpl implements {m.group(1)}_hook'")
        for imp in re.findall(r'^\s*import\s+(?:static\s+)?([\w.]+)', src, re.M):
            if any(imp == f or imp.startswith(f + '.') for f in forbidden):
                errors.append(f"{rel}: import {imp} bị cấm — dùng API vn.io.devhub.core")
            if not RE_HOOK_IMPORT_OK.match(imp):
                errors.append(f"{rel}: import {imp} ngoài vùng cho phép hook — chỉ Ctx/Errors/Conv/P/java.time/Component")
        bad_body = RE_HOOK_FORBIDDEN_BODY.search(re.sub(r'//[^\n]*', '', src))   # quét code thật, bỏ comment dòng
        if bad_body:
            errors.append(f"{rel}: hook chỉ được dùng Errors/Conv/P/java.time — thấy '{bad_body.group()}' "
                          f"(cấm SQL/IO/reflection)")
        for bad in ('Class.forName', 'Runtime.getRuntime', 'ProcessBuilder', 'System.exit'):
            if bad in src:
                errors.append(f"{rel}: không được dùng {bad}")


def check_js(forbidden):
    web = ROOT / 'out' / 'web'
    for p in sorted(web.rglob('*')):
        if p.suffix not in ('.js', '.html') or p.name in ('core.js',):
            continue
        src = p.read_text(encoding='utf-8')
        for f in forbidden:
            if re.search(rf'\b{re.escape(f)}\s*\(', src) or re.search(rf'\bnew\s+{re.escape(f)}\b', src):
                errors.append(f"out/web/{p.relative_to(web)}: gọi {f} trực tiếp — dùng core.request/api module")


def check_bot_diff(base, editable):
    files = subprocess.run(['git', 'diff', '--name-only', f"{base}...HEAD"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        name = Path(f).name
        if f.startswith('spec/') and name.startswith('_'):
            errors.append(f"{f}: file cấu hình chung của kiến trúc sư — bot không được sửa")
        elif f.startswith('spec/ZZ/'):
            errors.append(f"{f}: spec core (ZZ) — bot không được sửa")
        elif not any(fnmatch.fnmatch(f, g) for g in editable):
            errors.append(f"{f}: ngoài vùng được sửa {editable}")
    print(f"  bot diff so với {base}: {len(files)} file")


def main():
    forb_imports, forb_calls, editable = [], [], []
    for t in targets():
        forb_imports += t.get('forbidden_imports') or []
        forb_calls += t.get('forbidden_calls') or []
        editable += t.get('editable_globs') or []
    check_java_hooks(forb_imports)
    check_js(forb_calls)
    if os.environ.get('GUARD_BASE'):
        check_bot_diff(os.environ['GUARD_BASE'], editable)
    for e in errors:
        print(f"✗ {e}")
    print(f"guard: {len(errors)} vi phạm")
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
