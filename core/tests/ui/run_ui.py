#!/usr/bin/env python3
"""
Test GIAO DIỆN (Playwright, Chromium headless) có chụp màn hình — chạy sau khi app đã lên.
Selector lấy tất định từ metadata (name = tên cột, data-action/data-key/data-form do core/page.js gắn),
không đoán theo chữ hiển thị.

    BASE_URL=http://localhost:8080 python tests/ui/run_ui.py [--only ATA0_0110] [--headed]

Ảnh: out/ui/<FID>/NN-buoc.png · báo cáo: out/ui/report.md, out/ui/result.json. Exit 1 nếu có bước hỏng.
Cần: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('run_all', HERE.parent / 'http' / 'run_all.py')
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)                      # dùng chung fixtures + helper HTTP của bộ test API

OUT = Path.cwd() / 'out' / 'ui'
TIMEOUT = 15_000


class Run:
    def __init__(self):
        self.steps, self.fail = [], 0

    def step(self, fid, name, ok, shot=None, info=''):
        self.steps.append({'function': fid, 'step': name, 'ok': ok, 'shot': shot, 'info': str(info)[:300]})
        print(f"    {'✓' if ok else '✗'} {name}" + ('' if ok else f" — {info}"))
        if not ok:
            self.fail += 1
        return ok


def shoot(page, fid, n, name):
    d = OUT / fid
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{n:02d}-{name}.png"
    page.screenshot(path=str(p), full_page=True)
    return str(p.relative_to(OUT))


def fill(scope, name, value):
    loc = scope.locator(f'[name="{name}"]').first
    if loc.evaluate('e => e.tagName') == 'SELECT':
        loc.select_option(str(value))
    else:
        loc.fill('' if value is None else str(value))


def test_function(browser, run, fid):
    fx = api.FX['functions'][fid]
    maker = api.pick(fid, 'RWD')
    if not maker:
        run.step(fid, 'có user test quyền RWD', False, info='thêm vào _testdata.yaml')
        return
    print(f"• {fid} {fx['name']}")
    tk = api.token(maker)
    ex = dict(fx['example'])
    if fx['owner_unit']:
        ex.setdefault('owner_unit', maker['units'][0])
    key = '/'.join(str(ex[c]) for c in fx['pk'])
    path = api.keypath(fx, ex)
    api.ensure_parents(fx, ex, maker)
    cur = api.http('GET', path, token=tk)
    if cur.status == 200:
        api.http('DELETE', path, token=tk, query={'row_version': cur.body.get('row_version')})

    ctx = browser.new_context(viewport={'width': 1366, 'height': 900}, locale='vi-VN')
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT)
    page.on('dialog', lambda d: d.accept())
    console_errors = []
    page.on('pageerror', lambda e: console_errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and not m.text.startswith('Failed to load resource')
            and console_errors.append(m.text))                 # lỗi tải tài nguyên: xét riêng ở 'response'
    page.on('response', lambda r: r.status >= 400 and r.url.startswith(api.BASE) and '/api/' not in r.url
            and console_errors.append(f"{r.status} {r.url}"))  # file tĩnh của app hỏng (js/html…)
    n = 0

    def ok_shot(name, label):
        nonlocal n
        n += 1
        return run.step(fid, label, True, shoot(page, fid, n, name))

    def fail_shot(label, err):
        nonlocal n
        n += 1
        try:
            s = shoot(page, fid, n, 'loi')
        except Exception:
            s = None
        return run.step(fid, label, False, s, err)

    row = page.locator(f'tr[data-key="{key}"]')
    try:
        page.goto(f"{api.BASE}/pages/{fid}.html")
        lf = page.locator('form[data-form="login"]')
        lf.locator('[name="u"]').fill(maker['user_id'])
        lf.locator('[name="p"]').fill(maker['password'])
        lf.locator('[data-action="login"]').click()
        page.locator(f'[data-page="{fid}"]').wait_for()
        page.locator('[data-total]').wait_for()
        ok_shot('danh-sach', 'đăng nhập, mở trang danh sách')

        page.locator('[data-action="create"]').click()
        form = page.locator('form[data-form="create"]')
        form.wait_for()
        for k, v in ex.items():
            fill(form, k, v)
        for dt in fx['details']:
            form.locator(f'[data-action="add-line-{dt["as"]}"]').click()
            line = form.locator(f'tr[data-detail="{dt["as"]}"]').last
            for k, v in dt['line1'].items():
                fill(line, k, v)
        ok_shot('form-tao', 'điền form tạo mới' + (' + dòng chi tiết' if fx['details'] else ''))
        form.locator('[data-action="save"]').click()
        row.wait_for()
        ok_shot('da-tao', 'tạo xong, dòng mới hiện trong danh sách')
        got = api.http('GET', path, token=tk)
        run.step(fid, 'dữ liệu lưu đúng (kiểm qua API)',
                 got.status == 200 and all(api.same(got.body.get(k), v) for k, v in ex.items()),
                 info={k: (got.body.get(k), v) for k, v in ex.items() if got.body and not api.same(got.body.get(k), v)})
        for dt in fx['details']:
            run.step(fid, f"lưu kèm 1 dòng {dt['as']}", len((got.body or {}).get(dt['as']) or []) == 1,
                     info=(got.body or {}).get(dt['as']))

        page.locator('[data-action="create"]').click()
        form = page.locator('form[data-form="create"]')
        form.wait_for()
        for k, v in ex.items():
            fill(form, k, v)
        form.locator('[data-action="save"]').click()
        page.locator('[data-error="E_DUPLICATE"]').wait_for()
        ok_shot('loi-trung-khoa', 'tạo trùng khoá → hiện lỗi E_DUPLICATE')
        form.locator('[data-action="close"]').click()

        uf = fx['update_field']
        if uf and 'UPDATE' in fx['actions']:
            new = str(ex.get(uf) or 'x')[:40] + ' (sửa UI)'
            row.locator('[data-action="edit"]').click()
            form = page.locator('form[data-form="edit"]')
            form.wait_for()
            fill(form, uf, new)
            ok_shot('form-sua', f"sửa {uf}")
            form.locator('[data-action="save"]').click()
            form.wait_for(state='hidden')
            row.filter(has_text=new[:20]).wait_for()
            ok_shot('da-sua', 'sửa xong, danh sách cập nhật')
            got = api.http('GET', path, token=tk)
            run.step(fid, 'giá trị sửa đã lưu (kiểm qua API)', got.status == 200 and got.body.get(uf) == new,
                     info=(got.body or {}).get(uf))

        row.locator('[data-action="delete"]').click()
        row.wait_for(state='detached')
        ok_shot('da-xoa', 'xoá xong, dòng biến mất')
        run.step(fid, 'đã xoá (kiểm qua API)', api.http('GET', path, token=tk).status == 404)
    except (PwTimeout, AssertionError) as e:
        fail_shot('bước giao diện bị kẹt', str(e).splitlines()[0] + (f" | trang báo: {'; '.join(console_errors)[:200]}"
                                                                     if console_errors else ''))
    run.step(fid, 'không có lỗi JavaScript trên trang', not console_errors, info='; '.join(console_errors))
    ctx.close()


def report(run, seconds):
    by_fn = {}
    for s in run.steps:
        by_fn.setdefault(s['function'], []).append(s)
    L = [f"## Test giao diện — {sum(s['ok'] for s in run.steps)} đạt · {run.fail} hỏng · {seconds:.0f}s", '']
    for fid, steps in by_fn.items():
        bad = sum(not s['ok'] for s in steps)
        L += [f"### {'✅' if not bad else '❌'} {fid} — {api.FX['functions'][fid]['name']}", '',
              '| Bước | Kết quả | Ảnh |', '|---|---|---|']
        L += [f"| {s['step']} | {'✓' if s['ok'] else '✗ ' + s['info']} | {('`' + s['shot'] + '`') if s['shot'] else ''} |"
              for s in steps]
        L.append('')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.md').write_text('\n'.join(L), encoding='utf-8')
    (OUT / 'result.json').write_text(json.dumps(run.steps, ensure_ascii=False, indent=2), encoding='utf-8')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only')
    ap.add_argument('--headed', action='store_true')
    a = ap.parse_args()
    if not api.wait_ready():
        print('✗ backend không lên')
        sys.exit(2)
    run, t0 = Run(), time.time()
    order = sorted(api.FX['functions'], key=lambda f: (len(api.FX['functions'][f]['refs']), f))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        for fid in order:
            if a.only and fid != a.only:
                continue
            test_function(browser, run, fid)
        browser.close()
    print('\n' + report(run, time.time() - t0).split('\n')[0])
    sys.exit(1 if run.fail else 0)


if __name__ == '__main__':
    main()
