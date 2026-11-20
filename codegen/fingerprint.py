"""
Dấu vân tay build — biết "cái gì đổi" trước khi chạy các bước nặng (mvn, test).

Vì sao không hash theo FILE spec? Vì đổi ATA0_0110 (thêm field, đổi `device_name`)
làm đổi cả phần lookup/JOIN của ATA0_0120, ATA0_0131 dù file của chúng không đổi
(hash theo file bỏ sót → cache stale). Vì vậy:
  - G        : dấu vân tay phần NỀN sinh code (schema, _project, _core, codegen,
               targets, core, requirements). G đổi ⇒ ảnh hưởng ALL.
  - fp(fid)  : sha256 của LÁT IR của chức năng (function + entity + quan hệ +
               cột lookup + nhóm codemap nó dùng + testdata/quyền liên quan).
               Đổi comment trong YAML không đổi IR ⇒ fp giữ nguyên ⇒ bỏ qua bước nặng.
  - phụ thuộc: FID bị ảnh hưởng = FID đổi ∪ chức năng DÙNG nó (quan hệ con,
               composition, lookup vào field của nó) — đúng 4 tình huống PLANS.

Mọi thứ băm qua json sort_keys nên hai IR nội dung y hệt cho cùng dấu vân tay.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

# Đổi FORMAT hoặc G_GLOBS ⇒ state cũ (.cache/build-state.json) vô hiệu tự động.
FORMAT = 'build-fingerprint-v1'

# Phần nền: đổi bất kỳ file nào khớp các mẫu này ⇒ ảnh hưởng tới TOÀN BỘ chức năng.
# Chú ý 1: _codemaps.yaml / _testdata.yaml CỐ Ý không nằm đây — chúng được soi theo lát
# trong fp(fid) để chỉ các chức năng dùng nhóm codemap / quyền bị đổi mới chịu ảnh hưởng.
# Chú ý 2: pathlib cần '/**/*' (chứ không phải '/**') để khớp FILE ở mọi độ sâu.
G_GLOBS = ['schema/**/*', 'spec/_project.yaml', 'spec/ZZ/A0/_core.yaml', 'codegen/**/*',
           'targets/**/*', 'core/**/*', 'requirements*.txt']

# Tên phần lát IR → nhãn tiếng Việt cho cột "lý do" của `generator.py changes`.
PART_LABELS = {
    'function': 'khai báo chức năng',
    'entity': 'entity/cột',
    'relations': 'quan hệ',
    'lookup_fields': 'cột lookup',
    'codemaps': 'codemap',
    'testdata': 'testdata/quyền',
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


# ── G: phần nền ───────────────────────────────────────────────────────────────

def g_hash(root: Path) -> str:
    """sha256 trên (đường dẫn + nội dung) của mọi file khớp G_GLOBS, sắp xếp ổn định."""
    root = Path(root)
    files: list[Path] = []
    for pat in G_GLOBS:
        files += [p for p in root.glob(pat) if p.is_file()]
    h = hashlib.sha256()
    h.update(FORMAT.encode())
    for pat in G_GLOBS:                       # đổi danh sách mẫu ⇒ G đổi
        h.update(pat.encode())
    for p in sorted(set(files), key=lambda x: x.as_posix()):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(_sha(p.read_bytes()).encode())
    return h.hexdigest()


# ── fp: lát IR của từng chức năng ─────────────────────────────────────────────

def ir_parts(ir: dict, fid: str) -> dict[str, dict] | None:
    """Lát IR của chức năng, chia phần để `changes` nói được 'lý do' đổi gì."""
    fn = next((f for f in ir['functions'] if f['id'] == fid), None)
    if fn is None:
        return None
    ents = {e['id']: e for e in ir['entities']}
    ent = ents.get(fn['entity']) if fn['entity'] else None
    parts: dict[str, dict] = {'function': dict(fn)}
    if ent:
        groups = {f['codemap'] for f in ent['fields'] if f.get('codemap')}
        parts['entity'] = {k: v for k, v in ent.items() if k not in ('api_fields', 'lookup_fields')}
        parts['relations'] = [r for r in ir['relations']
                              if r['child'] == ent['id'] or r['parent'] == ent['id']]
        parts['lookup_fields'] = ent['lookup_fields']        # nhúng sẵn field cha → đổi field cha thấy ngay
        parts['codemaps'] = [g for g in ir['codemaps'] if g['group'] in groups]
        # lát _testdata: quyền gán TRỰC TIẾP cho FID này + override codemap nhóm nó dùng
        parts['testdata'] = {
            'grants': {r['role_id']: r['grants'][fid] for r in ir['testdata'].get('roles', [])
                       if fid in r.get('grants', {})},
            'codemap_overrides': [o for o in ir['testdata'].get('codemap_overrides', [])
                                  if o.get('group') in groups],
        }
    return parts


def fingerprints(root: Path, spec_dir: Path, ir=None) -> dict:
    """{'G', '_spec_dir', <fid>: {'fp': sha, 'parts': {phần: sha}}} — dấu vân tay cả spec."""
    from codegen import model                                    # nạp muộn để test dễ vá
    root, spec_dir = Path(root), Path(spec_dir)
    if ir is None:
        ir, rep = model.build_ir(spec_dir)
        if rep.errors:
            raise SystemExit('spec có lỗi, không tính được dấu vân tay:\n' + '\n'.join(rep.errors))
    out = {'G': g_hash(root), '_spec_dir': str(spec_dir)}
    for fn in ir['functions']:
        parts = ir_parts(ir, fn['id']) or {}
        out[fn['id']] = {'fp': _sha(_dump(parts).encode()),
                         'parts': {k: _sha(_dump(v).encode()) for k, v in parts.items()}}
    return out


def _head_ir(head: dict, ir=None) -> dict:
    """IR của lần chạy hiện tại — cần khi tính chức năng phụ thuộc."""
    if ir is not None:
        return ir
    from codegen import model
    new, rep = model.build_ir(Path(head['_spec_dir']))
    if rep.errors:
        raise SystemExit('spec có lỗi:\n' + '\n'.join(rep.errors))
    return new


# ── phụ thuộc: ai DÙNG chức năng này ─────────────────────────────────────────

def dependents(ir: dict, fid: str) -> dict[str, str]:
    """{FID_phụ_thuộc: lý do} — những chức năng sinh ra thứ nhúng nội dung của `fid`.

    Chỉ đi XUỐNG dưới (con/lookup/composition), không đi lên (cha): đổi con không làm
    đổi code sinh ra của cha — khớp tình huống 1 của PLANS (đổi 0131 → chỉ 0131).
    """
    fns = {f['id']: f for f in ir['functions']}
    me = fns.get(fid)
    if not me or not me['entity']:
        return {}
    ents = {e['id']: e for e in ir['entities']}
    my_ent = ents[me['entity']]
    out: dict[str, str] = {}
    for r in ir['relations']:
        if r['parent'] == my_ent['id'] and r['child_function']:
            lk = ', '.join(x['field'] for x in r['lookup']) or ', '.join(r['cols'])
            out[r['child_function']] = f"quan hệ con {r['child']} ({lk})"
    for other in ir['entities']:
        for lf in other['lookup_fields']:
            if lf['lookup']['parent_table'] == my_ent['table'] and other['function'] \
                    and other['function'] != fid:
                out[other['function']] = (f"lookup {lf['name']} ← "
                                          f"{my_ent['table']}.{lf['lookup']['parent_field']}")
    return out


# ── so sánh hai lần chạy ──────────────────────────────────────────────────────

def _fps_of(base: dict | None) -> dict:
    """Nhận cả hai dạng đầu vào: state (save_state: fp nằm dưới 'fp') hoặc fingerprints() thô."""
    if not base:
        return {}
    inner = base.get('fp')
    if isinstance(inner, dict) and any(isinstance(v, dict) and 'fp' in v for v in inner.values()):
        return inner
    return {k: v for k, v in base.items() if not k.startswith('_') and k != 'G' and isinstance(v, dict)}


def diff(base: dict | None, head: dict, ir=None) -> dict:
    """So dấu vân tay gốc (state/ref) với hiện tại → bảng + tập bị ảnh hưởng.

    G đổi ⇒ all=True (không so từng FID: luật sinh code đã đổi, so lát IR giữa hai
    luật khác nhau vô nghĩa). `base=None` ⇒ mọi FID là 'mới'.
    """
    if base and base.get('G') != head['G']:
        return {'all': True, 'rows': [], 'affected': ['ALL'],
                'reason_all': 'phần nền sinh code đổi (schema/_project/_core/codegen/targets/core/requirements)'}
    base_fps = _fps_of(base)
    head_fids = {k for k in head if not k.startswith('_') and k != 'G'}
    rows, affected, changed = [], [], {}
    for fid in sorted(head_fids | set(base_fps)):
        old, new = base_fps.get(fid), head.get(fid)
        if new is None:
            rows.append({'fid': fid, 'status': 'xoa', 'reason': 'đã bỏ khỏi spec'})
            affected.append(fid)
        elif old is None:
            rows.append({'fid': fid, 'status': 'moi', 'reason': 'chưa có trong lần chạy gốc'})
            affected.append(fid)
        elif old['fp'] != new['fp']:
            diff_parts = {k for k in set(old['parts']) | set(new['parts'])
                          if old['parts'].get(k) != new['parts'].get(k)}
            why = 'lát IR đổi: ' + ', '.join(PART_LABELS.get(k, k) for k in sorted(diff_parts))
            rows.append({'fid': fid, 'status': 'doi', 'reason': why})
            affected.append(fid)
            changed[fid] = diff_parts
        else:
            rows.append({'fid': fid, 'status': 'giu', 'reason': ''})
    # Chức năng phụ thuộc: chỉ lan từ FID đổi phần ENTITY (cột/pk) — vì con chỉ tiêu thụ
    # field/pk của cha (nhúng trong lookup_fields của nó). Phần khác của cha (codemap,
    # lookup, hook…) không chảy vào code sinh ra của con — lan rộng sẽ báo sai (0121 bị
    # kéo theo dù nó chỉ lookup vendor_name của 0120, không đụng device_name).
    hir = _head_ir(head, ir)
    for fid, parts in changed.items():
        if 'entity' not in parts:
            continue
        for dep, why in dependents(hir, fid).items():
            if dep in changed or dep not in head_fids:
                continue                       # tự nó đã đổi / đã bị xoá
            row = next((r for r in rows if r['fid'] == dep), None)
            if row is not None:
                row['reason'] = f"phụ thuộc {fid} ({why})"
                if dep not in affected:
                    affected.append(dep)
    rows.sort(key=lambda r: r['fid'])
    affected = sorted(set(affected))
    return {'all': False, 'rows': rows, 'affected': affected, 'reason_all': ''}


# ── state sau lần chạy xanh + quyết định bỏ qua mvn ───────────────────────────

def tree_sha(root: Path, exclude: tuple[str, ...] = ()) -> str:
    """sha256 trên mọi file trong thư mục (đường dẫn tương đối + nội dung).

    exclude loại TRỌN một thành phần đường dẫn — dùng ('target',) vì target chứa jar
    có timestamp bản dựng: giữ lại thì sha luôn khác dù nguồn Java không đổi.
    """
    root = Path(root)
    if not root.exists():
        return 'khong-co'
    h = hashlib.sha256()
    files = [p for p in root.rglob('*') if p.is_file()
             and not any(part in exclude for part in p.relative_to(root).parts)]
    for p in sorted(files, key=lambda x: x.as_posix()):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(_sha(p.read_bytes()).encode())
    return h.hexdigest()


def state_path(root: Path) -> Path:
    return Path(root) / '.cache' / 'build-state.json'


def load_state(root: Path) -> dict | None:
    p = state_path(root)
    if not p.exists():
        return None
    try:
        st = json.loads(p.read_text(encoding='utf-8'))
        return st if st.get('format') == FORMAT else None      # luật băm đổi → coi như chưa có
    except (json.JSONDecodeError, OSError):
        return None


def skip_build(root: Path) -> tuple[bool, str]:
    """(bỏ_qua_mvn, lý do) — chỉ tin khi: có state xanh trước + jar còn + nguồn Java y hệt."""
    root = Path(root)
    st = load_state(root)
    if st is None:
        return False, 'chưa có .cache/build-state.json xanh trước đó (hoặc luật băm đã đổi)'
    if not (root / '.cache' / 'app.jar').exists():
        return False, 'không có jar đã dựng trong .cache/app.jar'
    if not (root / 'out' / 'app').exists():
        return False, 'out/app chưa được sinh (pipeline luôn sinh trước khi tới bước mvn)'
    cur_app = tree_sha(root / 'out' / 'app', exclude=('target',))
    cur_core = tree_sha(root / 'core' / 'java')
    if cur_app == st.get('out_app_sha') and cur_core == st.get('core_java_sha'):
        return True, 'nguồn Java sinh ra + core/java y hệt lần xanh trước — dùng lại jar, bỏ mvn'
    return False, 'out/app hoặc core/java đổi so với lần xanh trước'


def save_state(root: Path, ir=None) -> dict:
    """Ghi state của lần chạy XANH (pipeline gọi ở bước cuối): G, fp từng FID, sha nguồn Java."""
    root = Path(root)
    fp = fingerprints(root, root / 'spec', ir)
    st = {
        'format': FORMAT,
        'G': fp['G'],
        'fp': {k: v for k, v in fp.items() if not k.startswith('_') and k != 'G'},
        'out_app_sha': tree_sha(root / 'out' / 'app', exclude=('target',)),
        'core_java_sha': tree_sha(root / 'core' / 'java'),
    }
    p = state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')
    return st


def clear_cache(root: Path) -> list[str]:
    """Xoá .cache/ — trả về danh sách tên file đã xoá để CLI báo cáo."""
    root = Path(root)
    cache = root / '.cache'
    removed = [p.name for p in sorted(cache.glob('*'))] if cache.exists() else []
    if cache.exists():
        import shutil
        shutil.rmtree(cache)
    return removed


# ── so với một ref git (--base) ───────────────────────────────────────────────

def fingerprints_at_ref(root: Path, ref: str, workdir: Path | None = None) -> dict:
    """Dấu vân tay của cây git tại `ref`: `git archive` ra thư mục tạm rồi băm như thường.

    Vì sao archive cả cây thay vì chỉ spec/: G cần cả schema/targets/core... của ref đó;
    chỉ khi G trùng mới so từng FID, nên lấy đủ một lần cho đơn giản.
    """
    root = Path(root)
    import shutil
    import tempfile
    workdir = Path(workdir or tempfile.mkdtemp(prefix='fp-base-'))
    dest = workdir / 'base-tree'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    r = subprocess.run(['git', 'archive', ref], cwd=str(root), capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"git archive {ref} thất bại: {r.stderr.decode(errors='replace').strip()}")
    subprocess.run(['tar', '-x', '-C', str(dest)], input=r.stdout, check=True)
    return fingerprints(dest, dest / 'spec')
