package vn.io.devhub.core;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** CODEMAP hiệu lực theo tenant: dòng của tenant ghi đè dòng chung '*' (status I = ẩn). */
@Component
public class Codemap {
    private final Sql sql;

    public Codemap(Sql sql) { this.sql = sql; }

    public boolean exists(Ctx ctx, String group, String code) {
        if (code == null) return true;
        return sql.count(ctx, "core.codemap_exists", P.of("group_code", group, "code", code)) > 0;
    }

    public Optional<Map<String, Object>> group(String group) {
        return sql.one(null, "core.codemap_group", P.of("group_code", group));
    }

    public List<Map<String, Object>> list(Ctx ctx, String group, String parent, String lang) {
        List<Map<String, Object>> rows = sql.list(ctx, "core.codemap_list",
                P.of("group_code", group, "lang", lang == null ? "vi" : lang));
        if (parent == null) return rows;
        return rows.stream().filter(r -> parent.equals(Conv.str(r, "parent_code"))).toList();
    }
}
