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

SYSTEM = """Bạn chuyển mô tả chức năng thành SPEC JSON đúng schema. /no_think
Luật:
- Chỉ trả JSON. Không giải thích. Không viết code.
- name/cột: snake_case không dấu. label: tiếng Việt có dấu.
- Mã/khoá chuỗi: TEXT có length; mã HOA thì thêm pattern, ví dụ ^[A-Z0-9]{3,10}$.
- Tiền: DECIMAL precision 18 scale 2, min 0. Ngày: DATE. Trạng thái: enum ["A","I"], codemap STATUS_AI, default "A".
- Chỉ dùng codemap trong danh sách được cho. Không bịa codemap.
- profiles luôn là ["tenant","owner_unit","audit","versioned"].
- Mỗi field có example hợp lệ (đúng pattern, đúng codemap). Trường tìm kiếm thì thêm search eq|like.
- actions: ["SEARCH","GET","CREATE","UPDATE","DELETE"] trừ khi mô tả nói khác.
- Luật nghiệp vụ không diễn tả được bằng ràng buộc trường → thêm hooks (phase VALIDATE, name camelCase, description).
Quan hệ với bảng CÓ SẴN (xem NGỮ CẢNH — chỉ dùng mã chức năng/cột có trong đó):
- Cột trỏ tới bảng khác → relations: {cols: [cột của bảng mới], parent: <mã chức năng cha>}; cột phải cùng kiểu/độ dài với khoá cha.
- Muốn hiện tên của bảng cha → thêm lookup: [<cột hiển thị của cha>], vd lookup: ["device_name"].
- Bảng mới là DÒNG CHI TIẾT thuộc về bản ghi cha (xoá cha thì xoá dòng) → composition: true, as: <tên mảng số nhiều>,
  pk = khoá cha + 1 cột số thứ tự kiểu INT.
- Tham chiếu thường mà cha bị xoá thì chặn → on_delete: RESTRICT.
"""


def example_spec():
    ex = yaml.safe_load((ROOT / 'spec/AT/A0/ATA0_0110.yaml').read_text(encoding='utf-8'))
    ex.pop('tests', None)
    return ex


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
    SCHEMA = ai.dynamic_schema(ir, BASE_SCHEMA)
    ctx = ai.context(ir, request + ' ' + parent)
    schema_name = next((yaml.safe_load(p.read_text(encoding='utf-8')).get('schema')
                        for p in (ROOT / 'spec' / sys_ / sub).glob('*.yaml')), sys_.lower())
    user = (f"NGỮ CẢNH (bảng/chức năng có sẵn liên quan, codemap): {json.dumps(ctx, ensure_ascii=False)}\n\n"
            f"Ví dụ spec hợp lệ:\n{json.dumps(example_spec(), ensure_ascii=False)}\n\n"
            f"Tạo spec cho: module={module}, schema={schema_name}, function.id={fid}"
            f"{', function.parent=' + parent if parent else ''}.\nMô tả: {request}")
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_TRIES + 1):
        raw = ask(messages)
        try:
            spec = json.loads(raw)
        except ValueError as e:
            err = f"JSON lỗi: {e}"
        else:
            spec.update(module=module, schema=schema_name)              # không để AI chọn sai
            spec.setdefault('function', {})['id'] = fid
            if parent:
                spec['function']['parent'] = parent
            dest.write_text(f"# Sinh bởi AI (scripts/ai_spec.py) — người duyệt trước khi merge\n"
                            + yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=110), encoding='utf-8')
            ok, out = validate()
            if ok:
                log(f"✓ lần {attempt}: {dest.relative_to(ROOT)} hợp lệ\n{out}")
                return True, dest, ctx
            err = '\n'.join(line for line in out.splitlines() if line.startswith('✗'))
        log(f"✗ lần {attempt}:\n{err}")
        messages += [{'role': 'assistant', 'content': raw},
                     {'role': 'user', 'content': f"Spec chưa hợp lệ, sửa và trả lại TOÀN BỘ JSON:\n{err}"}]
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
