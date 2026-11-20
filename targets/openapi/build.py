import yaml

ERRORS = {
    '400': ('E_VALIDATION / E_BAD_REQUEST — dữ liệu không hợp lệ', True),
    '401': ('E_UNAUTHORIZED — thiếu hoặc sai token', False),
    '403': ('E_FORBIDDEN (thiếu quyền) / E_SCOPE (ngoài đơn vị được phép)', False),
    '404': ('E_NOT_FOUND — không có hoặc ngoài phạm vi tenant/đơn vị', False),
    '409': ('E_CONFLICT (row_version cũ) / E_DUPLICATE / E_RESTRICT (còn dữ liệu con)', False),
}


def field_schema(f, cm):
    t = f['type']
    s = {'TEXT': {'type': 'string'}, 'INT': {'type': 'integer', 'format': 'int32'},
         'BIGINT': {'type': 'integer', 'format': 'int64'}, 'DECIMAL': {'type': 'number'},
         'DATE': {'type': 'string', 'format': 'date'}, 'TIMESTAMP': {'type': 'string', 'format': 'date-time'},
         'BOOL': {'type': 'boolean'}, 'JSON': {'type': 'string', 'description': 'JSON'}}[t]
    s = dict(s)
    desc = [f['label']] + ([f['description']] if f['description'] else [])
    if f['length']:
        s['maxLength'] = f['length']
    if f['pattern']:
        s['pattern'] = f['pattern']
    if f['enum']:
        s['enum'] = f['enum']
    if f['min'] is not None:
        s['minimum'] = f['min']
    if f['max'] is not None:
        s['maximum'] = f['max']
    if f['codemap']:
        g = cm[f['codemap']]
        s['x-codemap'] = f['codemap']
        desc.append(f"CODEMAP `{f['codemap']}` (lấy danh sách hiệu lực: GET /api/v1/codemap/{f['codemap']}); "
                    f"mã chuẩn: " + ', '.join(f"{c['code']}={c['label']}" for c in g['codes']))
    if f['readonly']:
        s['readOnly'] = True
    if f['example'] is not None:
        s['example'] = f['example']
    if f['nullable']:
        s['nullable'] = True
    s['description'] = ' — '.join(desc)
    return s


def obj(fields, cm, required=()):
    o = {'type': 'object', 'properties': {f['name']: field_schema(f, cm) for f in fields}}
    req = [f['name'] for f in fields if f['name'] in required]
    if req:
        o['required'] = req
    return o


def core_paths():
    return {
        '/api/v1/auth/token': {'post': {
            'tags': ['core'], 'summary': 'Đăng nhập, nhận JWT', 'operationId': 'core_token', 'security': [],
            'requestBody': {'required': True, 'content': {'application/json': {'schema': {
                'type': 'object', 'required': ['user_id', 'password'],
                'properties': {'user_id': {'type': 'string'}, 'password': {'type': 'string', 'format': 'password'},
                               'tenant_id': {'type': 'string', 'description': 'Bắt buộc nếu user thuộc nhiều tenant'}}}}}},
            'responses': {'200': {'description': 'OK', 'content': {'application/json': {'schema': {
                'type': 'object', 'properties': {
                    'access_token': {'type': 'string'}, 'token_type': {'type': 'string', 'example': 'Bearer'},
                    'expires_in': {'type': 'integer'}, 'tenant_id': {'type': 'string'},
                    'units': {'type': 'array', 'items': {'type': 'string'}}}}}}},
                '401': {'$ref': '#/components/responses/E401'}}}},
        '/api/v1/codemap/{group}': {'get': {
            'tags': ['core'], 'summary': 'Danh sách CODEMAP hiệu lực của tenant', 'operationId': 'core_codemap',
            'parameters': [{'name': 'group', 'in': 'path', 'required': True, 'schema': {'type': 'string'}},
                           {'name': 'lang', 'in': 'query', 'schema': {'type': 'string', 'default': 'vi'}},
                           {'name': 'parent', 'in': 'query', 'schema': {'type': 'string'}}],
            'responses': {'200': {'description': 'OK (ETag = data_version của nhóm)', 'content': {
                'application/json': {'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/CodemapItem'}}}}},
                '401': {'$ref': '#/components/responses/E401'}, '404': {'$ref': '#/components/responses/E404'}}}},
        '/api/v1/menu': {'get': {
            'tags': ['core'], 'summary': 'Cây chức năng user được xem (quyền R)', 'operationId': 'core_menu',
            'responses': {'200': {'description': 'OK', 'content': {'application/json': {'schema': {
                'type': 'array', 'items': {'$ref': '#/components/schemas/MenuItem'}}}}},
                '401': {'$ref': '#/components/responses/E401'}}}},
    }


