#!/usr/bin/env python3
"""
Gộp kết quả lượt test giao diện LAYOUT THỨ HAI (out/ui2, chạy --quick với UI_LAYOUT đè layout)
vào out/ui để scripts/publish_ui.py đăng MỘT comment đủ ảnh cả 2 layout.

    python scripts/merge_ui2.py [label]     # label mặc định: layout-2

Ảnh của layout 2 chuyển thành out/ui/<label>/<FID>/NN-*.png; các bước trong result.json/report.md
được đánh dấu ({label}) để phân biệt trong comment PR.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ui, ui2 = ROOT / 'out' / 'ui', ROOT / 'out' / 'ui2'
label = sys.argv[1] if len(sys.argv) > 1 else 'layout-2'

if not (ui2 / 'result.json').exists():
    print('không có out/ui2/result.json — bỏ qua gộp')
    sys.exit(0)

dest = ui / label
if dest.exists():
    shutil.rmtree(dest)
shutil.copytree(ui2, dest)
for name in ('result.json', 'report.md'):
    (dest / name).unlink(missing_ok=True)

shots = json.loads((ui / 'result.json').read_text(encoding='utf-8'))
extra = json.loads((ui2 / 'result.json').read_text(encoding='utf-8'))
for s in extra:
    s['function'] = f"{s['function']} ({label})"
    if s.get('shot'):
        s['shot'] = f"{label}/{s['shot']}"
shots += extra
(ui / 'result.json').write_text(json.dumps(shots, ensure_ascii=False, indent=2), encoding='utf-8')

rep2 = (ui2 / 'report.md').read_text(encoding='utf-8')
rep = (ui / 'report.md').read_text(encoding='utf-8') if (ui / 'report.md').exists() else ''
(ui / 'report.md').write_text(rep + '\n\n---\n\n' + rep2, encoding='utf-8')
print(f"✓ đã gộp {len(extra)} bước của {label} vào out/ui/")
