#!/usr/bin/env python3
"""
AI nhỏ sửa spec cho issue loại CHANGE/BUG — trích "patch nhỏ" theo schema JSON HẸP rồi áp vào YAML
(giữ comment bằng ruamel.yaml), generator validate; lỗi thì đưa lại cho model, tối đa 3 vòng.

Chỉ cho phép: thêm field · sửa field (length/required/pattern/search/label/example/enum/codemap…) ·
xoá field · thêm lookup vào quan hệ có sẵn.  CẤM: đổi pk, xoá entity, sửa _core.yaml — schema
không có op nào cho chúng, code áp patch cũng chặn lại một lớp nữa (remove_field chạm pk → từ chối).

    python scripts/ai_change.py --function-id ATA0_0131 --request "note cho phép 800 ký tự"
    AI_BACKEND=file AI_FILE=patch.json …           # test pipeline không cần model
Backend như ai_spec.py: llama-cpp-python (mặc định) | Ollama | file.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml  # noqa: F401  (fallback nếu ruamel chưa cài)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from codegen import ai, model  # noqa: E402

MAX_TRIES = 3
PROFILE_COLS = {'tenant_id', 'owner_unit', 'create_id', 'create_dt', 'update_id', 'update_dt', 'row_version'}
OPS = ('add_field', 'edit_field', 'remove_field', 'add_lookup')


def change_schema(ir):
    """Schema HẸP: chỉ các op nhỏ; codemap/parent chỉ nhận giá trị ĐANG CÓ (ép model không bịa)."""
    crud = sorted(f['id'] for f in ir['functions'] if f['entity'])
    groups = sorted(g['group'] for g in ir['codemaps'])
    return {'type': 'object', 'additionalProperties': False, 'required': ['changes'],
            'properties': {'changes': {'type': 'array', 'minItems': 1, 'items': {
                'type': 'object', 'additionalProperties': False, 'required': ['op'],
                'properties': {
                    'op': {'enum': list(OPS)},
                    'name': {'type': 'string'},
                    'label': {'type': 'string'},
                    'type': {'enum': ['TEXT', 'INT', 'BIGINT', 'DECIMAL', 'DATE', 'TIMESTAMP', 'BOOL']},
                    'length': {'type': 'integer', 'minimum': 1, 'maximum': 2000},
                    'required': {'type': 'boolean'},
                    'nullable': {'type': 'boolean'},
                    'pattern': {'type': 'string'},
                    'example': {'type': ['string', 'number']},
                    'search': {'enum': ['eq', 'like']},
                    'codemap': {'enum': groups},
                    'parent': {'enum': crud},
                    'show': {'type': 'string'},
                    'reason': {'type': 'string'}}}}}}


def ask(messages, ir):
    import ai_spec
    ai_spec.SCHEMA = change_schema(ir)                      # dùng chung backend switching của ai_spec
    return ai_spec.ask(messages)


SYSTEM = """Đọc yêu cầu sửa/lỗi và trích thành PATCH NHỎ lên spec theo schema. /no_think
- op: add_field | edit_field | remove_field | add_lookup. KHÔNG đổi pk, KHÔNG xoá entity.
- edit_field: 'name' là field hiện có; các thuộc tính chỉ gửi THỦ TỤC THAY ĐỔI (length, pattern,
  search, required, nullable, label, example, enum là không hỗ trợ — dùng codemap nếu nhiều giá trị).
- add_field: name snake_case không dấu, label tiếng Việt; field bắt buộc PHẢI có example khớp
  length/pattern; TEXT nên có length; tiền dùng DECIMAL.
- add_lookup: 'name' là cột FK CÓ SẴN của bảng, 'parent' là mã chức năng cha có quan hệ với bảng này,
  'show' là cột hiển thị của bảng cha (chỉ ĐỌC). Chỉ thêm lookup vào quan hệ ĐÃ TỒN TẠI.
