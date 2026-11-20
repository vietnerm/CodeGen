#!/usr/bin/env python3
"""
Issue → AI. Đọc issue (form "AI: chức năng"), tìm hiểu trong IR rồi xử lý:

  • Chức năng mới      → AI viết spec (ngữ cảnh từ IR + schema động) → workflow chạy pipeline → PR "Closes #N"
  • Sửa chức năng có sẵn / Lỗi / Hỏi
                        → KHÔNG để AI nhỏ sửa: phân tích ảnh hưởng từ IR (bảng, quan hệ, lookup,
                          master–detail, file sinh) + gợi ý chỗ sửa → comment, gắn nhãn needs-human

    python scripts/ai_issue.py --issue 12                 # trong GitHub Actions (đọc bằng gh)
    python scripts/ai_issue.py --title "..." --body-file issue.md   # chạy thử tại máy

Ghi kết quả: out/ai/comment.md (nội dung comment) + GITHUB_OUTPUT (action, ok, fid, branch).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from codegen import ai, model  # noqa: E402

RE_FID = re.compile(r'\b([A-Z]{2}[A-Z0-9]{2}_\d{4})\b')
OUT = ROOT / 'out' / 'ai'


def read_issue(args):
    if args.issue:
        raw = subprocess.run(['gh', 'issue', 'view', str(args.issue), '--json', 'number,title,body,url'],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(raw)
    body = Path(args.body_file).read_text(encoding='utf-8') if args.body_file else ''
    return {'number': 0, 'title': args.title or '', 'body': body, 'url': ''}


def sections(body: str) -> dict:
    """Issue form của GitHub sinh '### Nhãn\\n\\ngiá trị'."""
    out, cur = {}, None
    for line in (body or '').splitlines():
        m = re.match(r'^###\s+(.+?)\s*$', line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: '\n'.join(v).strip() for k, v in out.items() if '\n'.join(v).strip() not in ('', '_No response_')}


def pick(sec, *names):
    for n in names:
        for k, v in sec.items():
            if n in k:
                return v
    return ''


def next_fid(ir, parent):
    module = parent[:4]
    nos = [int(f['no']) for f in ir['functions'] if f['module'] == module]
    base = int(parent[5:]) if parent else 0
    cand = max([n for n in nos if n // 100 == base // 100] + [base]) + 10
    while f"{module}_{cand:04d}" in {f['id'] for f in ir['functions']}:
        cand += 10
    return f"{module}_{cand:04d}"


def md_context(ctx):
    if not ctx or not ctx['entities']:
        return '_Không tìm thấy bảng có sẵn liên quan._'
    rows = ['| Chức năng | Bảng | Khoá | Cột | Quan hệ |', '|---|---|---|---|---|']
    for e in ctx['entities']:
        rel = '; '.join(f"{','.join(r['cols'])}→{r['parent']}" + (f" (chi tiết `{r['composition']}`)" if r.get('composition') else '')
                        for r in e['relations']) or '-'
        cols = ', '.join(f"`{f['name']}`" for f in e['fields'][:8]) + (' …' if len(e['fields']) > 8 else '')
        rows.append(f"| {e['function'] or '-'} {e['name']} | `{e['table']}` | {', '.join(e['pk'])} | {cols} | {rel} |")
    return '\n'.join(rows)


def md_impact(imp):
    L = [f"**{imp['function']} — {imp['name']}** (`{imp['entity'] or 'menu'}`)", '']
    if imp['uses']:
        L.append('Dùng tới: ' + '; '.join(f"`{u['table']}` qua {','.join(u['cols'])}"
                                          + (f" (lookup {', '.join(u['lookup'])})" if u['lookup'] else '') for u in imp['uses']))
    if imp['used_by']:
        L.append('Được dùng bởi: ' + '; '.join(
            f"{u['function'] or u['table']} ({','.join(u['cols'])}, xoá: {u['on_delete']}"
            + (f", chi tiết `{u['composition']}`" if u['composition'] else '') + ')' for u in imp['used_by']))
    if imp['lookups_of_my_fields']:
        L.append('Cột đang được hiển thị ở nơi khác: ' + ', '.join(f"`{x}`" for x in imp['lookups_of_my_fields']))
    if imp['codemaps']:
        L.append('CODEMAP: ' + ', '.join(f"`{c}`" for c in imp['codemaps']))
    L += ['', 'File liên quan: ' + ', '.join(f"`{f}`" for f in imp['files'])]
    return '\n'.join(L)


def output(**kw):
    gh = os.environ.get('GITHUB_OUTPUT')
    for k, v in kw.items():
        print(f"::{k}={v}")
        if gh:
            with open(gh, 'a', encoding='utf-8') as f:
                f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--issue', type=int)
    ap.add_argument('--title')
    ap.add_argument('--body-file')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    issue = read_issue(a)
    sec = sections(issue['body'])
    text = pick(sec, 'mô tả', 'mo ta', 'description') or issue['body'] or ''
    kind = pick(sec, 'loại', 'loai', 'type').lower()
    fid = pick(sec, 'mã chức năng', 'ma chuc nang', 'function')
    parent = pick(sec, 'chức năng cha', 'chuc nang cha', 'parent')
    m = RE_FID.search(fid or '') or RE_FID.search(issue['title'])
    fid = m.group(1) if m else ''
    m = RE_FID.search(parent or '')
    parent = m.group(1) if m else ''

    ir, rep = model.build_ir(ROOT / 'spec')
    if rep.errors:
        (OUT / 'comment.md').write_text("🤖 Spec trên nhánh chính đang lỗi, chưa xử lý được:\n```\n"
                                        + '\n'.join(rep.errors) + "\n```", encoding='utf-8')
        output(action='reject', ok='false', fid='', branch='')
        return
    existing = {f['id'] for f in ir['functions']}
    is_new = ('mới' in kind or 'moi' in kind or 'new' in kind) or (fid and fid not in existing and 'sửa' not in kind
                                                                    and 'lỗi' not in kind)
    ctx = ai.context(ir, f"{issue['title']} {text} {fid} {parent}")

    if is_new:
        if parent and parent not in existing:
            body = f"🤖 Chức năng cha `{parent}` không tồn tại. Các nút menu có sẵn: " + \
                   ', '.join(f"`{f['id']}`" for f in ir['functions'] if f['type'] == 'MENU')
            (OUT / 'comment.md').write_text(body, encoding='utf-8')
            output(action='reject', ok='false', fid=fid, branch='')
            return
        chosen = ''
        if not fid:
            fid = next_fid(ir, parent or next(f['id'] for f in ir['functions'] if f['type'] == 'MENU'))
            chosen = f" (tự chọn mã còn trống `{fid}` — ghi mã vào issue nếu muốn khác)"
        if fid in existing:
            (OUT / 'comment.md').write_text(f"🤖 `{fid}` đã tồn tại — chọn mã khác hoặc đổi loại yêu cầu thành *Sửa chức năng có sẵn*.",
                                            encoding='utf-8')
            output(action='reject', ok='false', fid=fid, branch='')
            return
        import ai_spec
        logs = []
        ok, dest, used = ai_spec.generate(fid, text or issue['title'], parent, log=logs.append)
        body = [f"🤖 **Chức năng mới `{fid}`**{chosen}", '', '### Ngữ cảnh AI đã dùng (tìm trong IR)', md_context(used or ctx), '']
        trace = [x for x in logs if x.startswith('model trích')]
        if trace:
            lines, n = [], 0
            for t in trace:
                if t.startswith('model trích — điều chỉnh: '):
                    lines.append(f"  - ↳ {t.removeprefix('model trích — điều chỉnh: ')}")
                else:
                    n += 1
                    lines.append(f"- lần {n}: {t.removeprefix('model trích ')}")
            body += ['<details><summary>Model đã trích</summary>', '', *lines, '', '</details>', '']
        if ok:
            new_ir, _ = model.build_ir(ROOT / 'spec')
            imp = ai.impact(new_ir, fid)
            body += ['### Spec đã sinh', f"`{dest.relative_to(ROOT)}`", '', md_impact(imp), '',
                     '_Pipeline đầy đủ (sinh code, guard, build, chạy app, test HTTP) đang chạy — đạt thì PR sẽ được mở và liên kết ở đây._']
        else:
            body += ['### Không sinh được spec hợp lệ', '```', '\n'.join(logs)[-3000:], '```',
                     'Bổ sung mô tả (trường, kiểu, ràng buộc, chức năng liên quan) rồi comment `/ai` để chạy lại.']
        (OUT / 'comment.md').write_text('\n'.join(body), encoding='utf-8')
        output(action='spec', ok='true' if ok else 'false', fid=fid,
               branch=f"ai/issue-{issue['number']}-{fid}")
        return

    # Sửa / lỗi / hỏi: phân tích từ IR, người (hoặc agent lớn) xử lý
    body = ['🤖 **Phân tích tự động** — yêu cầu sửa/lỗi không giao cho AI nhỏ; đây là bản đồ ảnh hưởng để người/agent lớn xử lý.', '']
    targets = [x for x in RE_FID.findall(f"{issue['title']} {text} {fid}") if x in existing] or \
              [e['function'] for e in ctx['entities'][:2] if e['function']]
    for t in dict.fromkeys(targets):
        body += [md_impact(ai.impact(ir, t)), '']
    body += ['### Bảng liên quan theo mô tả', md_context(ctx), '',
             'Gợi ý: sửa `spec/…/<FID>.yaml` (trường, ràng buộc, quan hệ) hoặc hook `custom/…/<FID>_hookImpl.java`; '
             'pipeline sẽ sinh lại code, tài liệu, test cho mọi chức năng bị ảnh hưởng.']
    (OUT / 'comment.md').write_text('\n'.join(body), encoding='utf-8')
    output(action='analysis', ok='true', fid=fid, branch='')


if __name__ == '__main__':
    main()
