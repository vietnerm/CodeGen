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
SCHEMA = json.loads((ROOT / 'schema/function-spec.schema.json').read_text(encoding='utf-8'))
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
"""


def context():
    cm = yaml.safe_load((ROOT / 'spec/_codemaps.yaml').read_text(encoding='utf-8'))['codemap_groups']
    codemaps = {g: [c['code'] for c in d['codes']] for g, d in cm.items()}
    example = yaml.safe_load((ROOT / 'spec/AT/A0/ATA0_0110.yaml').read_text(encoding='utf-8'))
    example.pop('tests', None)
    return codemaps, example


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--function-id', required=True)
    ap.add_argument('--request', required=True)
    ap.add_argument('--parent', default='')
    a = ap.parse_args()
    fid = a.function_id
    module, sys_, sub = fid[:4], fid[:2], fid[2:4]
    dest = ROOT / 'spec' / sys_ / sub / f"{fid}.yaml"
    if dest.exists():
        sys.exit(f"✗ {dest.relative_to(ROOT)} đã có — AI chỉ tạo mới; sửa spec có sẵn thì người sửa")
    codemaps, example = context()
    schema_name = next((yaml.safe_load(p.read_text(encoding='utf-8')).get('schema')
                        for p in (ROOT / 'spec' / sys_ / sub).glob('*.yaml')), sys_.lower())
    user = (f"Codemap được dùng: {json.dumps(codemaps, ensure_ascii=False)}\n"
            f"Ví dụ spec hợp lệ:\n{json.dumps(example, ensure_ascii=False)}\n\n"
            f"Tạo spec cho: module={module}, schema={schema_name}, function.id={fid}"
            f"{', function.parent=' + a.parent if a.parent else ''}.\nMô tả: {a.request}")
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
            if a.parent:
                spec['function']['parent'] = a.parent
            dest.write_text(f"# Sinh bởi AI (scripts/ai_spec.py) — người duyệt trước khi merge\n"
                            + yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=110), encoding='utf-8')
            ok, out = validate()
            if ok:
                print(f"✓ lần {attempt}: {dest.relative_to(ROOT)} hợp lệ\n{out}")
                return
            err = '\n'.join(line for line in out.splitlines() if line.startswith('✗'))
        print(f"✗ lần {attempt}:\n{err}")
        messages += [{'role': 'assistant', 'content': raw},
                     {'role': 'user', 'content': f"Spec chưa hợp lệ, sửa và trả lại TOÀN BỘ JSON:\n{err}"}]
    dest.unlink(missing_ok=True)
    sys.exit(f"✗ sau {MAX_TRIES} lần vẫn không hợp lệ — cần người viết spec")


if __name__ == '__main__':
    main()
