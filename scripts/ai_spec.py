#!/usr/bin/env python3
"""
AI nhỏ viết SPEC — không viết code. Output bị ÉP theo schema/function-spec.schema.json
(grammar của llama.cpp / `format` của Ollama), rồi generator validate; lỗi thì đưa lại cho model.

    python scripts/ai_spec.py --function-id ATA0_0130 --parent ATA0_0100 \
        --request "Danh mục nhà cung cấp bảo trì: mã NCC (HOA, 3-10 ký tự), tên, số điện thoại, trạng thái"

Backend (biến môi trường):
    AI_MODEL_PATH=models/Qwen3-1.7B-Q8_0.gguf      llama-cpp-python (mặc định, chạy CPU trong CI)
    OLLAMA_URL=http://host:11434 OLLAMA_MODEL=...   Ollama (runner tự host)
    AI_BACKEND=file AI_FILE=x.json                  trả file JSON có sẵn (test pipeline không cần model)
"""
import argparse
import re
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from codegen import ai, model  # noqa: E402

BASE_SCHEMA = json.loads((ROOT / 'schema/function-spec.schema.json').read_text(encoding='utf-8'))
SCHEMA = BASE_SCHEMA            # thay bằng schema động (chỉ nhận chức năng/codemap/cột đang có) khi chạy
MAX_TRIES = 3

SYSTEM = """Trích các TRƯỜNG từ mô tả chức năng thành JSON đúng schema. /no_think
- Mỗi thông tin được nhắc tới trong mô tả là 1 field. KHÔNG bỏ sót trường nào.
- name: snake_case không dấu, ngắn (vd plan_date). label: tiếng Việt có dấu.
- type: TEXT (chữ, mã), INT (số nguyên), DECIMAL (tiền, số có lẻ), DATE (ngày).
- Trường trỏ tới dữ liệu CÓ SẴN (xem DANH SÁCH CHỨC NĂNG) → ref = mã chức năng đó (vd "thiết bị" → ATA0_0110).
- required=false khi mô tả nói "có thể trống"/"không bắt buộc".
- pattern chỉ khi mô tả nêu định dạng mã; example PHẢI khớp pattern, length, kiểu.
- Trạng thái A/I → name "status", codemap STATUS_AI, example "A".
- pk = name của trường mã/khoá chính.
- rules = các luật nghiệp vụ so sánh giữa các trường (vd ngày A không trước ngày B); name camelCase bắt đầu bằng validate.
Chỉ trả JSON."""

FEW_SHOT_REQUEST = ("Danh mục thiết bị ATM: mã thiết bị (chữ hoa/số 4-20 ký tự), tên thiết bị (tìm gần đúng), "
                    "loại thiết bị theo DEVICE_TYPE, ngày lắp đặt (có thể trống), hạn mức tiền mặt, trạng thái A/I. "
                    "Luật: ngày lắp đặt không được ở tương lai.")
FEW_SHOT_ANSWER = {
    "entity_name": "atm_device", "label": "Thiết bị ATM", "pk": "device_id",
    "fields": [
        {"name": "device_id", "label": "Mã thiết bị", "type": "TEXT", "length": 20, "required": True,
         "pattern": "^[A-Z0-9]{4,20}$", "example": "ATM0001", "search": "eq"},
        {"name": "device_name", "label": "Tên thiết bị", "type": "TEXT", "length": 200, "required": True,
         "example": "ATM Hội sở", "search": "like"},
        {"name": "device_type", "label": "Loại thiết bị", "type": "TEXT", "required": True, "codemap": "DEVICE_TYPE",
         "example": "ATM"},
        {"name": "install_date", "label": "Ngày lắp đặt", "type": "DATE", "required": False, "example": "2026-01-15"},
        {"name": "cash_limit", "label": "Hạn mức tiền mặt", "type": "DECIMAL", "required": True, "example": 500000000},
        {"name": "status", "label": "Trạng thái", "type": "TEXT", "required": True, "codemap": "STATUS_AI", "example": "A"}],
    "rules": [{"name": "validateInstallDate", "description": "Ngày lắp đặt không được ở tương lai"}]}

PROFILE_COLS = {'tenant_id', 'owner_unit', 'create_id', 'create_dt', 'update_id', 'update_dt', 'row_version'}
RE_HOOK = re.compile(r'^[a-z][A-Za-z0-9]{2,60}$')


def extract_schema(ir):
    """Schema NHỎ cho model: chỉ danh sách trường + luật; ref/codemap chỉ nhận giá trị đang có."""
    crud = sorted(f['id'] for f in ir['functions'] if f['entity'])
    groups = sorted(g['group'] for g in ir['codemaps'])
    field = {'type': 'object', 'additionalProperties': False,
             'required': ['name', 'label', 'type', 'required', 'example'],
             'properties': {'name': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{1,40}$'},
                            'label': {'type': 'string'},
                            'type': {'enum': ['TEXT', 'INT', 'DECIMAL', 'DATE']},
                            'length': {'type': 'integer', 'minimum': 1, 'maximum': 2000},
                            'required': {'type': 'boolean'},
                            'pattern': {'type': 'string'},
                            'example': {'type': ['string', 'number']},
                            'search': {'enum': ['eq', 'like']},
                            'ref': {'enum': crud},
                            'codemap': {'enum': groups}}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['entity_name', 'label', 'pk', 'fields'],
            'properties': {'entity_name': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{2,40}$'},
                           'label': {'type': 'string'}, 'pk': {'type': 'string'},
                           'fields': {'type': 'array', 'minItems': 2, 'items': field},
                           'rules': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                     'required': ['name', 'description'],
                                     'properties': {'name': {'type': 'string'}, 'description': {'type': 'string'}}}}}}


