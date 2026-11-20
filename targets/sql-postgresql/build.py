"""Target SQL theo dialect: logic chung ở codegen/ddl.py, khác biệt nằm trong types.yaml."""
from codegen import ddl


def build(ir, ctx):
    t = ctx['types']
    d = t['dialect']
    h = f"-- SINH TỰ ĐỘNG bởi CodeGen (IR {ir['ir_version']}) · dialect {d} · KHÔNG SỬA TAY"
    return {
        f"sql/{d}/00_schema.sql": ddl.schema_ddl(ir, d, t, h),
        f"sql/{d}/10_seed.sql": ddl.seed_sql(ir, d, t, h),
        f"sql/{d}/90_testdata.sql": ddl.testdata_sql(ir, d, t, h),
        f"sql/{d}/99_integrity.sql": ddl.integrity_sql(ir, d, t, h),
    }
