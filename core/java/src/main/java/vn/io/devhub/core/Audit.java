package vn.io.devhub.core;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class Audit {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final Sql sql;

    public Audit(Sql sql) { this.sql = sql; }

    public void write(Ctx ctx, String functionId, String action, String target, Map<String, Object> detail) {
        String d;
        try {
            d = JSON.writeValueAsString(detail == null ? Map.of() : detail);
        } catch (Exception e) {
            d = "{}";
        }
        sql.exec(ctx, "core.audit_insert", P.of("function_id", functionId, "action", action,
                "target", target.length() > 300 ? target.substring(0, 300) : target, "detail", d));
    }
}
