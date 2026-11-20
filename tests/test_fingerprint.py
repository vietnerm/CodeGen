"""
4 tình huống PLANS (PR-16) cho dấu vân tay build + vài test đơn vị.

Mỗi tình huống copy cả repo sang thư mục tạm (bỏ .git/out/.cache — repo ~4MB nên nhanh)
rồi sửa ĐÚNG MỘT chỗ, so tập FID bị ảnh hưởng trước/sau. Vì sao copy: fingerprint đọc cả
spec/ lẫn phần nền (targets/core/codegen), không được đụng repo thật.

Chạy:  python -m pytest tests/test_fingerprint.py -q
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codegen import fingerprint  # noqa: E402

IGNORE = shutil.ignore_patterns('.git', 'out', '.cache', '__pycache__', '.venv', 'node_modules')


def fresh_copy(tmp_path: Path) -> Path:
    work = tmp_path / 'repo'
    shutil.copytree(ROOT, work, ignore=IGNORE, symlinks=True)
    return work


def edit(work: Path, rel: str, old: str, new: str) -> None:
    p = work / rel
    text = p.read_text(encoding='utf-8')
    assert old in text, f"không tìm thấy chuỗi để sửa trong {rel}: {old!r}"
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def affected(base: dict, head: dict) -> set:
    return set(fingerprint.diff(base, head)['affected'])


# ── 4 tình huống "Xong khi" của PLANS ─────────────────────────────────────────

def test_s1_doi_0131_chi_anh_huong_0131(tmp_path):
    work = fresh_copy(tmp_path)
    base = fingerprint.fingerprints(work, work / 'spec')
    edit(work, 'spec/AT/A0/ATA0_0131.yaml', 'label: Ghi chú', 'label: Ghi chú bảo dưỡng')
    head = fingerprint.fingerprints(work, work / 'spec')
    assert affected(base, head) == {'ATA0_0131'}
    d = fingerprint.diff(base, head)
    row = next(r for r in d['rows'] if r['fid'] == 'ATA0_0131')
    assert row['status'] == 'doi' and 'entity' in row['reason']


def test_s2_doi_field_lookup_cua_0110_anh_huong_0120_0131(tmp_path):
    work = fresh_copy(tmp_path)
    base = fingerprint.fingerprints(work, work / 'spec')
    # device_name của 0110 được 0120, 0131 lookup — đổi nhãn làm đổi JOIN/hiển thị của chúng
    edit(work, 'spec/AT/A0/ATA0_0110.yaml', 'label: Tên thiết bị', 'label: Tên máy ATM')
    head = fingerprint.fingerprints(work, work / 'spec')
    assert affected(base, head) == {'ATA0_0110', 'ATA0_0120', 'ATA0_0131'}
    d = fingerprint.diff(base, head)
    # 0120/0131 đổi trực tiếp (lát lookup của chúng nhúng field cha device_name);
    # 0121 chỉ lookup vendor_name của 0120 — không được bị kéo theo
    assert all(r['status'] == 'giu' and not r['reason']
               for r in d['rows'] if r['fid'] == 'ATA0_0121')


def test_s3_doi_codemap_status_ai_anh_huong_fid_dung_no(tmp_path):
    work = fresh_copy(tmp_path)
    base = fingerprint.fingerprints(work, work / 'spec')
    # STATUS_AI dùng bởi 0110, 0120, 0131 — 0121 không dùng nên phải nằm ngoài
    edit(work, 'spec/_codemaps.yaml', '{code: A, label: Hoạt động}', '{code: A, label: Đang hoạt động}')
    head = fingerprint.fingerprints(work, work / 'spec')
    assert affected(base, head) == {'ATA0_0110', 'ATA0_0120', 'ATA0_0131'}


def test_s4_doi_targets_anh_huong_all(tmp_path):
    work = fresh_copy(tmp_path)
    base = fingerprint.fingerprints(work, work / 'spec')
    tmpl = sorted((work / 'targets' / 'html' / 'templates').glob('*.j2'))[0]
    tmpl.write_text(tmpl.read_text(encoding='utf-8') + '\n{# đụng phần nền #}\n', encoding='utf-8')
    head = fingerprint.fingerprints(work, work / 'spec')
    d = fingerprint.diff(base, head)
    assert d['all'] is True and d['affected'] == ['ALL']


# ── tính chất phải giữ ────────────────────────────────────────────────────────

def test_doi_comment_yaml_khong_doi_dau_van_tay(tmp_path):
    """Cái chốt của cả PR: sửa bình luận không đổi IR ⇒ fp giữ nguyên ⇒ bỏ qua bước nặng."""
    work = fresh_copy(tmp_path)
    base = fingerprint.fingerprints(work, work / 'spec')
    p = work / 'spec' / 'AT' / 'A0' / 'ATA0_0131.yaml'
    p.write_text(p.read_text(encoding='utf-8') + '\n# bình luận thêm, không đổi nghĩa\n',
                 encoding='utf-8')
    head = fingerprint.fingerprints(work, work / 'spec')
    d = fingerprint.diff(base, head)
    assert d['affected'] == [] and d['all'] is False


def test_lap_lai_cho_cung_dau_van_tay(tmp_path):
    work = fresh_copy(tmp_path)
    a = fingerprint.fingerprints(work, work / 'spec')
    b = fingerprint.fingerprints(work, work / 'spec')
    strip = lambda d: {k: v['fp'] for k, v in d.items() if not k.startswith('_') and k != 'G'}
    assert a['G'] == b['G'] and strip(a) == strip(b)


def test_phu_thuoc_chi_di_xuong_duoi(tmp_path):
    """Đổi con (0131) không được kéo theo cha (0110) — khớp tình huống 1 PLANS."""
    work = fresh_copy(tmp_path)
    from codegen import model
    ir, _ = model.build_ir(work / 'spec')
    assert fingerprint.dependents(ir, 'ATA0_0131') == {}      # không ai dùng 0131
    deps0110 = fingerprint.dependents(ir, 'ATA0_0110')
    assert set(deps0110) == {'ATA0_0120', 'ATA0_0131'}


def test_state_quyet_dinh_skip_build(tmp_path):
    """skip_build chỉ đúng khi: state xanh + jar còn + nguồn Java y hệt lần xanh."""
    work = fresh_copy(tmp_path)
    do, why = fingerprint.skip_build(work)
    assert not do and 'build-state' in why
    fingerprint.save_state(work)
    (work / '.cache' / 'app.jar').write_bytes(b'jar-gia-lap')
    # chưa có out/app → sha hiện tại ≠ state → vẫn phải build
    do, _ = fingerprint.skip_build(work)
    assert not do
    # mô phỏng: nguồn out/app đúng bằng lần ghi state
    (work / 'out' / 'app').mkdir(parents=True)
    st = fingerprint.load_state(work)
    st['out_app_sha'] = fingerprint.tree_sha(work / 'out' / 'app', exclude=('target',))
    st['core_java_sha'] = fingerprint.tree_sha(work / 'core' / 'java', exclude=('target',))   # khớp save_state v2
    fingerprint.state_path(work).write_text(json.dumps(st), encoding='utf-8')
    do, why = fingerprint.skip_build(work)
    assert do and 'y hệt lần xanh' in why


def test_g_bo_qua_pycache_duoc_tao_khi_chay(tmp_path):
    """G tất định giữa các job CI (lỗi thật run 44722931898).

    Trong CI, import codegen tạo codegen/__pycache__/*.pyc TRƯỚC khi g_hash glob;
    .pyc nhúng mtime file nguồn mà actions/checkout ghi mtime theo giây checkout,
    nên hai job của cùng một run có pyc khác nhau ⇒ G khác nhau ⇒ key cache mỗi job
    một loại. G phải bỏ qua pyc/pycache — chúng không phải nguồn sinh code.
    """
    work = fresh_copy(tmp_path)
    g0 = fingerprint.g_hash(work)
    py = work / 'codegen' / '__pycache__'
    py.mkdir()
    (py / 'fingerprint.cpython-312.pyc').write_bytes(b'pyc cua job postgresql')
    (py / 'model.cpython-312.pyc').write_bytes(b'pyc cua job postgresql 2')
    assert fingerprint.g_hash(work) == g0
    # job kia checkout lệch vài giây ⇒ pyc "khác" (mtime nhúng trong header khác)
    (py / 'fingerprint.cpython-312.pyc').write_bytes(b'pyc cua job mysql - khac byte')
    assert fingerprint.g_hash(work) == g0


def test_g_bo_qua_thu_muc_target_mvn(tmp_path):
    """mvn ghi core/java/target/** SAU khi ghash tính G cho key cache (run 44724125899:
    key aca2ef7e… nhưng state ghi 62b16979…/e467f8c7… mỗi job một giá trị). target chứa
    jar/class nhúng timestamp bản dựng — G phải bỏ qua, thư mục 'targets' (template) thì giữ."""
    work = fresh_copy(tmp_path)
    g0 = fingerprint.g_hash(work)
    tgt = work / 'core' / 'java' / 'target' / 'classes'
    tgt.mkdir(parents=True, exist_ok=True)   # bản copy có thể đã chứa target/ từ mvn cũ
    (tgt / 'Core.class').write_bytes(b'class job A')
    (work / 'core' / 'java' / 'target' / 'devhub-core.jar').write_bytes(b'jar timestamp A')
    assert fingerprint.g_hash(work) == g0
    # job/lần dựng khác: mvn ghi lại target với timestamp khác
    (tgt / 'Core.class').write_bytes(b'class job B - khac')
    assert fingerprint.g_hash(work) == g0
    # thư mục 'targets' (template generator) vẫn phải được soi — đổi file trong đó là G đổi
    tpl = next(p for p in (work / 'targets').rglob('*') if p.is_file())
    edit(work, tpl.relative_to(work).as_posix(), '\n', '\n<!-- doi -->\n')
    assert fingerprint.g_hash(work) != g0


def test_skip_build_khong_ke_target_mvn(tmp_path):
    """State được ghi SAU khi mvn đã tạo core/java/target (thời điểm thật của CI); run sau
    chưa mvn hoặc mvn ra timestamp khác — nếu target bị tính vào sha thì luôn mvn lại vô ích
    (lỗi thật run 44725364104: cache đã restore mà vẫn mvn)."""
    work = fresh_copy(tmp_path)
    # giả lập run A: mvn đã chạy (target có file timestamp), sinh out/app, ghi state
    tgt = work / 'core' / 'java' / 'target' / 'classes'
    tgt.mkdir(parents=True, exist_ok=True)   # bản copy có thể đã chứa target/ từ mvn cũ
    (tgt / 'Core.class').write_bytes(b'class run A')
    fingerprint.save_state(work)
    (work / '.cache' / 'app.jar').write_bytes(b'jar run A')
    (work / 'out' / 'app').mkdir(parents=True)
    st = fingerprint.load_state(work)
    st['out_app_sha'] = fingerprint.tree_sha(work / 'out' / 'app', exclude=('target',))
    fingerprint.state_path(work).write_text(json.dumps(st), encoding='utf-8')
    # run B: target mvn ra NỘI DUNG KHÁC (timestamp mới) — nguồn không đổi vẫn phải skip
    (tgt / 'Core.class').write_bytes(b'class run B - timestamp khac')
    do, why = fingerprint.skip_build(work)
    assert do, why
    # nhưng nguồn core/java thật sự đổi thì phải mvn lại
    java = next(p for p in (work / 'core' / 'java' / 'src').rglob('*') if p.is_file())
    edit(work, java.relative_to(work).as_posix(), '\n', '\n// doi that\n')
    do, _ = fingerprint.skip_build(work)
    assert not do


def test_state_v1_cu_bat_le(tmp_path):
    """Đổi FORMAT ⇒ state cũ vô hiệu (skip_build phải từ chối, không tin state sai luật)."""
    work = fresh_copy(tmp_path)
    fingerprint.save_state(work)
    (work / '.cache' / 'app.jar').write_bytes(b'jar')
    st = json.loads(fingerprint.state_path(work).read_text(encoding='utf-8'))
    st['format'] = 'build-fingerprint-v1'
    fingerprint.state_path(work).write_text(json.dumps(st), encoding='utf-8')
    do, why = fingerprint.skip_build(work)
    assert not do and 'build-state' in why