def components():
    return {
        'securitySchemes': {'bearer': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}},
        'schemas': {
            'Error': {'type': 'object', 'required': ['code', 'message'], 'properties': {
                'code': {'type': 'string', 'example': 'E_VALIDATION'}, 'message': {'type': 'string'},
                'details': {'type': 'array', 'items': {'type': 'object', 'properties': {
                    'field': {'type': 'string'}, 'code': {'type': 'string',
                    'description': 'REQUIRED | LENGTH | PATTERN | ENUM | RANGE | CODEMAP | REFERENCE | HOOK'},
                    'message': {'type': 'string'}}}}}},
            'CodemapItem': {'type': 'object', 'properties': {
                'code': {'type': 'string'}, 'label': {'type': 'string'}, 'parent_code': {'type': 'string', 'nullable': True},
                'seq': {'type': 'integer'}, 'attrs': {'type': 'string', 'nullable': True},
                'is_system': {'type': 'string', 'enum': ['Y', 'N']}}},
            'MenuItem': {'type': 'object', 'properties': {
                'function_id': {'type': 'string'}, 'function_name': {'type': 'string'}, 'url': {'type': 'string', 'nullable': True},
                'right_mask': {'type': 'integer'}, 'children': {'type': 'array', 'items': {'$ref': '#/components/schemas/MenuItem'}}}},
        },
        'responses': {f"E{k}": {'description': v[0], 'content': {'application/json': {
            'schema': {'$ref': '#/components/schemas/Error'}}}} for k, v in ERRORS.items()},
    }


