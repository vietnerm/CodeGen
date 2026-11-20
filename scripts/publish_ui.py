#!/usr/bin/env python3
"""
Đăng ảnh test giao diện lên PR/issue: đẩy out/ui/ sang nhánh `ui-screenshots` (giữ 30 lần gần nhất)
rồi tạo/cập nhật MỘT comment có ảnh (đánh dấu <!-- ui-shots -->) — không spam mỗi lần chạy.

    python scripts/publish_ui.py --target 12 --label pr-12      # trong GitHub Actions (gh + git đã có quyền)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = 'ui-screenshots'
KEEP = 30
MARK = '<!-- ui-shots -->'


def sh(*cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True).stdout.strip()


def push_shots(label):
    repo = os.environ['GITHUB_REPOSITORY']
    prefix = f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    work = Path(tempfile.mkdtemp())
    remote = sh('git', 'remote', 'get-url', 'origin', cwd=ROOT)
    if sh('git', 'ls-remote', '--heads', 'origin', BRANCH, cwd=ROOT):
        sh('git', 'clone', '-q', '--depth', '1', '--branch', BRANCH, remote, str(work))
    else:
        sh('git', 'init', '-q', '-b', BRANCH, str(work))
        sh('git', 'remote', 'add', 'origin', remote, cwd=work)
        (work / 'README.md').write_text('Ảnh test giao diện do CI sinh ra (scripts/publish_ui.py). Tự xoá bớt, giữ 30 lần gần nhất.\n')
    # mượn credential của checkout chính (actions/checkout lưu ở extraheader)
    for k in ('http.https://github.com/.extraheader',):
        v = subprocess.run(['git', 'config', '--get', k], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if v:
            sh('git', 'config', k, v, cwd=work)
    shutil.copytree(ROOT / 'out' / 'ui', work / prefix)
    runs = sorted(p.name for p in work.iterdir() if p.is_dir() and p.name[:8].isdigit())
    for old in runs[:-KEEP]:
        shutil.rmtree(work / old)
    sh('git', '-c', 'user.name=codegen-bot', '-c', 'user.email=codegen-bot@users.noreply.github.com',
       'add', '-A', cwd=work)
    sh('git', '-c', 'user.name=codegen-bot', '-c', 'user.email=codegen-bot@users.noreply.github.com',
       'commit', '-q', '-m', f"ảnh test giao diện {prefix}", cwd=work)
    sh('git', 'push', '-q', 'origin', BRANCH, cwd=work)
    return f"https://github.com/{repo}/blob/{BRANCH}/{prefix}"


def changes_section() -> list[str]:
    """Bảng FID thay đổi (PR-16 mục 6): chạy `generator.py changes --base` với ref gốc của PR."""
    base = os.environ.get('BASE_REF', '')
    if not base:
        return []
    try:
        r = subprocess.run([sys.executable, str(ROOT / 'generator.py'), 'changes',
                            '--base', base, '--json'],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return [f'_(bỏ qua bảng changes: {r.stderr.strip()[:120]})_', '']
        d = json.loads(r.stdout)
    except Exception as e:                                   # comment ảnh không được hỏng vì bảng này
        return [f'_(bỏ qua bảng changes: {e})_', '']
    L = [f"### 🔎 FID thay đổi so với `{base}`", '']
    if d.get('all'):
        return L + [f"**ALL** — {d.get('reason_all')}", '']
    mark = {'moi': 'mới', 'doi': 'đổi', 'xoa': 'xoá', 'giu': 'giữ'}
    L += ['| FID | Trạng thái | Lý do |', '|---|---|---|']
    for r in d.get('rows') or []:
        if r['status'] == 'giu' and not r['reason']:
            continue                        # dòng 'giữ' không lý do: bỏ, giữ comment gọn
        L.append(f"| `{r['fid']}` | {mark[r['status']]} | {r['reason']} |")
    if d.get('affected'):
        L += ['', 'Bị ảnh hưởng: ' + ', '.join(f"`{f}`" for f in d['affected'])]
    return L + ['']


def timing_section() -> list[str]:
    """Thời gian từng bước pipeline (out/logs/steps.tsv do pipeline.sh ghi)."""
    tsv = ROOT / 'out' / 'logs' / 'steps.tsv'
    if not tsv.exists():
        return []
    L = ['### ⏱️ Thời gian từng bước', '', '| Bước | Giây |', '|---|---|']
    for line in tsv.read_text(encoding='utf-8').splitlines():
        name, _, sec = line.partition('\t')
        if name:
            L.append(f"| {name} | {sec} |")
    return L + ['']


def body(base):
    steps = json.loads((ROOT / 'out' / 'ui' / 'result.json').read_text(encoding='utf-8'))
    ok, bad = sum(s['ok'] for s in steps), sum(not s['ok'] for s in steps)
    run = os.environ.get('RUN_URL', '')
    L = [MARK, f"### 🖥️ Test giao diện — {'✅' if not bad else '❌'} {ok} đạt · {bad} hỏng",
         f"Chạy lúc {time.strftime('%H:%M %d/%m/%Y')} · [log]({run})" if run else '', '']
    by = {}
    for s in steps:
        by.setdefault(s['function'], []).append(s)
    for fid, ss in by.items():
        nb = sum(not s['ok'] for s in ss)
        L += [f"<details{' open' if nb else ''}><summary>{'✅' if not nb else '❌'} <b>{fid}</b> — "
              f"{len(ss) - nb}/{len(ss)} bước</summary>", '']
        for s in ss:
            line = f"- {'✓' if s['ok'] else '✗'} {s['step']}" + ('' if s['ok'] else f" — `{s['info']}`")
            L.append(line)
            if s['shot']:
                L.append(f'  <br><img src="{base}/{s["shot"]}?raw=true" width="560">')
        L += ['', '</details>', '']
    L += changes_section() + timing_section()
    return '\n'.join(L)


def upsert_comment(target, text):
    repo = os.environ['GITHUB_REPOSITORY']
    ids = sh('gh', 'api', f"repos/{repo}/issues/{target}/comments", '--paginate',
             '--jq', f'.[] | select(.body | startswith("{MARK}")) | .id').split()
    f = ROOT / 'out' / 'ui' / 'comment.md'
    f.write_text(text, encoding='utf-8')
    if ids:
        sh('gh', 'api', '-X', 'PATCH', f"repos/{repo}/issues/comments/{ids[-1]}", '-F', f"body=@{f}")
    else:
        sh('gh', 'api', f"repos/{repo}/issues/{target}/comments", '-F', f"body=@{f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', required=True, help='số PR hoặc issue')
    ap.add_argument('--label', required=True)
    a = ap.parse_args()
    if not (ROOT / 'out' / 'ui' / 'result.json').exists():
        print('không có out/ui/result.json — bỏ qua')
        return
    base = push_shots(a.label)
    upsert_comment(a.target, body(base))
    print(f"✓ đã đăng ảnh: {base}")


if __name__ == '__main__':
    main()