- Mỗi ý trong yêu cầu = 1 change kèm 'reason' ngắn. Chỉ trả JSON."""


def _yaml():
    try:
        from ruamel.yaml import YAML
        y = YAML()
        y.preserve_quotes = True
        y.width = 110
        return y
    except ImportError:                                     # không có ruamel: fallback mất comment
        class _F:
            def load(self, s):
                return yaml.safe_load(s)

            def dump(self, d, buf):
                yaml.safe_dump(d, buf, allow_unicode=True, sort_keys=False, width=110)
        return _F()


def _fields_of(doc):
    return doc.get('entity', {}).get('fields') or []


def _rel_of(doc):
    return doc.get('relations') or []


def apply_changes(ir, fid, doc, changes, notes):
    """Áp patch TẤT ĐỊNH vào doc (ruamel giữ comment). Trả (ok, lỗi_áp). Trả về None nếu chỉ khuyết danh."""
    ents = {e['id']: e for e in ir['entities']}
    fn = next((f for f in ir['functions'] if f['id'] == fid), None)
    ent = ents.get(fn['entity']) if fn else None
    if not ent:
        return False, f'không có entity cho {fid}'
    names = {f['name']: f for f in _fields_of(doc)}     # object trong DOC ruamel — sửa mới thật sự ghi đuợc file
    pk = set(ent['pk'])
    rels = _rel_of(doc)
    for c in changes:
        op, n = c.get('op'), str(c.get('name') or '')
        if op == 'add_field':
            if n in names or n in PROFILE_COLS:
                return False, f"add_field: `{n}` đã tồn tại (hoặc là cột profile)"
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', n):
                return False, f"add_field: tên `{n}` phải snake_case"
            t = c.get('type')
            if t not in {'TEXT', 'INT', 'BIGINT', 'DECIMAL', 'DATE', 'TIMESTAMP', 'BOOL'}:
                return False, f"add_field: type không hỗ trợ {t!r}"
            f = {'name': n, 'type': t, 'label': c.get('label') or n}
            if t == 'TEXT':
                f['length'] = c.get('length') or 200
                if c.get('pattern'):
                    f['pattern'] = c['pattern']
                if c.get('search'):
                    f['search'] = c['search']
            if t == 'DECIMAL':
                f.update(precision=18, scale=2, min=0)
            cm = c.get('codemap')
            if n == 'status' and not cm:
                cm = 'STATUS_AI'
            if cm:
                f['codemap'] = cm
                if cm == 'STATUS_AI':
                    f.setdefault('enum', ['A', 'I'])
                    f.setdefault('default', 'A')
            if c.get('required') is False or c.get('nullable'):
                f['nullable'] = True
            if c.get('example') is not None:
                f['example'] = c['example']
            _fields_of(doc).append(f)
            names[n] = f
            notes.append(f"+ field `{n}` ({t}" + (f", {f.get('length')}" if f.get('length') else '') +
                         f"): {c.get('reason') or c.get('label') or ''}")
        elif op == 'edit_field':
            f = names.get(n)
            if not f:
                return False, f"edit_field: `{n}` không tồn tại"
            allowed = {'label', 'length', 'pattern', 'search', 'example', 'codemap', 'min', 'max', 'nullable'}
            for k, v in c.items():
                if k in allowed:
                    if k in ('length', 'pattern') and f.get('type') != 'TEXT':
                        return False, f"edit_field: {k} chỉ cho cột TEXT (`{n}` là {f.get('type')})"
                    f[k] = v
                if k == 'required':
                    if v is True:
                        f.pop('nullable', None)
                    elif v is False:
                        f['nullable'] = True
            notes.append(f"~ field `{n}`: " + '; '.join(f"{k}={v}" for k, v in c.items()
                                                       if k in allowed | {'required'}) +
                         f" — {c.get('reason') or ''}")
        elif op == 'remove_field':
            if n in pk:
                return False, f"remove_field: `{n}` là khoá chính — CẤM đổi pk"
            if any(n in r.get('cols', []) for r in rels):
                return False, f"remove_field: `{n}` đang được dùng trong quan hệ — cần người xử lý"
            before = len(_fields_of(doc))
            doc['entity']['fields'] = [f for f in _fields_of(doc) if f['name'] != n]
            if len(_fields_of(doc)) == before:
                return False, f"remove_field: `{n}` không tồn tại"
            names.pop(n, None)
            notes.append(f"− field `{n}`: {c.get('reason') or ''}")
        elif op == 'add_lookup':
            show = c.get('show')
            rel = next((r for r in rels if r.get('cols') == [n] and r.get('parent') == c.get('parent')), None)
            if not rel:
                return False, f"add_lookup: không có quan hệ `{n}` → {c.get('parent')} — chỉ thêm lookup vào quan hệ có sẵn"
            pfn = next((f for f in ir['functions'] if f['id'] == c.get('parent')), None)
            pcols = {x['name'] for x in ents[pfn['entity']]['base_api_fields']} if pfn else set()
            if show not in pcols:
                return False, f"add_lookup: bảng cha không có cột `{show}`"
            lk = rel.setdefault('lookup', [])
            if show not in lk:
                lk.append(show)
                notes.append(f"+ lookup `{show}` trên quan hệ `{n}` → {c.get('parent')}: {c.get('reason') or ''}")
            else:
                notes.append(f"lookup `{show}` đã có trên quan hệ `{n}` → {c.get('parent')}")
        else:
            return False, f"op không hỗ trợ: {op!r}"
    return True, ''


def _parent_entity(ir, parent):
    fn = next((f for f in ir['functions'] if f['id'] == parent), None)
    return fn['entity'] if fn else None


def apply(fid, request, log=print):
    """Trích + áp patch cho spec của fid. Trả (ok, đường_dẫn, danh_sách_thay_đổi, log)."""
    ir, rep = model.build_ir(ROOT / 'spec')
    if rep.errors:
        return False, None, [], ['spec hiện tại đang lỗi:\n' + '\n'.join(rep.errors)]
    fn = next((f for f in ir['functions'] if f['id'] == fid), None)
    if not fn or not fn['entity']:
        return False, None, [], [f'{fid} không tồn tại hoặc không có entity']
    dest = ROOT / 'spec' / fid[:2] / fid[2:4] / f"{fid}.yaml"
    ents = {e['id']: e for e in ir['entities']}
    ent = ents[fn['entity']]
    catalog = [{'id': f['id'], 'name': f['name'], 'table': f['entity']} for f in ir['functions'] if f['entity']]
    cm = {g['group']: [c['code'] for c in g['codes']] for g in ir['codemaps']}
    fields = json.dumps([{k: f.get(k) for k in ('name', 'label', 'type', 'length', 'nullable', 'pattern',
                                               'codemap', 'search', 'example') if f.get(k) is not None}
                         for f in ent['fields'] if not f['from_profile']], ensure_ascii=False)
    rels = json.dumps([{'cols': r['cols'], 'parent': r['parent_function'], 'lookup': [x['field'] for x in r['lookup']]}
                       for r in fn['refs']], ensure_ascii=False)
    user = (f"SPEC HIỆN TẠI của {fid} ({ent['name']}, pk {ent['pk']}):\nFIELDS: {fields}\nRELATIONS: {rels}\n"
            f"CHỨC NĂNG (parent cho add_lookup): {json.dumps(catalog, ensure_ascii=False)}\n"
            f"CODEMAP: {json.dumps(cm, ensure_ascii=False)}\n\nYÊU CẦU SỬA: {request}")
    messages = [{'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': 'YÊU CẦU SỬA: ghi chú cho phép tối đa 300 ký tự thay vì 500.'},
                {'role': 'assistant', 'content': json.dumps(
                    {'changes': [{'op': 'edit_field', 'name': 'note', 'length': 300,
                                  'reason': 'rút gọn ghi chú'}]}, ensure_ascii=False)},
                {'role': 'user', 'content': user}]
    original = dest.read_text(encoding='utf-8')
    logs = []
    for attempt in range(1, MAX_TRIES + 1):
        raw = ask(messages, ir)
        try:
            facts = json.loads(raw)
            changes = facts['changes'] if isinstance(facts, dict) else []
            if not changes:
                raise ValueError('changes rỗng')
        except (ValueError, KeyError, TypeError) as e:
            err = f'JSON lỗi: {e}'
        else:
            doc = _yaml().load(original)                    # luôn áp lên bản gốc → retry không dồn patch cũ
            notes = []
            ok, aerr = apply_changes(ir, fid, doc, changes, notes)
            if ok:
                with dest.open('w', encoding='utf-8') as buf:
                    _yaml().dump(doc, buf)
                vok, vout = _validate()
                if vok:
                    log(f"✓ lần {attempt}: áp {len(changes)} thay đổi — " + '; '.join(notes))
                    log(vout.splitlines()[0] if vout else '')
                    return True, dest, notes, logs
                err = 'validate sau khi áp:\n' + '\n'.join(ln for ln in vout.splitlines() if ln.startswith('✗'))
            else:
                err = aerr
        log(f"✗ lần {attempt}: {err[:400]}")
        logs.append(f"lần {attempt}: {err[:400]}")
        messages += [{'role': 'assistant', 'content': raw},
                     {'role': 'user', 'content': f"Chưa hợp lệ, sửa và trả lại TOÀN BỘ JSON:\n{err[:2000]}"}]
    dest.write_text(original, encoding='utf-8')             # trả lại spec gốc — không để nửa vời
    log(f"✗ sau {MAX_TRIES} lần vẫn không hợp lệ — trả lại spec gốc, cần người xử lý")
    logs.append(f'sau {MAX_TRIES} lần vẫn không hợp lệ — trả lại spec gốc')
    return False, dest, [], logs


def _validate():
    import subprocess
    p = subprocess.run([sys.executable, str(ROOT / 'generator.py'), 'validate'],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode == 0, p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--function-id', required=True)
    ap.add_argument('--request', required=True)
    a = ap.parse_args()
    ok, dest, changes, _ = apply(a.function_id, a.request, log=print)
    print(('✓ ' if ok else '✗ ') + (f"{len(changes)} thay đổi vào {dest}" if dest else 'không áp được'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