def function_doc(ir, fn, e, cm):
    fid = fn['id']
    pascal = fid.replace('_', '')
    sch = {
        f"{pascal}": obj(e['api_fields'], cm),
        f"{pascal}Create": obj([f for f in e['api_fields'] if f['name'] in e['pk'] or not f['readonly']], cm,
                               required=[f['name'] for f in e['fields'] if f['required']]),
        f"{pascal}Update": obj([f for f in e['input_fields']] +
                               [f for f in e['fields'] if f['name'] == 'row_version'], cm,
                               required=[f['name'] for f in e['input_fields'] if f['required']] +
                                        (['row_version'] if e['versioned'] else [])),
        f"{pascal}Page": {'type': 'object', 'properties': {
            'items': {'type': 'array', 'items': {'$ref': f'#/components/schemas/{pascal}'}},
            'total': {'type': 'integer', 'format': 'int64'}, 'page': {'type': 'integer'}, 'size': {'type': 'integer'}}},
    }
    sch[f"{pascal}Update"]['properties'].pop('row_version', None)
    if e['versioned']:
        sch[f"{pascal}Update"]['properties']['row_version'] = {
            'type': 'integer', 'format': 'int64', 'description': 'row_version đang có (khoá lạc quan)'}
    pk_params = [{'name': c, 'in': 'path', 'required': True, 'schema': field_schema(f, cm)}
                 for c, f in zip(e['pk'], e['pk_fields'])]
    ext = {'x-function-id': fid, 'x-module': fn['module'],
           'x-relations': [{'cols': r['cols'], 'parent': r['parent'], 'on_delete': r['on_delete']} for r in fn['refs']],
           'x-children': [{'child': r['child'], 'cols': r['cols'], 'on_delete': r['on_delete']} for r in fn['children']],
           'x-hooks': [{'phase': h['phase'], 'name': h['name'], 'actions': h['actions'],
                        'description': h['description']} for h in fn['hooks']]}
    errs = lambda *codes: {c: {'$ref': f'#/components/responses/E{c}'} for c in codes}
    paths = {}
    for a in fn['actions']:
        op = {'tags': [fid], 'operationId': f"{fid}_{a['code'].lower()}", 'x-required-right': a['right'],
              'x-action': a['code'], **ext}
        name = fn['name']
        if a['code'] == 'SEARCH':
            op.update(summary=f"Tìm kiếm {name}", parameters=[
                {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'default': 0, 'minimum': 0}},
                {'name': 'size', 'in': 'query', 'schema': {'type': 'integer', 'default': 20, 'minimum': 1, 'maximum': 200}},
                {'name': 'sort', 'in': 'query', 'schema': {'type': 'string', 'enum': e['sort_fields']}},
                {'name': 'dir', 'in': 'query', 'schema': {'type': 'string', 'enum': ['asc', 'desc'], 'default': 'asc'}},
            ] + [{'name': f['name'], 'in': 'query', 'description': ('chứa (không phân biệt hoa thường)'
                  if f['search'] == 'like' else 'bằng'), 'schema': {'type': 'string'}} for f in e['search_fields']],
                responses={'200': {'description': 'OK', 'content': {'application/json': {'schema': {
                    '$ref': f'#/components/schemas/{pascal}Page'}}}}, **errs('400', '401', '403')})
        elif a['code'] == 'GET':
            op.update(summary=f"Xem {name}", parameters=pk_params, responses={'200': {'description': 'OK',
                'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{pascal}'}}}},
                **errs('401', '403', '404')})
        elif a['code'] == 'CREATE':
            op.update(summary=f"Tạo {name}", requestBody={'required': True, 'content': {'application/json': {
                'schema': {'$ref': f'#/components/schemas/{pascal}Create'}}}},
                responses={'201': {'description': 'Đã tạo', 'content': {'application/json': {'schema': {
                    '$ref': f'#/components/schemas/{pascal}'}}}}, **errs('400', '401', '403', '409')})
        elif a['code'] == 'UPDATE':
            op.update(summary=f"Sửa {name}", parameters=pk_params, requestBody={'required': True, 'content': {
                'application/json': {'schema': {'$ref': f'#/components/schemas/{pascal}Update'}}}},
                responses={'200': {'description': 'Đã sửa', 'content': {'application/json': {'schema': {
                    '$ref': f'#/components/schemas/{pascal}'}}}}, **errs('400', '401', '403', '404', '409')})
        elif a['code'] == 'DELETE':
            op.update(summary=f"Xoá {name}", parameters=pk_params + ([{'name': 'row_version', 'in': 'query',
                'required': True, 'schema': {'type': 'integer', 'format': 'int64'}}] if e['versioned'] else []),
                responses={'204': {'description': 'Đã xoá'}, **errs('401', '403', '404', '409')})
        paths.setdefault(a['path'], {})[a['method'].lower()] = op
    return paths, sch


def build(ir, ctx):
    cm = {g['group']: g for g in ir['codemaps']}
    p = ir['project']
    merged_paths, merged_schemas = core_paths(), {}
    files = {}
    for fn in [f for f in ir['functions'] if f['entity']]:
        e = ctx['ents'][fn['entity']]
        paths, sch = function_doc(ir, fn, e, cm)
        merged_paths.update(paths)
        merged_schemas.update(sch)
        comp = components()
        comp['schemas'].update(sch)
        doc = {'openapi': '3.0.3', 'info': {'title': f"{fn['id']} — {fn['name']}", 'version': p['version'],
               'description': fn['description']}, 'security': [{'bearer': []}], 'paths': paths, 'components': comp}
        files[f"openapi/{fn['id']}.yaml"] = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110)
    comp = components()
    comp['schemas'].update(merged_schemas)
    doc = {'openapi': '3.0.3', 'info': {'title': p.get('title', p['name']), 'version': p['version'],
           'description': f"Sinh từ spec bởi CodeGen (IR {ir['ir_version']}). Mọi API cần Bearer JWT trừ /auth/token."},
           'security': [{'bearer': []}], 'paths': merged_paths, 'components': comp}
    files['openapi/openapi.yaml'] = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110)
    return files
