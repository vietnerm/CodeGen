"""
Tầng 1 — IR là bản đồ nghiệp vụ; AI chỉ được chọn TRONG bản đồ đó.

  context(ir, text)          → phần IR liên quan tới mô tả (entity, cột, khoá, chức năng, codemap)
  dynamic_schema(ir, base)   → JSON schema ép model: parent/lookup/codemap chỉ nhận giá trị ĐANG CÓ
  impact(ir, fid)            → đổi chức năng này thì ảnh hưởng tới đâu (quan hệ, lookup, master–detail, file sinh)
"""
from __future__ import annotations

import copy
import re
import unicodedata

STOP = {'cua', 'va', 'cac', 'nhung', 'mot', 'cho', 'theo', 'voi', 'trong', 'la', 'co', 'duoc', 'khi',
        'thi', 'de', 'tu', 'den', 'ma', 'so', 'ten', 'ngay', 'danh', 'muc', 'quan', 'ly', 'chuc', 'nang',
        'the', 'of', 'and', 'for', 'id', 'no'}


def norm(s: str) -> str:
    s = unicodedata.normalize('NFD', str(s or '')).replace('đ', 'd').replace('Đ', 'D')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r'[^a-z0-9]+', norm(s)) if len(t) > 1 and t not in STOP}


def _ent_tokens(e, fn):
    words = [e['name'], e['label'], e['description'], fn['name'] if fn else '', fn['description'] if fn else '']
    words += [f"{f['name']} {f['label']}" for f in e['fields'] if not f['from_profile']]
    return tokens(' '.join(words))


def context(ir: dict, text: str, limit: int = 6) -> dict:
    """Entity/chức năng liên quan nhất tới mô tả + hàng xóm qua quan hệ."""
    fns = {f['entity']: f for f in ir['functions'] if f['entity']}
    want = tokens(text)
    ids_in_text = set(re.findall(r'[A-Z]{2}[A-Z0-9]{2}_\d{4}', text))
    scored = []
    for e in ir['entities']:
        if e['core']:
            continue
        fn = fns.get(e['id'])
        hit = len(want & _ent_tokens(e, fn)) + (10 if fn and fn['id'] in ids_in_text else 0)
        if hit:
            scored.append((hit, e['id']))
    picked = [eid for _, eid in sorted(scored, reverse=True)[:limit]]
    for r in ir['relations']:                                    # thêm hàng xóm 1 bước
        if r['child'] in picked and r['parent'] not in picked and len(picked) < limit + 3:
            picked.append(r['parent'])
    ents = {e['id']: e for e in ir['entities']}
    out = []
    for eid in picked:
        e, fn = ents[eid], fns.get(eid)
        out.append({
            'function': fn['id'] if fn else None, 'name': fn['name'] if fn else e['label'],
            'table': e['table'], 'pk': e['pk'],
            'fields': [{'name': f['name'], 'type': f['type'], 'label': f['label'],
                        **({'codemap': f['codemap']} if f['codemap'] else {})}
                       for f in e['base_api_fields'] if not f['from_profile']],
            'relations': [{'cols': r['cols'], 'parent': r['parent_function'] or r['parent'],
                           'on_delete': r['on_delete'], **({'composition': r['as']} if r['composition'] else {})}
                          for r in ir['relations'] if r['child'] == eid],
        })
    used_cm = {f.get('codemap') for o in out for f in o['fields']} - {None}
    return {
        'entities': out,
        'codemaps': {g['group']: {'name': g['name'], 'codes': [c['code'] for c in g['codes']],
                                  'used_by_related': g['group'] in used_cm} for g in ir['codemaps']},
        'functions': [{'id': f['id'], 'name': f['name'], 'type': f['type']} for f in ir['functions']],
    }


def dynamic_schema(ir: dict, base: dict) -> dict:
    """Thu hẹp schema chung theo IR hiện tại: không thể sinh tên chức năng/codemap/cột không tồn tại."""
    s = copy.deepcopy(base)
    crud = sorted(f['id'] for f in ir['functions'] if f['entity'])
    menus = sorted(f['id'] for f in ir['functions'])
    groups = sorted(g['group'] for g in ir['codemaps'])
    parent_fields = sorted({f['name'] for e in ir['entities'] if not e['core'] for f in e['base_api_fields']
                            if not f['from_profile']})
    props = s['properties']
    props['function']['properties']['parent'] = {'enum': menus}
    field_props = props['entity']['properties']['fields']['items']['properties']
    field_props['codemap'] = {'enum': groups}
    rel = props['relations']['items']['properties']
    rel['parent'] = {'enum': crud}
    rel['lookup'] = {'type': 'array', 'items': {'enum': parent_fields}}
    return s


def impact(ir: dict, fid: str) -> dict:
    fn = next((f for f in ir['functions'] if f['id'] == fid), None)
    if not fn:
        raise KeyError(fid)
    ents = {e['id']: e for e in ir['entities']}
    out = {'function': fid, 'name': fn['name'], 'entity': fn['entity'], 'menu_children': [], 'used_by': [],
           'uses': [], 'lookups_of_my_fields': [], 'codemaps': [], 'files': []}
    out['menu_children'] = [f['id'] for f in ir['functions'] if f['parent'] == fid]
    if not fn['entity']:
        return out
    e = ents[fn['entity']]
    for r in ir['relations']:
        if r['parent'] == e['id']:
            out['used_by'].append({'function': r['child_function'], 'table': r['child'], 'cols': r['cols'],
                                   'on_delete': r['on_delete'], 'composition': r['as'] if r['composition'] else None,
                                   'lookup': [x['field'] for x in r['lookup']]})
        if r['child'] == e['id']:
            out['uses'].append({'function': r['parent_function'], 'table': r['parent'], 'cols': r['cols'],
                                'lookup': [x['field'] for x in r['lookup']]})
    for other in ir['entities']:
        for lf in other['lookup_fields']:
            if lf['lookup']['parent_table'] == e['table']:
                out['lookups_of_my_fields'].append(f"{other['function'] or other['table']}.{lf['name']} ← {lf['lookup']['parent_field']}")
    out['codemaps'] = sorted({f['codemap'] for f in e['fields'] if f['codemap']})
    sys_, sub = fn['sys'], fn['sub']
    out['files'] = [f"spec/{sys_}/{sub}/{fid}.yaml", f"catalog/*/{fid}.sql", f"openapi/{fid}.yaml",
                    f"docs/{fid}.md", f"web/js/api/{fid}.js", f"web/pages/{fid}.html",
                    f"custom/…/{fid}_hookImpl.java (nếu có hook)"]
    return out
