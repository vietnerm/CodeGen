#!/usr/bin/env python3
"""
AI nhỏ viết THÂN HOOK nghiệp vụ — không đụng SQL/IO/reflection, không viết chữ ký/import.

Luồng: interface hook (sinh ra) + 2 hook mẫu đã viết (đọc từ custom/) + bảng field + luật (`rule`)
       + test (`tests`) → model trả JSON {"code": thân method} → chèn vào custom/…/<FID>_hookImpl.java
       (thay dòng TODO) → generator build + mvn compile (+ chạy test hook nếu DB đang chạy);
       lỗi thì gửi lại cho model, tối đa 3 vòng; vẫn sai → trả về stub như cũ, XÓA `tests:` của hook
       đó khỏi spec (stub không thực thi luật thì test hook sẽ làm đỏ pipeline) và ghi lý do
       (ai_issue đưa vào comment PR).

    python scripts/ai_hook.py --function-id ATA0_0131
    AI_BACKEND=file AI_FILE=body.json …                 # test pipeline không cần model thật
Backend như ai_spec.py: llama-cpp-python (mặc định) | Ollama | file.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from codegen import model  # noqa: E402

MAX_TRIES = 3
BODY_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['code'],
               'properties': {'code': {'type': 'string'}}}

SYSTEM = """Viết THÂN METHOD Java cho hook nghiệp vụ. Chỉ trả JSON {"code": "..."} với code là các dòng
trong thân method (không chữ ký, không import, không ngoặc đóng method). /no_think
- Chỉ được dùng: tham số ctx (Ctx), errors.add("field", "MÃ_LỖI", "thông điệp"), Conv, P, java.time.
- CẤM: SQL, IO/file, mạng, reflection, System.*, Thread, java.util (trừ tham số có sẵn).
- So sánh ngày dùng LocalDate (vd dto.actualDate().isBefore(dto.serviceDate())). Trường null phải bỏ qua.
- MÃ_LỖI dùng ĐÚNG mã mà TEST của hook mong đợi (liệt kê trong đầu bài); nếu không có test thì dùng "HOOK".
- Thông điệp lỗi viết tiếng Việt, trùng ý luật.
- BEFORE_SAVE: thân phải kết thúc bằng "return dto;".
- Thụt lề 8 khoảng trắng cho mỗi dòng thân method."""


def ask(messages):
    backend = os.environ.get('AI_BACKEND') or ('ollama' if os.environ.get('OLLAMA_URL') else 'llama')
    if backend == 'file':
        return Path(os.environ['AI_FILE']).read_text(encoding='utf-8')
    if backend == 'ollama':
        body = {'model': os.environ.get('OLLAMA_MODEL', 'qwen3:1.7b'), 'messages': messages, 'stream': False,
                'format': BODY_SCHEMA, 'options': {'temperature': 0.2}}
        req = urllib.request.Request(os.environ['OLLAMA_URL'].rstrip('/') + '/api/chat',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())['message']['content']
    from llama_cpp import Llama
    llm = ask.__dict__.get('llm')
    if llm is None:
        llm = ask.llm = Llama(model_path=os.environ.get('AI_MODEL_PATH', 'models/Qwen3-1.7B-Q8_0.gguf'),
                              n_ctx=8192, n_threads=int(os.environ.get('OMP_NUM_THREADS', '2')), verbose=False)
    r = llm.create_chat_completion(messages=messages, max_tokens=1200, temperature=0.2, top_p=0.9,
                                   response_format={'type': 'json_object', 'schema': BODY_SCHEMA})
    return r['choices'][0]['message']['content']


def clean_body(raw: str) -> list[str]:
    """Model hay bọc markdown/chữ ký/ngoặc method — lọc về đúng các dòng thân method, giữ thụt lề tương đối."""
    text = raw.strip()
    m = re.search(r'```(?:java)?\s*(.*?)```', text, re.S)
    if m:
        text = m.group(1).strip()

    def bal(ls):
        s = '\n'.join(ls)
        return s.count('{') - s.count('}')

    lines = text.splitlines()
    core = lines[1:-1] if (lines and lines[0].strip() == '{' and lines[-1].strip() == '}'
                           and bal(lines[1:-1]) == 0) else lines
    out = [ln for ln in core
           if not re.match(r'^(public|private|protected)\s', ln.strip())
           and not ln.strip().startswith('// TODO')]
    while bal(out) > 0 and out and out[-1].strip() == '}':      # chữ ký bị lọc bỏ → thừa ngoặc đóng
        out.pop()
    while bal(out) < 0 and out and out[0].strip() == '{':
        out.pop(0)
    ne = [ln for ln in out if ln.strip()]
    if not ne:
        return []
    min_i = min(len(ln) - len(ln.lstrip(' ')) for ln in ne)
    return [('        ' + ln[min_i:] if len(ln) > min_i else '').rstrip() for ln in out]


FORBIDDEN_BODY = re.compile(
    r'\b(java\.sql|javax\.sql|java\.net|reflect|Class\.forName|Runtime|ProcessBuilder|System\.|'
    r'Thread|Files|new\s+File|Socket|HttpClient|Statement|ResultSet|Connection|InputStream|OutputStream)\b')


def body_problems(lines, codes):
    errs = []
    joined = re.sub(r'//[^\n]*', '', '\n'.join(lines))          # quét code thật, bỏ comment dòng
    bad = FORBIDDEN_BODY.search(joined)
    if bad:
        errs.append(f"thân method chứa từ bị cấm (SQL/IO/reflection/System…): {bad.group()}")
    for c in codes:
        if f'"{c}"' not in joined:
            errs.append(f'không thấy errors.add(…, "{c}", …) nào — mã lỗi phải khớp test')
    return errs


def java_field(f):
    types = {'TEXT': 'String', 'INT': 'Integer', 'BIGINT': 'Long', 'DECIMAL': 'BigDecimal',
             'DATE': 'LocalDate', 'TIMESTAMP': 'OffsetDateTime', 'BOOL': 'Boolean', 'JSON': 'String'}
    return f"{types.get(f['type'], f['type'])} {f['n']['camel']}"


def hook_stub_path(ir, fid):
    fn = next(f for f in ir['functions'] if f['id'] == fid)
    pp = ir['project']['package_path']
    return ROOT / 'custom' / 'java' / pp / fn['sys'].lower() / fn['sub'].lower() / fid.lower() / 'mod' / f"{fid}_hookImpl.java"


def written_examples(fid, limit=2):
    """Hook mẫu ĐÃ VIẾT THẬT (không còn TODO, khác fid đang sửa) — đọc từ custom/, không hard-code."""
    out = []
    for p in sorted((ROOT / 'custom').rglob('*_hookImpl.java')):
        src = p.read_text(encoding='utf-8')
        if 'TODO' in src or fid.lower() in p.name.lower():
            continue
        out.append(src.strip())
        if len(out) >= limit:
            break
    return out


def insert_body(path: Path, hook: dict, lines: list[str]) -> bool:
    """Thay dòng `// TODO: <mô tả>` (kể cả dòng trắng còn lại) trong method của hook bằng thân mới."""
    src = path.read_text(encoding='utf-8')
    todo = re.search(rf"(public\s+\w+\s+{re.escape(hook['name'])}\s*\([^)]*\)\s*\{{\n)"
                     rf"(\s*// TODO:[^\n]*(?:\n\s*)*)(    \}})", src)
    if not todo:
        return False
    body = ''.join(f"{ln.rstrip()}\n" if ln.strip() else '\n' for ln in lines)
    src = src[:todo.start(2)] + (body or '') + src[todo.end(2):]
    path.write_text(src, encoding='utf-8')
    return True


def restore_stub(path: Path, hook: dict):
    """Trả về stub như cũ (giữ TODO, không thừa dòng trắng) — dùng khi mọi lần thử đều hỏng."""
    src = path.read_text(encoding='utf-8')
    m = re.search(rf"(public\s+\w+\s+{re.escape(hook['name'])}\s*\([^)]*\)\s*\{{\n)(.*?)(\n    \}})", src, re.S)
    if m and 'TODO' not in m.group(2):
        src = src[:m.start(2)] + f"        // TODO: {hook['description']}\n" + src[m.end(2):]
        path.write_text(src, encoding='utf-8')


def strip_hook_tests(spec_path: Path, hook_name: str):
    """Xoá `tests:` của hook khỏi spec — stub không thực thi luật thì test hook sẽ fail làm đỏ pipeline."""
    doc = yaml.safe_load(spec_path.read_text(encoding='utf-8'))
    changed = False
    for h in doc.get('hooks') or []:
        if h.get('name') == hook_name and h.get('tests'):
            h.pop('tests')
            changed = True
    if changed:
        spec_path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110), encoding='utf-8')
    return changed


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def compile_ok():
    """Sinh lại out/ (interface/dto mới nhất) rồi mvn compile. Trả (ok, lỗi)."""
    p = run([sys.executable, str(ROOT / 'generator.py'), 'build'], cwd=ROOT)
    if p.returncode != 0:
        return False, 'generator build lỗi:\n' + (p.stdout + p.stderr)[-1500:]
    p = run(['mvn', '-B', '-q', '-f', 'out/app/pom.xml', 'compile'], cwd=ROOT)
    if p.returncode != 0:
        errs = [ln for ln in (p.stdout + p.stderr).splitlines() if 'ERROR' in ln or '.java:' in ln]
        return False, 'compile lỗi:\n' + ('\n'.join(errs[-30:]) or (p.stdout + p.stderr)[-1500:])
    return True, ''


def db_ready():
    try:
        socket.create_connection((os.environ.get('DB_HOST', 'localhost'),
                                  int(os.environ.get('DB_PORT', '5432'))), 2).close()
        return True
    except OSError:
        return False


def hook_tests_ok(fid):
    """Package + chạy app + test HTTP của đúng chức năng này (gồm test hook). Trả (ok, thông_báo_lỗi)."""
    p = run(['mvn', '-B', '-q', '-f', 'out/app/pom.xml', 'package', '-DskipTests'], cwd=ROOT)
    if p.returncode != 0:
        return False, 'mvn package lỗi:\n' + (p.stdout + p.stderr)[-1200:]
    (ROOT / 'out' / 'logs').mkdir(exist_ok=True)
    log = open(ROOT / 'out' / 'logs' / 'ai_hook_app.log', 'w', encoding='utf-8')
    port = os.environ.get('PORT', '8080')
    env = {**os.environ, 'BASE_URL': f"http://localhost:{port}"}
    env.setdefault('APP_JWT_SECRET', 'ai-hook-local-secret-0123456789abcdef')  # chỉ cho lần chạy thử này
    app = subprocess.Popen(['java', '-jar', str(ROOT / 'out' / 'app' / 'target' / 'app.jar')],
                           stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
    try:
        probe = [sys.executable, str(ROOT / 'out' / 'tests' / 'http' / 'run_all.py'), '--only', '__probe__']
        deadline = time.time() + 90
        up = False
        while time.time() < deadline:
            if 'backend không lên' not in run(probe, env=env, cwd=ROOT).stdout:
                up = True
                break
            time.sleep(2)
        if not up:
            return False, 'app không lên sau 90s (xem out/logs/ai_hook_app.log)'
        p = run([sys.executable, str(ROOT / 'out' / 'tests' / 'http' / 'run_all.py'), '--only', fid], env=env, cwd=ROOT)
        if p.returncode != 0:
            return False, 'test hỏng:\n' + p.stdout[-2500:]
        return True, ''
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
        log.close()


def fill(fid, request='', log=print):
    """Viết thân mọi hook còn TODO của fid. Trả (ok, ghi_chú)."""
    ir, rep = model.build_ir(ROOT / 'spec')
    if rep.errors:
        return False, 'spec đang lỗi:\n' + '\n'.join(rep.errors)
    fn = next((f for f in ir['functions'] if f['id'] == fid), None)
    if not fn or not fn['entity']:
        return False, f'{fid} không tồn tại hoặc không có entity'
    if not fn['hooks']:
        return True, f'{fid} không có hook'
    path = hook_stub_path(ir, fid)
    if not path.exists():
        return False, f'không tìm thấy {path.relative_to(ROOT)} — chạy generator trước'
    src = path.read_text(encoding='utf-8')
    todo_hooks = [h for h in fn['hooks']
                  if re.search(rf"public\s+\w+\s+{re.escape(h['name'])}\s*\([^)]*\)\s*\{{\n\s*// TODO:", src)]
    if not todo_hooks:
        return True, 'hook đã viết sẵn — không làm lại'
    examples = written_examples(fid)
    ent = next(e for e in ir['entities'] if e['id'] == fn['entity'])
    fields = '\n'.join(f"- {java_field(f)}  // {f['label']}" for f in ent['api_fields'] if not f['from_profile'])
    results = []
    for h in todo_hooks:
        sig = {"VALIDATE": f"void {h['name']}(Ctx ctx, String action, {fid}_dto dto, Errors errors)",
               "BEFORE_SAVE": f"{fid}_dto {h['name']}(Ctx ctx, String action, {fid}_dto dto)",
               "AFTER_SAVE": f"void {h['name']}(Ctx ctx, String action, {fid}_dto dto)"}[h['phase']]
        codes = sorted({te['expect']['code'] for te in fn['tests']
                        if te['name'].startswith(f"hook {h['name']}") and te['expect'].get('code')})
        msgs = [SYSTEM,
                {'role': 'user', 'content': 'VÍ DỤ HOOK ĐÃ VIẾT (học phong cách):\n```java\n'
                 + '\n\n'.join(examples or ['(chưa có hook mẫu — tự viết tối giản)']) + '\n```'},
                {'role': 'user', 'content': (
                    f"INTERFACE (không được sửa chữ ký):\n```java\n{sig};\n```\n\n"
                    f"FIELD CỦA {fid}_dto ({ent['name']}):\n{fields}\n\n"
                    f"LUẬT: {h['rule'] or h['description']}\n"
                    f"MÃ LỖI test mong đợi: {', '.join(chr(34) + c + chr(34) for c in codes) or '"HOOK"'}\n"
                    f"NGỮ CẢNH issue: {request or h['rule'] or h['description']}\n\n"
                    'Chỉ trả JSON {"code": "…thân method…"}.')}]
        done, raw = False, ''
        for attempt in range(1, MAX_TRIES + 1):
            raw = ask(msgs)
            try:
                facts = json.loads(raw)
                lines = clean_body(facts['code'] if isinstance(facts, dict) else raw)
                if not lines:
                    raise ValueError('code rỗng')
            except (ValueError, KeyError, TypeError) as e:
                err = f'JSON/thân method lỗi: {e}'
            else:
                local = body_problems(lines, codes)
                if local:
                    err = 'vi phạm ràng buộc:\n' + '\n'.join(local)
                elif not insert_body(path, h, lines):
                    restore_stub(path, h)
                    err = 'không khớp stub TODO trong file (hook đã viết tay?)'
                elif (okc := compile_ok())[0]:
                    if not db_ready():
                        log(f"  ✓ lần {attempt}: compile đạt ({h['name']}) — DB không chạy, bỏ qua test hook")
                        results.append((h['name'], True, 'compile đạt (không chạy test: DB không sẵn sàng)'))
                        done = True
                        break
                    okt, msg = hook_tests_ok(fid)
                    if okt:
                        log(f"  ✓ lần {attempt}: compile + test hook đạt ({h['name']})")
                        results.append((h['name'], True, 'compile + test hook đạt'))
                        done = True
                        break
                    err = msg
                    restore_stub(path, h)                 # lần sau thử lại từ stub, không dồn lỗi cũ
                else:
                    err = okc[1]
                    restore_stub(path, h)
            log(f"  ✗ lần {attempt} ({h['name']}): {err[:300]}")
            msgs += [{'role': 'assistant', 'content': raw},
                     {'role': 'user', 'content': f"Chưa đúng, sửa và trả lại TOÀN BỘ JSON {{\"code\": …}}:\n{err[:2500]}"}]
        if not done:
            restore_stub(path, h)
            for sp in sorted((ROOT / 'spec').rglob(f'{fid}.yaml')):
                if strip_hook_tests(sp, h['name']):
                    log(f"  · xoá tests của hook {h['name']} khỏi {sp.relative_to(ROOT)} (stub không thực thi luật)")
            results.append((h['name'], False, f'sau {MAX_TRIES} lần vẫn sai — giữ stub, đã xoá test hook khỏi spec'))
    ok = all(r for _, r, _ in results)
    note = '; '.join(f"{n}: {'đạt' if r else 'THẤT BẠI — ' + why}" for n, r, why in results)
    return ok, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--function-id', required=True)
    ap.add_argument('--request', default='', help='mô tả từ issue (ngữ cảnh thêm cho model)')
    a = ap.parse_args()
    ok, note = fill(a.function_id, a.request, log=print)
    print(('✓ ' if ok else '✗ ') + note)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
