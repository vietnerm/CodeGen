#!/usr/bin/env python3
"""
So hai thư mục sinh ra (out/) theo NỘI DUNG file — bằng chứng "spec cũ sinh y hệt"
(PLANS mục 2-C: khi không còn sinh tách phần, byte-diff chính là bằng chứng không phá cái cũ).

    python scripts/outdiff.py out-main out-pr            # liệt kê file khác, exit 1 nếu khác
    python scripts/outdiff.py out-main out-pr --quiet    # không in chi tiết (dùng trong script)

Ký hiệu: `<` chỉ có ở thư mục A · `>` chỉ có ở thư mục B · `!` khác nội dung.
"""
import argparse
import hashlib
from pathlib import Path


def scan(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir_a', type=Path)
    ap.add_argument('dir_b', type=Path)
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    fa, fb = scan(a.dir_a), scan(a.dir_b)
    diffs = []
    for p in sorted(set(fa) | set(fb)):
        if p not in fb:
            diffs.append(f"< {p}  (chỉ có ở {a.dir_a})")
        elif p not in fa:
            diffs.append(f"> {p}  (chỉ có ở {a.dir_b})")
        elif fa[p] != fb[p]:
            diffs.append(f"! {p}  (khác nội dung)")
    if not a.quiet:
        print('\n'.join(diffs) if diffs else '✓ hai thư mục giống hệt nhau (byte-identical)')
        print(f"— {len(diffs)} file khác / {len(fa)} + {len(fb)} file")
    raise SystemExit(1 if diffs else 0)


if __name__ == '__main__':
    main()
