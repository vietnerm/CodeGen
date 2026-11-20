package vn.io.devhub.core;

import java.util.*;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import vn.io.devhub.flowsql.DataSet;
import vn.io.devhub.flowsql.DataSetRegistry;

/**
 * Lớp DB duy nhất code sinh ra được dùng. Bọc FlowSQL:
 *  • chạy câu SQL theo TÊN trong catalog đúng dialect của DataSet
 *  • tự gắn :_tenant, :_user, :_units từ Ctx (code sinh ra không tự truyền phạm vi)
 *  • bung tham số Collection: IN (:_units) → IN (:_units_0, :_units_1…)
 *  • phân trang/lọc/sắp xếp theo whitelist trong meta của catalog
 * Lưu ý FlowSQL: @Transactional của Spring KHÔNG áp dụng → dùng tx(...).
 */
@Component
public class Sql {
    private final DataSet db;
    private final Dialect dialect;
    private final SqlCatalog catalog;

    public Sql(DataSetRegistry registry, @Value("${app.datasource:main}") String datasource) {
        this.db = registry.get(datasource);
        this.dialect = Dialect.of(db.dbType());
        this.catalog = SqlCatalog.load(dialect.dir());
    }

    public Dialect dialect() { return dialect; }

    public SqlCatalog catalog() { return catalog; }

    public List<Map<String, Object>> list(Ctx ctx, String name, Map<String, Object> params) {
        return run(ctx, catalog.get(name).sql(), params);
    }

    public Optional<Map<String, Object>> one(Ctx ctx, String name, Map<String, Object> params) {
        List<Map<String, Object>> rows = list(ctx, name, params);
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public long count(Ctx ctx, String name, Map<String, Object> params) {
        return countSql(ctx, catalog.get(name).sql(), params);
    }

    public int exec(Ctx ctx, String name, Map<String, Object> params) {
        Bound b = bind(ctx, catalog.get(name).sql(), params);
        return db.execute(b.sql, b.params);
    }

    public <T> T tx(Supplier<T> work) { return db.inTransaction(work); }

    public void tx(Runnable work) { db.inTransaction(work); }

    /** SEARCH chuẩn: {fid}.select + {fid}.count + {fid}.filter.* + meta sort/pk. */
    public Page<Map<String, Object>> page(Ctx ctx, String fid, PageQuery q) {
        SqlCatalog.Stmt sel = catalog.get(fid + ".select");
        SqlCatalog.Stmt cnt = catalog.get(fid + ".count");
        StringBuilder where = new StringBuilder();
        Map<String, Object> p = new HashMap<>();
        for (Map.Entry<String, Object> f : q.filters().entrySet()) {
            Object v = f.getValue();
            if (v == null || v.toString().isBlank()) continue;
            SqlCatalog.Stmt cond = catalog.find(fid + ".filter." + f.getKey())
                    .orElseThrow(() -> ApiException.badRequest("Không lọc được theo " + f.getKey()));
            where.append(" AND (").append(cond.sql()).append(')');
            p.put("f_" + f.getKey(), "true".equals(cond.meta("like")) ? "%" + likeEscape(v.toString()) + "%" : v);
        }
        List<String> allowed = split(sel.meta("sort"));
        String a = sel.meta("alias") == null ? "" : sel.meta("alias") + ".";
        StringBuilder order = new StringBuilder(" ORDER BY ");
        if (q.sort() != null && !q.sort().isBlank()) {
            if (!allowed.contains(q.sort())) throw ApiException.badRequest("Không sắp xếp được theo " + q.sort());
            order.append(a).append(q.sort()).append(' ').append(q.dir()).append(", ");
        }
        order.append(String.join(", ", split(sel.meta("pk")).stream().map(c -> a + c).toList()));
        long total = countSql(ctx, cnt.sql() + where, p);
        p.put("_limit", q.size());
        p.put("_offset", q.page() * q.size());
        List<Map<String, Object>> rows = run(ctx, sel.sql() + where + order + dialect.pageSuffix(), p);
        return new Page<>(rows, total, q.page(), q.size());
    }

    // ───────────────────────── nội bộ ─────────────────────────
    private record Bound(String sql, Map<String, Object> params) {}

    private List<Map<String, Object>> run(Ctx ctx, String sql, Map<String, Object> params) {
        Bound b = bind(ctx, sql, params);
        return db.query(b.sql, b.params);
    }

    private long countSql(Ctx ctx, String sql, Map<String, Object> params) {
        Bound b = bind(ctx, sql, params);
        Object v = db.queryScalar(b.sql, b.params);
        return v == null ? 0 : ((Number) v).longValue();
    }

    private static final Pattern PARAM = Pattern.compile("(?<!:):([A-Za-z_][A-Za-z0-9_]*)");

    Bound bind(Ctx ctx, String sql, Map<String, Object> params) {
        Map<String, Object> p = new HashMap<>(params == null ? Map.of() : params);
        if (ctx != null) {
            p.put("_tenant", ctx.tenantId());
            p.put("_user", ctx.userId());
            p.put("_units", ctx.units());
        }
        StringBuilder out = new StringBuilder();
        Matcher m = PARAM.matcher(sql);
        Map<String, Object> bound = new HashMap<>();
        while (m.find()) {
            String name = m.group(1);
            Object v = p.get(name);
            if (v instanceof Collection<?> c) {
                if (c.isEmpty()) {
                    m.appendReplacement(out, "NULL");          // IN (NULL) → không dòng nào
                } else {
                    StringJoiner j = new StringJoiner(", ");
                    int i = 0;
                    for (Object x : c) {
                        String n = name + "_" + i++;
                        j.add(":" + n);
                        bound.put(n, x);
                    }
                    m.appendReplacement(out, Matcher.quoteReplacement(j.toString()));
                }
            } else {
                if (!p.containsKey(name)) throw new IllegalStateException("Thiếu tham số :" + name);
                bound.put(name, v);
                m.appendReplacement(out, Matcher.quoteReplacement(m.group(0)));
            }
        }
        m.appendTail(out);
        return new Bound(out.toString(), bound);
    }

    private static String likeEscape(String s) {
        return s.replace("%", "").replace("_", "");
    }

    private static List<String> split(String s) {
        if (s == null || s.isBlank()) return List.of();
        return Arrays.stream(s.split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList();
    }
}