def compose(ir, facts, fid, parent, module, schema_name):
    """Ghép spec ĐẦY ĐỦ một cách tất định từ danh sách trường model trích ra."""
    fns = {f['id']: f for f in ir['functions']}
    ents = {e['id']: e for e in ir['entities']}
    cmaps = {g['group']: g for g in ir['codemaps']}
    names_in = [x['name'] for x in facts['fields']]
    pk = facts.get('pk') if facts.get('pk') in names_in else (names_in[0] if names_in else 'code')
    fields, relations, seen = [], [], set()
    for x in facts['fields']:
        n = x['name']
        if n in PROFILE_COLS or n in seen:
            continue
        seen.add(n)
        f = {'name': n, 'type': x['type'], 'label': x.get('label') or n}
        ex = x.get('example')
        ref = x.get('ref')
        pe = ents.get(fns[ref]['entity']) if ref in fns and fns[ref]['entity'] else None
        if pe and len(pe['pk_fields']) == 1:                      # tham chiếu: lấy đúng kiểu/độ dài khoá cha
            pf = pe['pk_fields'][0]
            f['type'] = pf['type']
            if pf['length']:
                f['length'] = pf['length']
            ex = pe['example'].get(pf['name'], ex)
            display = next((g['name'] for g in pe['base_api_fields'] if g['type'] == 'TEXT' and 'name' in g['name']
                            and g['name'] not in PROFILE_COLS and g['name'] != pf['name']), None)
            rel = {'cols': [n], 'parent': ref, 'on_delete': 'RESTRICT'}
            if display and display not in names_in:
                rel['lookup'] = [display]
            relations.append(rel)
            x = dict(x, search=x.get('search') or 'eq')
        elif f['type'] == 'TEXT':
            f['length'] = x.get('length') or (20 if n == pk else 500 if re.search(r'note|ghi_chu|desc|mo_ta', n) else 200)
            if x.get('pattern'):
                f['pattern'] = x['pattern']
        elif f['type'] == 'DECIMAL':
            f.update(precision=18, scale=2, min=0)
        cm = x.get('codemap')
        if n == 'status' and not cm:
            cm = 'STATUS_AI'
        if cm in cmaps:
            codes = [c['code'] for c in cmaps[cm]['codes']]
            f['codemap'] = cm
            f['length'] = max(len(c) for c in codes)
            if cm == 'STATUS_AI':
                f.update(enum=['A', 'I'], default='A')
            if str(ex) not in codes:
                ex = codes[0]
        if not x.get('required', True) and n != pk:
            f['nullable'] = True
        if f['type'] == 'DATE' and (not isinstance(ex, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', ex)):
            ex = '2026-01-15'
        elif f['type'] in ('INT', 'DECIMAL') and not isinstance(ex, (int, float)):
            try:
                ex = float(str(ex).replace(',', '')) if f['type'] == 'DECIMAL' else int(str(ex))
            except ValueError:
                ex = 1
        elif f['type'] == 'TEXT' and ex is not None:
            ex = str(ex)[: f.get('length') or 200]
        f['example'] = ex
        if x.get('search') or n == pk:
            f['search'] = x.get('search') or 'eq'
        fields.append(f)
    hooks = []
    for i, r in enumerate(facts.get('rules') or [], 1):
        name = r.get('name') if RE_HOOK.match(str(r.get('name', ''))) else f"validateRule{i}"
        hooks.append({'phase': 'VALIDATE', 'name': name, 'actions': ['CREATE', 'UPDATE'],
                      'description': r.get('description', '')})
    spec = {'module': module, 'schema': schema_name,
            'function': {'id': fid, 'name': facts.get('label') or fid, **({'parent': parent} if parent else {})},
            'entity': {'name': facts['entity_name'], 'label': facts.get('label') or facts['entity_name'], 'pk': [pk],
                       'profiles': ['tenant', 'owner_unit', 'audit', 'versioned'], 'fields': fields},
            'actions': ['SEARCH', 'GET', 'CREATE', 'UPDATE', 'DELETE']}
    if relations:
        spec['relations'] = relations
    if hooks:
        spec['hooks'] = hooks
    return spec


def ask(messages):
    backend = os.environ.get('AI_BACKEND') or ('ollama' if os.environ.get('OLLAMA_URL') else 'llama')
    if backend == 'file':
        return Path(os.environ['AI_FILE']).read_text(encoding='utf-8')
    if backend == 'ollama':
        body = {'model': os.environ.get('OLLAMA_MODEL', 'qwen3:1.7b'), 'messages': messages, 'stream': False,
                'format': SCHEMA, 'options': {'temperature': 0.2}}
        req = urllib.request.Request(os.environ['OLLAMA_URL'].rstrip('/') + '/api/chat',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())['message']['content']
    from llama_cpp import Llama
    llm = ask.__dict__.get('llm')
    if llm is None:
        llm = ask.llm = Llama(model_path=os.environ.get('AI_MODEL_PATH', 'models/Qwen3-1.7B-Q8_0.gguf'),
                              n_ctx=8192, n_threads=int(os.environ.get('OMP_NUM_THREADS', '2')), verbose=False)
    r = llm.create_chat_completion(messages=messages, max_tokens=2500, temperature=0.2, top_p=0.9,
                                   response_format={'type': 'json_object', 'schema': SCHEMA})
    return r['choices'][0]['message']['content']


def validate():
    p = subprocess.run([sys.executable, str(ROOT / 'generator.py'), 'validate'], capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def generate(fid, request, parent='', log=print):
    """Sinh spec mới cho fid. Trả (ok, đường_dẫn, ngữ_cảnh_đã_dùng)."""
    global SCHEMA
    module, sys_, sub = fid[:4], fid[:2], fid[2:4]
    dest = ROOT / 'spec' / sys_ / sub / f"{fid}.yaml"
    if dest.exists():
        log(f"✗ {dest.relative_to(ROOT)} đã có — AI chỉ tạo mới; sửa spec có sẵn thì người sửa")
        return False, dest, None
    ir, rep = model.build_ir(ROOT / 'spec')
    if rep.errors:
        log("✗ spec hiện tại đang lỗi — sửa trước:\n" + '\n'.join(rep.errors))
        return False, dest, None
    menus = {f['id']: f for f in ir['functions']}
    if parent and parent not in menus:
        log(f"✗ chức năng cha {parent} không tồn tại. Nút menu đang có: "
            + ', '.join(f"{f['id']} ({f['name']})" for f in menus.values() if f['type'] == 'MENU')
            + f". Module mới ({fid[:4]}) cần kiến trúc sư tạo spec/{sys_}/{sub}/_menu.yaml trước.")
        return False, dest, None
    if parent and parent[:4] != module:
        log(f"✗ chức năng cha {parent} thuộc module khác {module} — mã chức năng và cha phải cùng module")
        return False, dest, None
    SCHEMA = extract_schema(ir)
    ctx = ai.context(ir, request + ' ' + parent)
    schema_name = next((yaml.safe_load(p.read_text(encoding='utf-8')).get('schema')
                        for p in (ROOT / 'spec' / sys_ / sub).glob('*.yaml')), sys_.lower())
    catalog = [{'id': f['id'], 'name': f['name']} for f in ir['functions'] if f['entity']]
    cm = {g['group']: [c['code'] for c in g['codes']] for g in ir['codemaps']}
    user = (f"DANH SÁCH CHỨC NĂNG (để ref): {json.dumps(catalog, ensure_ascii=False)}\n"
            f"CODEMAP: {json.dumps(cm, ensure_ascii=False)}\n"
            f"BẢNG LIÊN QUAN: {json.dumps([{'function': e['function'], 'name': e['name'], 'pk': e['pk']} for e in ctx['entities']], ensure_ascii=False)}\n\n"
            f"MÔ TẢ: {request}")
    messages = [{'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': f"MÔ TẢ: {FEW_SHOT_REQUEST}"},
                {'role': 'assistant', 'content': json.dumps(FEW_SHOT_ANSWER, ensure_ascii=False)},
                {'role': 'user', 'content': user}]
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_TRIES + 1):
        raw = ask(messages)
        try:
            facts = json.loads(raw)
            spec = compose(ir, facts, fid, parent, module, schema_name)
        except (ValueError, KeyError, TypeError) as e:
            err = f"JSON lỗi: {e}"
        else:
            dest.write_text(f"# Sinh bởi AI (scripts/ai_spec.py: model trích trường → code ghép spec) — người duyệt\n"
                            + yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=110), encoding='utf-8')
            ok, out = validate()
            if ok:
                log(f"✓ lần {attempt}: {dest.relative_to(ROOT)} hợp lệ — {len(spec['entity']['fields'])} trường, "
                    f"{len(spec.get('relations', []))} quan hệ, {len(spec.get('hooks', []))} hook\n{out}")
                return True, dest, ctx
            err = '\n'.join(line for line in out.splitlines() if line.startswith('✗'))
        log(f"✗ lần {attempt}:\n{err}")
        messages += [{'role': 'assistant', 'content': raw},
                     {'role': 'user', 'content': f"Chưa hợp lệ, sửa và trả lại TOÀN BỘ JSON:\n{err}"}]
    dest.unlink(missing_ok=True)
    log(f"✗ sau {MAX_TRIES} lần vẫn không hợp lệ — cần người viết spec")
    return False, dest, ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--function-id', required=True)
    ap.add_argument('--request', required=True)
    ap.add_argument('--parent', default='')
    a = ap.parse_args()
    ok, _, _ = generate(a.function_id, a.request, a.parent)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
