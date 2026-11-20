#!/usr/bin/env python3
"""
Test GIAO DIỆN (Playwright, Chromium headless) đi qua KHUNG WEB THỐNG NHẤT (shell):
đăng nhập ở /index.html → chụp shell → mở từng chức năng bằng cách BẤM MENU (mở nhóm cha trước)
→ kiểm aria-current + breadcrumb → chạy các bước CRUD trong vùng nội dung.
Selector lấy tất định từ metadata + thuộc tính data-* do shell/core/page.js gắn, không đoán theo chữ.

    BASE_URL=http://localhost:8080 python tests/ui/run_ui.py [--only FID] [--quick] [--headed]

--quick: lượt rút gọn cho LAYOUT THỨ HAI (UI_LAYOUT do generator đọc đè khi sinh): shell + mở 1 chức năng.
UI_OUT=... đổi thư mục ảnh (mặc định out/ui; pipeline dùng out/ui2 cho lượt layout 2 rồi gộp bằng
scripts/merge_ui2.py). Ảnh: out/ui/<FID>/NN-buoc.png · báo cáo: out/ui/report.md, out/ui/result.json.
Exit 1 nếu có bước hỏng. Cần: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('run_all', HERE.parent / 'http' / 'run_all.py')
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)                      # dùng chung fixtures + helper HTTP của bộ test API

OUT = Path(os.environ.get('UI_OUT') or Path.cwd() / 'out' / 'ui')
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


def shoot(page, fid, name):
    d = OUT / fid
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    return str(p.relative_to(OUT))


def fill(scope, name, value):
    loc = scope.locator(f'[name="{name}"]').first
    if loc.evaluate('e => e.tagName') == 'SELECT':
        loc.select_option(str(value))
    else:
        loc.fill('' if value is None else str(value))


def new_page(browser):
    """Context mới + thu lỗi console/pageerror/tài nguyên tĩnh hỏng (shell import module API)."""
    ctx = browser.new_context(viewport={'width': 1366, 'height': 900}, locale='vi-VN')
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT)
    page.on('dialog', lambda d: d.accept())
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and not m.text.startswith('Failed to load resource')
            and errors.append(m.text))                 # lỗi tải tài nguyên: xét riêng ở 'response'
    page.on('response', lambda r: r.status >= 400 and r.url.startswith(api.BASE) and '/api/' not in r.url
            and errors.append(f"{r.status} {r.url}"))  # file tĩnh của app hỏng (js/html/css/font…)
    return ctx, page, errors


def login_shell(page, user):
    """Vào /index.html, đăng nhập qua form của shell; xong khi ô lọc menu (sidebar) hiện."""
    page.goto(f"{api.BASE}/index.html")
    lf = page.locator('form[data-form="login"]')
    lf.wait_for()
    lf.locator('[name="u"]').fill(user['user_id'])
    lf.locator('[name="p"]').fill(user['password'])
    lf.locator('[data-action="login"]').click()
    page.locator('[data-action="menu-filter"]').wait_for()      # sidebar đã dựng xong


def menu_ancestors(token, fid):
    """Các nút nhóm từ gốc tới fid theo cây menu THẬT của user (GET /api/v1/menu)."""
    tree = api.http('GET', '/api/v1/menu', token=token).body or []
    def walk(nodes, path):
        for n in nodes:
            if n['function_id'] == fid:
                return path
            got = walk(n.get('children') or [], path + [n['function_id']])
            if got is not None:
                return got
        return None
    return walk(tree, []) or []


def open_via_menu(page, run, fid, ancestors, prefix=''):
    """Mở chức năng bằng cách BẤM MENU (không goto URL trực tiếp) — đúng thao tác người dùng."""
    for anc in ancestors:                                       # mở các nhóm cha trước
        grp = page.locator(f'[data-menu="{anc}"]')
        if grp.get_attribute('aria-expanded') == 'false':
            grp.click()
    item = page.locator(f'a[data-menu="{fid}"]')
    item.click()
    active = page.locator(f'a[data-menu="{fid}"][aria-current="page"]')
    active.wait_for()
    crumb = page.locator('[data-breadcrumb]')
    text = (crumb.text_content() or '').strip()
    return run.step(fid, f"{prefix}bấm menu mở chức năng, breadcrumb đúng", fid in text,
                    info=text or '(breadcrumb rỗng)')


def test_function(browser, run, fid, first=False):
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

    ctx, page, console_errors = new_page(browser)
    n = 0

    def ok_shot(name, label):
        nonlocal n
        n += 1
        return run.step(fid, label, True, shoot(page, fid, f"{n:02d}-{name}"))

    def fail_shot(label, err):
        nonlocal n
        n += 1
        try:
            s = shoot(page, fid, f"{n:02d}-loi")
        except Exception:
            s = None
        return run.step(fid, label, False, s, err)

    content = page.locator('[data-content]')
    row = content.locator(f'tr[data-key="{key}"]')
    try:
        login_shell(page, maker)
        page.locator('[data-menu]').first.wait_for()
        run.step(fid, 'đăng nhập vào shell, sidebar menu dựng đúng', True, shoot(page, fid, '00-shell'))

        ancestors = menu_ancestors(tk, fid)
        open_via_menu(page, run, fid, ancestors)
        content.locator(f'[data-page="{fid}"]').wait_for()
        content.locator('[data-total]').wait_for()
        ok_shot('danh-sach', 'nạp trang danh sách qua shell (bấm menu)')

        content.locator('[data-action="create"]').click()
        form = content.locator('form[data-form="create"]')
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

        content.locator('[data-action="create"]').click()
        form = content.locator('form[data-form="create"]')
        form.wait_for()
        for k, v in ex.items():
            fill(form, k, v)
        form.locator('[data-action="save"]').click()
        content.locator('[data-error="E_DUPLICATE"]').wait_for()
        ok_shot('loi-trung-khoa', 'tạo trùng khoá → hiện lỗi E_DUPLICATE')
        form.locator('[data-action="close"]').click()

        uf = fx['update_field']
        if uf and 'UPDATE' in fx['actions']:
            new = str(ex.get(uf) or 'x')[:40] + ' (sửa UI)'
            row.locator('[data-action="edit"]').click()
            form = content.locator('form[data-form="edit"]')
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

        if first:
            # FID không có trong menu (không quyền) → E_FORBIDDEN, không import module API
            page.evaluate("location.hash = '#/KHONG_TON_TAI'")
            content.locator('[data-error="E_FORBIDDEN"]').wait_for()
            ok_shot('loi-khong-co-quyen', 'mở #/KHONG_TON_TAI → E_FORBIDDEN, không import')

        # ── viewer (chỉ R): thấy chức năng trong menu nhưng KHÔNG nút tạo/sửa/xoá ──
        viewer = api.pick(fid, 'R', tenant=maker['tenant'], lacks='W')
        if viewer:
            api.http('POST', fx['base'], token=tk, body=ex)     # tạo 1 dòng để bảng có nút để kiểm
            vctx, vpage, verr = new_page(browser)
            try:
                login_shell(vpage, viewer)
                if open_via_menu(vpage, run, fid, menu_ancestors(api.token(viewer), fid), prefix='viewer: '):
                    vcontent = vpage.locator('[data-content]')
                    vcontent.locator(f'[data-page="{fid}"]').wait_for()
                    vcontent.locator('[data-total]').wait_for()
                    n_create = vcontent.locator('[data-action="create"]').count()
                    n_edit = vcontent.locator('[data-action="edit"]').count()
                    n_delete = vcontent.locator('[data-action="delete"]').count()
                    run.step(fid, 'viewer chỉ R: không có nút tạo/sửa/xoá',
                             n_create == 0 and n_edit == 0 and n_delete == 0,
                             info=f'create={n_create} edit={n_edit} delete={n_delete}')
                    run.step(fid, 'viewer chỉ R: không có lỗi JavaScript', not verr, info='; '.join(verr))
                    run.step(fid, 'viewer chỉ R: xem được danh sách', True, shoot(vpage, fid, '90-viewer-chi-xem'))
            except (PwTimeout, AssertionError) as e:
                fail_shot('viewer bị kẹt', str(e).splitlines()[0])
            finally:
                vctx.close()
            got = api.http('GET', path, token=tk)
            if got.status == 200:
                api.http('DELETE', path, token=tk, query={'row_version': got.body.get('row_version')})
    except (PwTimeout, AssertionError) as e:
        fail_shot('bước giao diện bị kẹt', str(e).splitlines()[0] + (f" | trang báo: {'; '.join(console_errors)[:200]}"
                                                                     if console_errors else ''))
    run.step(fid, 'không có lỗi JavaScript trên trang', not console_errors, info='; '.join(console_errors))
    ctx.close()


def test_tenant_codemap(browser, run):
    """Tenant T2 thấy codemap riêng trên UI: mã thêm hiện, mã ẩn (status=I) không hiện trong ô lọc."""
    target = next(((fid, fx) for fid, fx in sorted(api.FX['functions'].items()) if fx.get('codemap_search')), None)
    if not target:
        return
    fid, fx = target
    user = api.pick(fid, 'RWD', tenant='T2')
    if not user:
        run.step(fid, 'có user tenant T2 quyền RWD', False, info='thêm vào _testdata.yaml')
        return
    print(f"• {fid} — codemap theo tenant ({user['user_id']}/T2)")
    ctx, page, console_errors = new_page(browser)
    try:
        login_shell(page, user)
        if open_via_menu(page, run, fid, menu_ancestors(api.token(user), fid), prefix='T2: '):
            content = page.locator('[data-content]')
            content.locator(f'[data-page="{fid}"]').wait_for()
            for cm in fx['codemap_search']:
                sel = content.locator(f'select[name="{cm["field"]}"]').first
                sel.wait_for()
                for o in api.FX['codemap_overrides']:
                    if o['group'] != cm['group'] or o['tenant'] != user['tenant']:
                        continue
                    opt = sel.locator(f'option[value="{o["code"]}"]')
                    if o.get('status') == 'I':
                        run.step(fid, f"tenant {user['tenant']} ẩn {o['group']}.{o['code']} trên UI",
                                 opt.count() == 0, info=f"số option = {opt.count()}")
                    else:
                        run.step(fid, f"tenant {user['tenant']} có mã riêng {o['group']}.{o['code']} trên UI",
                                 opt.count() == 1, info=f"số option = {opt.count()}")
            run.step(fid, 'codemap theo tenant: chụp màn hình', True, shoot(page, fid, '95-tenant-codemap'))
    except (PwTimeout, AssertionError) as e:
        run.step(fid, 'codemap theo tenant bị kẹt', False, info=str(e).splitlines()[0])
    run.step(fid, 'codemap theo tenant: không có lỗi JavaScript', not console_errors, info='; '.join(console_errors))
    ctx.close()


def quick_pass(browser, run, fid):
    """Lượt rút gọn cho layout thứ hai (UI_LAYOUT): chỉ shell + mở 1 chức năng qua menu."""
    maker = api.pick(fid, 'RWD')
    if not maker:
        run.step(fid, '(layout 2) có user test quyền RWD', False, info='thêm vào _testdata.yaml')
        return
    print(f"• {fid} — layout thứ hai (UI_LAYOUT)")
    tk = api.token(maker)
    ctx, page, console_errors = new_page(browser)
    try:
        login_shell(page, maker)
        page.locator('[data-menu]').first.wait_for()
        run.step(fid, '(layout 2) shell dựng đúng sau đăng nhập', True, shoot(page, fid, '00-shell'))
        open_via_menu(page, run, fid, menu_ancestors(tk, fid), prefix='(layout 2) ')
        page.locator('[data-content]').locator(f'[data-page="{fid}"]').wait_for()
        run.step(fid, '(layout 2) mở chức năng qua menu', True, shoot(page, fid, '01-mo-qua-menu'))
    except (PwTimeout, AssertionError) as e:
        run.step(fid, '(layout 2) bị kẹt', False, info=str(e).splitlines()[0])
    run.step(fid, '(layout 2) không có lỗi JavaScript', not console_errors, info='; '.join(console_errors))
    ctx.close()


def report(run, seconds):
    by_fn = {}
    for s in run.steps:
        by_fn.setdefault(s['function'], []).append(s)
    L = [f"## Test giao diện — {sum(s['ok'] for s in run.steps)} đạt · {run.fail} hỏng · {seconds:.0f}s", '']
    for fid, steps in by_fn.items():
        name = api.FX['functions'].get(fid.replace(' (layout 2)', '').split(' — ')[0], {}).get('name', '')
        bad = sum(not s['ok'] for s in steps)
        L += [f"### {'✅' if not bad else '❌'} {fid} — {name}", '',
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
    ap.add_argument('--quick', action='store_true', help='lượt rút gọn cho layout thứ hai')
    ap.add_argument('--headed', action='store_true')
    a = ap.parse_args()
    if not api.wait_ready():
        print('✗ backend không lên')
        sys.exit(2)
    run, t0 = Run(), time.time()
    order = sorted(api.FX['functions'], key=lambda f: (len(api.FX['functions'][f]['refs']), f))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        if a.quick:
            quick_pass(browser, run, order[0])
        else:
            for i, fid in enumerate(order):
                if a.only and fid != a.only:
                    continue
                test_function(browser, run, fid, first=(i == 0))
            if not a.only:
                test_tenant_codemap(browser, run)
        browser.close()
    print('\n' + report(run, time.time() - t0).split('\n')[0])
    sys.exit(1 if run.fail else 0)


if __name__ == '__main__':
    main()
