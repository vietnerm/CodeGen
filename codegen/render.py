"""
Engine chạy target pack. Generator KHÔNG biết ngôn ngữ nào: mọi thứ đặc thù nằm trong
targets/<tên>/ (target.yaml + types.yaml + templates/*.j2 + build.py tuỳ chọn).

target.yaml:
  name, kind: shared | backend, ir_versions: ["1."]
  outputs:  [{template, path, scope: project|function|codemap, once: false}]
  copy:     [{from: <thư mục trong out/>, to: <thư mục trong out/>}]   (chạy sau cùng)
  editable_globs: [...]    file AI được sửa (guard kiểm tra PR)
  build / test: lệnh shell — tài liệu cho pipeline
Placeholder trong path: {package_path} {fid} {fid_l} {sys_l} {sub_l} {no} {group}
`once: true` = file sinh MỘT lần vào thư mục custom/ của repo (người/AI sửa tiếp), không ghi đè.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import jinja2
import yaml

from .model import IR_VERSION, crud_functions
from .sqlgen import lit


def _load_target(tdir: Path):
    m = yaml.safe_load((tdir / 'target.yaml').read_text(encoding='utf-8'))
    if not any(IR_VERSION.startswith(v) for v in m.get('ir_versions', [])):
        raise RuntimeError(f"target {m['name']} không hỗ trợ IR {IR_VERSION} (hỗ trợ {m.get('ir_versions')})")
    types = {}
    if (tdir / 'types.yaml').exists():
        types = yaml.safe_load((tdir / 'types.yaml').read_text(encoding='utf-8')) or {}
    plugin = None
    if (tdir / 'build.py').exists():
        spec = importlib.util.spec_from_file_location(f"target_{m['name'].replace('-', '_')}", tdir / 'build.py')
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
    return m, types, plugin


def _env(tdir: Path, types: dict):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tdir / 'templates')),
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True,
        trim_blocks=True, lstrip_blocks=True)
    tmap = types.get('fields', {})

    def ftype(f):
        return tmap[f['type']]
    env.globals.update(zip=zip)
    env.filters.update({
        'ftype': ftype, 'tojson': lambda v, indent=None: json.dumps(v, ensure_ascii=False, indent=indent),
        'lit': lit, 'pick': lambda d, *keys: {k: d.get(k) for k in keys},
        'jstr': lambda s: json.dumps('' if s is None else str(s), ensure_ascii=False),
    })
    return env


def _fmt(path: str, ir, fn=None, extra=None) -> str:
    d = {'package_path': ir['project']['package_path']}
    if fn:
        d.update({'fid': fn['id'], 'fid_l': fn['id'].lower(), 'sys_l': fn['sys'].lower(),
                  'sub_l': fn['sub'].lower(), 'no': fn['no']})
    d.update(extra or {})
    return path.format(**d)


def run(ir: dict, root: Path, out: Path, log=print) -> dict:
    ents = {e['id']: e for e in ir['entities']}
    written, created_custom, copies = [], [], []
    for tname in ir['targets']:
        tdir = root / 'targets' / tname
        if not tdir.is_dir():
            raise RuntimeError(f"không có target pack targets/{tname}/")
        m, types, plugin = _load_target(tdir)
        env = _env(tdir, types)
        fns = crud_functions(ir)
        if m.get('kind') == 'backend':
            fns = [f for f in fns if f['target'] == m['name']]
        base_ctx = {'ir': ir, 'project': ir['project'], 'types': types, 'ents': ents,
                    'crud': crud_functions(ir), 'target': m}

        files: dict[str, str] = {}
        if plugin:
            files.update(plugin.build(ir, {'root': root, 'types': types, 'ents': ents, 'target': m}))
        for o in m.get('outputs') or []:
            tpl = env.get_template(o['template'])
            scope = o.get('scope', 'project')
            items = [None] if scope in ('project', 'codemap') else fns
            for fn in items:
                ctx = dict(base_ctx)
                if fn:
                    ctx.update(fn=fn, ent=ents[fn['entity']])
                path = _fmt(o['path'], ir, fn)
                content = tpl.render(**ctx)
                if o.get('once'):
                    dest = root / path
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(content, encoding='utf-8')
                        created_custom.append(path)
                    continue
                files[path] = content
        for rel, content in files.items():
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding='utf-8')
            written.append(rel)
        for c in m.get('copy') or []:
            copies.append((tname, c))
        log(f"  · {tname:14s} {len(files):3d} file")

    for tname, c in copies:                               # copy chạy sau cùng
        src = (root / c['from'][5:]) if c['from'].startswith('repo:') else (out / c['from'])
        dst = out / c['to']
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return {'written': written, 'custom_created': created_custom}
