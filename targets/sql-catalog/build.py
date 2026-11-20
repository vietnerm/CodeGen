from codegen import model, sqlgen


def build(ir, ctx):
    ents = ctx['ents']
    files = {}
    groups = {'core': sqlgen.parse_catalog((ctx['root'] / 'core/sql/core.sql').read_text(encoding='utf-8'),
                                           'core/sql/core.sql')}
    for fn in model.crud_functions(ir):
        groups[fn['id']] = sqlgen.function_statements(ir, fn, ents.get)
    for d in ir['dialects']:
        header = (f"-- SINH TỰ ĐỘNG bởi CodeGen · dialect {d}"
                  f"{' (chuẩn)' if d == sqlgen.CANONICAL else ' (sqlglot chuyển từ ' + sqlgen.CANONICAL + ')'}"
                  f" · KHÔNG SỬA TAY")
        for name, stmts in groups.items():
            files[f"catalog/{d}/{name}.sql"] = sqlgen.render_catalog(stmts, d, header)
        files[f"catalog/{d}/index.txt"] = '\n'.join(f"{n}.sql" for n in groups) + '\n'
    return files
