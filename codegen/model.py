"""
Nạp spec YAML → kiểm tra → IR (dict thuần, JSON được).

IR là hợp đồng giữa spec và các target: template KHÔNG đọc YAML, chỉ đọc IR.
Đổi cấu trúc IR ⇒ tăng IR_VERSION; target khai báo version nó hỗ trợ.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

IR_VERSION = "1.0"

TYPES = {'TEXT', 'INT', 'BIGINT', 'DECIMAL', 'DATE', 'TIMESTAMP', 'BOOL', 'JSON'}
ACTIONS = {  # action → (quyền, HTTP method, có pk trên path)
    'SEARCH': ('R', 'GET', False),
    'GET':    ('R', 'GET', True),
    'CREATE': ('W', 'POST', False),
    'UPDATE': ('W', 'PUT', True),
    'DELETE': ('D', 'DELETE', True),
}
PHASES = {'VALIDATE', 'BEFORE_SAVE', 'AFTER_SAVE'}
ON_DELETE = {'CASCADE', 'RESTRICT', 'NULLIFY'}
FUNC_TYPES = {'MENU', 'BOTH', 'API'}

RE_FID = re.compile(r'^([A-Z]{2})([A-Z0-9]{2})_(\d{4})$')
RE_MODULE = re.compile(r'^[A-Z]{2}[A-Z0-9]{2}$')
RE_IDENT = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
RE_CODE = re.compile(r'^[A-Z0-9][A-Z0-9_]{0,39}$')
RE_HOOK = re.compile(r'^[a-z][A-Za-z0-9]{2,60}$')

FIELD_KEYS = {'name', 'type', 'length', 'precision', 'scale', 'nullable', 'default', 'identity',
              'enum', 'pattern', 'min', 'max', 'codemap', 'label', 'example', 'search',
              'readonly', 'system', 'sensitive', 'description'}


class SpecError(Exception):
    def __init__(self, errors):
        super().__init__(f"{len(errors)} lỗi spec")
        self.errors = errors


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where, msg):
        self.errors.append(f"✗ {where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"! {where}: {msg}")


# ─────────────────────────── tên ───────────────────────────
def names(snake: str) -> dict:
    parts = snake.split('_')
    camel = parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:])
    return {'snake': snake, 'camel': camel, 'pascal': camel[:1].upper() + camel[1:],
            'kebab': snake.replace('_', '-'), 'upper': snake.upper()}


# ─────────────────────────── nạp YAML ───────────────────────────
def _check_keys(node, where, rep):
    """YAML 1.1: khoá no/yes/on/off → bool, null/~ → None. Bắt sớm."""
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                rep.err(where, f"khoá YAML {k!r} không phải chuỗi (no/yes/on/off/null bị hiểu "
                               f"thành bool/null) — đổi tên khoá hoặc đặt trong nháy")
            _check_keys(v, where, rep)
    elif isinstance(node, list):
        for x in node:
            _check_keys(x, where, rep)


def _load(path: Path, rep: Report):
    try:
        doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        rep.err(str(path), f"YAML lỗi cú pháp: {e}")
        return {}
    _check_keys(doc, str(path), rep)
    return doc


# ─────────────────────────── field ───────────────────────────
def _field(f: dict, where: str, rep: Report, codemaps: dict, from_profile=False) -> dict:
    name = f.get('name')
    w = f"{where}.{name}"
    for k in f:
        if k not in FIELD_KEYS:
            rep.err(w, f"thuộc tính field không hợp lệ: {k!r}")
    if not isinstance(name, str) or not RE_IDENT.match(name):
        rep.err(w, "tên cột phải snake_case thường ≤63 ký tự")
        name = str(name)
    t = f.get('type')
    if t not in TYPES:
        rep.err(w, f"type phải thuộc {sorted(TYPES)}: {t!r}")
    if t == 'DECIMAL' and not f.get('precision'):
        rep.err(w, "DECIMAL cần precision")
    if f.get('identity') and t not in ('INT', 'BIGINT'):
        rep.err(w, "identity chỉ cho INT/BIGINT")
    enum = f.get('enum')
    if enum is not None and (not isinstance(enum, list) or not all(isinstance(x, str) for x in enum)):
        rep.err(w, "enum phải là danh sách chuỗi (đặt 'Y'/'N' trong nháy)")
        enum = None
    cm = f.get('codemap')
    if cm is not None and cm not in codemaps:
        rep.err(w, f"codemap {cm!r} chưa khai báo trong _codemaps.yaml")
    if enum and cm and set(enum) != {c['code'] for c in codemaps.get(cm, {}).get('codes', [])}:
        rep.warn(w, f"enum {enum} khác danh sách mã của codemap {cm}")
    if f.get('pattern'):
        try:
            re.compile(f['pattern'])
        except re.error as e:
            rep.err(w, f"pattern sai: {e}")
    default = f.get('default')
    if enum and default is not None and str(default) not in enum:
        rep.err(w, f"default {default!r} không thuộc enum")
    if f.get('search') not in (None, 'eq', 'like'):
        rep.err(w, "search phải là eq | like")
    if f.get('search') == 'like' and t != 'TEXT':
        rep.err(w, "search: like chỉ cho TEXT")
    system = bool(f.get('system', False))
    nullable = bool(f.get('nullable', False))
    return {
        'name': name, 'n': names(name), 'label': f.get('label') or name, 'type': t,
        'length': f.get('length'), 'precision': f.get('precision'), 'scale': f.get('scale') or 0,
        'nullable': nullable, 'default': default, 'identity': bool(f.get('identity', False)),
        'enum': enum, 'pattern': f.get('pattern'), 'min': f.get('min'), 'max': f.get('max'),
        'codemap': cm, 'example': f.get('example'), 'search': f.get('search'),
        'system': system, 'readonly': bool(f.get('readonly', False)) or system or bool(f.get('identity')),
        'sensitive': bool(f.get('sensitive', False)), 'description': f.get('description', ''),
        'from_profile': from_profile,
        # bắt buộc nhập: không null, không default, không do hệ thống điền
        'required': not nullable and default is None and not system and not f.get('identity'),
    }


# ─────────────────────────── build IR ───────────────────────────
def build_ir(spec_dir: Path) -> tuple[dict, Report]:
    rep = Report()
    proj_doc = _load(spec_dir / '_project.yaml', rep)
    cm_doc = _load(spec_dir / '_codemaps.yaml', rep)
    td_path = spec_dir / '_testdata.yaml'
    td_doc = _load(td_path, rep) if td_path.exists() else {}

    project = proj_doc.get('project') or {}
    for k in ('name', 'group', 'package', 'version'):
        if not project.get(k):
            rep.err('_project.yaml', f"project.{k} bắt buộc")
    dialects = proj_doc.get('dialects') or ['postgresql']
    profiles = proj_doc.get('profiles') or {}

    # ── codemap ──
    codemaps = {}
    for g, d in (cm_doc.get('codemap_groups') or {}).items():
        where = f"codemap {g}"
        if not RE_CODE.match(g):
            rep.err(where, "mã nhóm phải HOA, [A-Z0-9_]")
        codes, seen = [], set()
        for i, c in enumerate(d.get('codes') or [], 1):
            code = c.get('code')
            if not isinstance(code, str) or not RE_CODE.match(code):
                rep.err(where, f"mã {code!r} không hợp lệ (chuỗi HOA; đặt trong nháy nếu là Y/N)")
                continue
            if code in seen:
                rep.err(where, f"mã {code} trùng")
            seen.add(code)
            codes.append({'code': code, 'label': c.get('label') or code, 'seq': c.get('seq', i * 10),
                          'system': bool(d.get('system') or c.get('system')),
                          'attrs': c.get('attrs'), 'parent_code': c.get('parent_code'),
                          'n': names(code.lower())})
        codemaps[g] = {'group': g, 'n': names(g.lower()), 'name': d.get('name') or g,
                       'module': d.get('module', 'ZZA0'), 'tenant_editable': bool(d.get('tenant_editable')),
                       'parent_group': d.get('parent_group'), 'attr_fields': d.get('attr_fields'),
                       'codes': codes}
    for g, d in codemaps.items():
        for af in d['attr_fields'] or []:
            _field(af, f"codemap {g}.attr", rep, codemaps)
        if d['parent_group'] and d['parent_group'] not in codemaps:
            rep.err(f"codemap {g}", f"parent_group {d['parent_group']} không tồn tại")

    # ── module files ──
    entities, relations_raw, functions = {}, [], []
    for path in sorted(spec_dir.rglob('*.yaml')):
        if path.parent == spec_dir:
            continue                                     # _project, _codemaps, _testdata
        doc = _load(path, rep)
        where = str(path.relative_to(spec_dir))
        module, schema = doc.get('module'), doc.get('schema')
        if not isinstance(module, str) or not RE_MODULE.match(module):
            rep.err(where, f"module không hợp lệ: {module!r}")
            continue
        if not isinstance(schema, str) or not RE_IDENT.match(schema):
            rep.err(where, f"schema không hợp lệ: {schema!r}")
            continue
        expected_dir = Path(module[:2]) / module[2:]
        if path.parent.relative_to(spec_dir) != expected_dir:
            rep.err(where, f"file của module {module} phải nằm trong spec/{expected_dir}/")

        def add_entity(e, core, fid=None):
            name = e.get('name')
            eid = f"{schema}.{name}"
            w = f"{where} entity {eid}"
            if not isinstance(name, str) or not RE_IDENT.match(name):
                rep.err(w, "tên entity phải snake_case thường")
                return None
            if eid in entities:
                rep.err(w, "entity khai báo trùng")
            prof = e.get('profiles') or []
            fields = []
            if 'tenant' in prof:                         # tenant đứng đầu bảng
                fields += [_field(f, w, rep, codemaps, True) for f in profiles.get('tenant', [])]
            fields += [_field(f, w, rep, codemaps) for f in e.get('fields') or []]
            for p in prof:
                if p not in profiles:
                    rep.err(w, f"profile {p!r} chưa khai báo")
                elif p != 'tenant':
                    fields += [_field(f, w, rep, codemaps, True) for f in profiles[p]]
            fnames = [f['name'] for f in fields]
            for dup in sorted({x for x in fnames if fnames.count(x) > 1}):
                rep.err(w, f"cột {dup} trùng (có thể do profile)")
            fmap = {f['name']: f for f in fields}
            pk = e.get('pk') or []
            if not pk or any(c not in fmap for c in pk):
                rep.err(w, f"pk {pk} phải là danh sách cột có trong fields")
            for c in pk:
                if c in fmap and fmap[c]['nullable']:
                    rep.err(w, f"cột pk {c} không được nullable")
            tenant = 'tenant' in prof
            physical_pk = (['tenant_id'] if tenant and 'tenant_id' not in pk else []) + pk
            for ix in e.get('indexes') or []:
                if any(c not in fmap for c in ix):
                    rep.err(w, f"index {ix} có cột không tồn tại")
            ent = {
                'id': eid, 'module': module, 'schema': schema, 'name': name, 'n': names(name),
                'table': eid, 'label': e.get('label') or name, 'core': core, 'function': fid,
                'description': e.get('description', ''), 'pk': pk, 'physical_pk': physical_pk,
                'pk_fields': [fmap[c] for c in pk if c in fmap],
                'fields': fields, 'checks': e.get('checks') or [], 'indexes': e.get('indexes') or [],
                'tenant': tenant, 'owner_unit': 'owner_unit' in prof,
                'versioned': 'versioned' in prof, 'audit_cols': 'audit' in prof,
            }
            ent['api_fields'] = [f for f in fields if f['name'] != 'tenant_id']
            ent['input_fields'] = [f for f in fields if not f['readonly'] and f['name'] not in pk]
            ent['search_fields'] = [f for f in fields if f['search']]
            ent['sort_fields'] = [f['name'] for f in fields
                                  if not f['sensitive'] and f['type'] not in ('JSON',) and f['name'] != 'tenant_id']
            ent['example'] = {f['name']: f['example'] for f in fields
                              if f['example'] is not None and (f['name'] in pk or not f['readonly'])}
            entities[eid] = ent
            return ent

        for e in doc.get('entities') or []:
            add_entity(e, core=bool(e.get('core', False)))
        if not doc.get('function'):
            for r in doc.get('relations') or []:
                relations_raw.append({**r, '_schema': schema, '_where': where, '_fid': None})
        for f in doc.get('functions') or []:          # nút menu
            functions.append({'raw': f, 'module': module, 'schema': schema, 'where': where, 'entity': None})

        if doc.get('function'):
            f = doc['function']
            fid = f.get('id')
            if path.stem != fid:
                rep.err(where, f"tên file phải trùng mã chức năng: {fid}.yaml")
            ent = add_entity(doc.get('entity') or {}, core=False, fid=fid) if doc.get('entity') else None
            if not ent:
                rep.err(where, "function CRUD phải có entity")
            for r in doc.get('relations') or []:
                relations_raw.append({**r, 'child': (ent or {}).get('name'), '_schema': schema,
                                      '_where': where, '_fid': fid})
            functions.append({'raw': {**f, 'type': f.get('type', 'BOTH')}, 'module': module,
                              'schema': schema, 'where': where, 'entity': ent,
                              'actions': doc.get('actions') or list(ACTIONS),
                              'hooks': doc.get('hooks') or [], 'tests': doc.get('tests') or []})

    # ── function ──
    fn_by_id = {}
    for item in functions:
        f = item['raw']
        fid = f.get('id')
        w = f"{item['where']} function {fid}"
        m = RE_FID.match(str(fid))
        if not m:
            rep.err(w, "id phải dạng SSUU_NNNN, vd ATA0_0110")
            continue
        sys_, sub, no = m.groups()
        if sys_ + sub != item['module']:
            rep.err(w, f"id không thuộc module {item['module']}")
        if fid in fn_by_id:
            rep.err(w, "trùng mã chức năng")
        ftype = f.get('type', 'MENU')
        if ftype not in FUNC_TYPES:
            rep.err(w, f"type phải thuộc {sorted(FUNC_TYPES)}")
        base = f"/api/v1/{sys_.lower()}/{sub.lower()}/{no}"
        fn = {'id': fid, 'n': names(fid.lower()), 'module': item['module'], 'sys': sys_, 'sub': sub,
              'no': no, 'name': f.get('name') or fid, 'type': ftype, 'parent': f.get('parent'),
              'sort': f.get('sort', 0), 'description': f.get('description', ''),
              'target': f.get('target', 'java-spring'), 'entity': None,
              'url': f"/pages/{fid}.html" if item['entity'] else None,
              'api_base': base if item['entity'] else None,
              'actions': [], 'hooks': [], 'refs': [], 'children': [], 'tests': item.get('tests', [])}
        ent = item['entity']
        if ent:
            fn['entity'] = ent['id']
            for a in item['actions']:
                if a not in ACTIONS:
                    rep.err(w, f"action {a!r} không hỗ trợ; chỉ {sorted(ACTIONS)}")
                    continue
                right, method, with_pk = ACTIONS[a]
                path = base + ''.join(f"/{{{c}}}" for c in ent['pk']) if with_pk else base
                fn['actions'].append({'code': a, 'right': right, 'method': method, 'path': path,
                                      'with_pk': with_pk})
            seen_h = set()
            for h in item['hooks']:
                hw = f"{w} hook {h.get('name')}"
                if h.get('phase') not in PHASES:
                    rep.err(hw, f"phase phải thuộc {sorted(PHASES)}")
                if not RE_HOOK.match(str(h.get('name', ''))):
                    rep.err(hw, "name phải camelCase, vd validateDevice")
                if h.get('name') in seen_h:
                    rep.err(hw, "trùng tên hook")
                seen_h.add(h.get('name'))
                acts = h.get('actions') or ['CREATE', 'UPDATE']
                bad = [a for a in acts if a not in ('CREATE', 'UPDATE', 'DELETE')]
                if bad:
                    rep.err(hw, f"hook chỉ gắn CREATE/UPDATE/DELETE: {bad}")
                fn['hooks'].append({'phase': h.get('phase'), 'name': h.get('name'),
                                    'n': names(re.sub(r'(?<!^)([A-Z])', r'_\1', str(h.get('name'))).lower()),
                                    'actions': acts, 'description': h.get('description', '')})
        fn_by_id[fid] = fn
    for fn in fn_by_id.values():
        if fn['parent'] and fn['parent'] not in fn_by_id:
            rep.err(f"function {fn['id']}", f"parent {fn['parent']} không tồn tại")
    # chu trình + cấp
    for fn in fn_by_id.values():
        seen, cur, level = {fn['id']}, fn['parent'], 0
        while cur and cur in fn_by_id:
            level += 1
            if cur in seen:
                rep.err(f"function {fn['id']}", "cây chức năng có chu trình")
                break
            seen.add(cur)
            cur = fn_by_id[cur]['parent']
        fn['level'] = level

    # ── relation ──
    relations = []
    for r in relations_raw:
        w = f"{r['_where']} relation"
        child_id = f"{r['_schema']}.{r.get('child')}"
        parent_ref = r.get('parent')
        if parent_ref in fn_by_id:                       # tham chiếu tới function
            parent_id = fn_by_id[parent_ref]['entity']
        elif parent_ref and '.' in str(parent_ref):
            parent_id = parent_ref
        else:
            parent_id = f"{r['_schema']}.{parent_ref}"
        ce, pe = entities.get(child_id), entities.get(parent_id)
        if not ce or not pe:
            rep.err(w, f"entity không tồn tại: {child_id if not ce else parent_ref}")
            continue
        cols = r.get('cols') or []
        pcols = r.get('parent_cols') or pe['pk']
        if len(cols) != len(pcols) or not cols:
            rep.err(w, "cols và parent_cols phải cùng số cột")
            continue
        for c, p in zip(cols, pcols):
            cf = next((f for f in ce['fields'] if f['name'] == c), None)
            pf = next((f for f in pe['fields'] if f['name'] == p), None)
            if not cf or not pf:
                rep.err(w, f"cột không tồn tại: {c if not cf else p}")
            elif cf['type'] != pf['type']:
                rep.err(w, f"kiểu lệch {c}:{cf['type']} ≠ {p}:{pf['type']}")
        if sorted(pcols) != sorted(pe['pk']):
            rep.err(w, f"parent_cols {pcols} phải là pk {pe['pk']} của {parent_id}")
        od = r.get('on_delete', 'RESTRICT')
        if od not in ON_DELETE:
            rep.err(w, f"on_delete phải thuộc {sorted(ON_DELETE)}")
        slug = f"{ce['name']}__{'_'.join(cols)}" + (f"__{r['name']}" if r.get('name') else '')
        rel = {'id': f"{child_id}->{parent_id}" + (f"#{r['name']}" if r.get('name') else ''),
               'slug': slug, 'child': child_id, 'cols': cols, 'parent': parent_id,
               'parent_cols': pcols, 'on_delete': od, 'label': r.get('label') or pe['label'],
               'tenant_scoped': ce['tenant'] and pe['tenant'],
               'child_function': ce['function'], 'parent_function': pe['function']}
        relations.append(rel)
        if ce['function']:
            fn_by_id[ce['function']]['refs'].append(rel)
        if pe['function']:
            fn_by_id[pe['function']]['children'].append(rel)
        elif not pe['core']:
            pass

    # ── test data ──
    testdata = td_doc or {}
    for u in testdata.get('users') or []:
        for rl in u.get('roles') or []:
            if rl not in {x['role_id'] for x in testdata.get('roles') or []}:
                rep.err('_testdata.yaml', f"user {u.get('user_id')}: role {rl} chưa khai báo")
    for rl in testdata.get('roles') or []:
        for fid, rights in (rl.get('grants') or {}).items():
            if fid not in fn_by_id:
                rep.err('_testdata.yaml', f"role {rl['role_id']}: function {fid} không tồn tại")
            if not re.fullmatch(r'[RWDX]+', str(rights)):
                rep.err('_testdata.yaml', f"role {rl['role_id']}: quyền {rights!r} phải gồm R/W/D/X")
    for o in testdata.get('codemap_overrides') or []:
        if o.get('group') not in codemaps:
            rep.err('_testdata.yaml', f"codemap_overrides: nhóm {o.get('group')} không tồn tại")

    ir = {
        'ir_version': IR_VERSION,
        'project': {**project, 'package_path': str(project.get('package', '')).replace('.', '/')},
        'dialects': dialects,
        'targets': proj_doc.get('targets') or [],
        'codemaps': list(codemaps.values()),
        'entities': list(entities.values()),
        'relations': relations,
        'functions': sorted(fn_by_id.values(), key=lambda x: x['id']),
        'testdata': testdata,
    }
    return ir, rep


def entity(ir, eid):
    return next(e for e in ir['entities'] if e['id'] == eid)


def crud_functions(ir):
    return [f for f in ir['functions'] if f['entity']]
