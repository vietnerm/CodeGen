"""Sinh fixtures.json cho engine test: ví dụ hợp lệ, ca không hợp lệ, quan hệ, người dùng test."""
import json


def invalid_cases(e):
    out = []
    for f in e['api_fields']:
        if f['readonly'] or f['name'] == 'owner_unit':
            continue
        n, L = f['name'], f['length'] or 50
        if f['required']:
            out.append({'field': n, 'value': None, 'code': 'REQUIRED'})
        if f['enum']:
            out.append({'field': n, 'value': '#' * min(L, 1), 'code': 'ENUM'})
        elif f['codemap']:
            out.append({'field': n, 'value': 'ZZZ'[:L], 'code': 'CODEMAP'})
        if f['pattern']:
            out.append({'field': n, 'value': '!!'[:L], 'code': 'PATTERN'})
        if f['type'] == 'TEXT' and f['length'] and not f['pattern'] and not f['enum'] and not f['codemap']:
            out.append({'field': n, 'value': 'x' * (f['length'] + 1), 'code': 'LENGTH'})
        if f['min'] is not None:
            out.append({'field': n, 'value': f['min'] - 1, 'code': 'RANGE'})
        if f['max'] is not None:
            out.append({'field': n, 'value': f['max'] + 1, 'code': 'RANGE'})
    return out


def update_field(e, fn):
    ref_cols = {c for r in fn['refs'] for c in r['cols']}
    for f in e['input_fields']:
        if f['type'] == 'TEXT' and not (f['pattern'] or f['enum'] or f['codemap']) \
                and f['name'] != 'owner_unit' and f['name'] not in ref_cols:
            return f['name']
    return None


def build(ir, ctx):
    ents = ctx['ents']
    bits = {'R': 1, 'W': 2, 'D': 4, 'X': 8}
    roles = {r['role_id']: r for r in ir['testdata'].get('roles') or []}
    users = []
    for u in ir['testdata'].get('users') or []:
        rights = {}
        for rl in u.get('roles') or []:
            for fid, rs in (roles[rl].get('grants') or {}).items():
                rights[fid] = rights.get(fid, 0) | sum(bits[c] for c in set(rs))
        users.append({'user_id': u['user_id'], 'password': u['password'], 'tenant': u['tenant'],
                      'units': u.get('units') or [], 'rights': rights})
    fns = {}
    for fn in ir['functions']:
        if not fn['entity']:
            continue
        e = ents[fn['entity']]
        fns[fn['id']] = {
            'id': fn['id'], 'name': fn['name'], 'base': fn['api_base'], 'pk': e['pk'],
            'versioned': e['versioned'], 'tenant': e['tenant'], 'owner_unit': e['owner_unit'],
            'example': e['example'], 'update_field': update_field(e, fn), 'invalid': invalid_cases(e),
            'actions': [a['code'] for a in fn['actions']],
            'types': {f['name']: f['type'] for f in e['api_fields']},
            'search': [{'field': f['name'], 'kind': f['search']} for f in e['search_fields']],
            'refs': [{'cols': r['cols'], 'parent_fid': r['parent_function'], 'parent_cols': r['parent_cols']}
                     for r in fn['refs'] if r['parent_function']],
            'children': [{'child_fid': r['child_function'], 'cols': r['cols'], 'parent_cols': r['parent_cols'],
                          'on_delete': r['on_delete']} for r in fn['children'] if r['child_function']],
            'tests': fn['tests'],
        }
    fixtures = {'ir_version': ir['ir_version'], 'users': users, 'functions': fns,
                'codemap_overrides': ir['testdata'].get('codemap_overrides') or [],
                'codemap_groups': {g['group']: [c['code'] for c in g['codes']] for g in ir['codemaps']}}
    return {'tests/http/fixtures.json': json.dumps(fixtures, ensure_ascii=False, indent=2)}
