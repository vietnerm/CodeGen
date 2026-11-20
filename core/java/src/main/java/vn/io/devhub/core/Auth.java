package vn.io.devhub.core;

import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Xác thực + phân quyền theo function_id và bit quyền (R=1 W=2 D=4 X=8).
 * Quyền đọc từ DB mỗi request → thu hồi quyền có hiệu lực ngay (không chờ token hết hạn).
 */
@Component
public class Auth {
    private final Sql sql;
    private final Jwt jwt;
    private final long ttl;

    public Auth(Sql sql, @Value("${app.jwt.secret}") String secret, @Value("${app.jwt.ttl-seconds:3600}") long ttl) {
        this.sql = sql;
        this.jwt = new Jwt(secret);
        this.ttl = ttl;
    }

    public static int bit(char right) {
        return switch (right) {
            case 'R' -> 1;
            case 'W' -> 2;
            case 'D' -> 4;
            case 'X' -> 8;
            default -> throw new IllegalArgumentException("Quyền không hợp lệ: " + right);
        };
    }

    /** Chỉ kiểm token (API dùng chung như codemap, menu). */
    @SuppressWarnings("unchecked")
    public Ctx authenticate(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer "))
            throw ApiException.unauthorized("Thiếu Authorization: Bearer <token>");
        Map<String, Object> c = jwt.verify(authorization.substring(7).trim(), Instant.now().getEpochSecond());
        Object units = c.get("units");
        return new Ctx((String) c.get("sub"), (String) c.get("tenant"),
                units instanceof List<?> l ? (List<String>) l : List.of());
    }

    /** Token hợp lệ + có bit quyền trên function. */
    public Ctx require(String authorization, String functionId, char right) {
        Ctx ctx = authenticate(authorization);
        if ((mask(ctx, functionId) & bit(right)) == 0)
            throw ApiException.forbidden("Không có quyền " + right + " trên " + functionId);
        return ctx;
    }

    public int mask(Ctx ctx, String functionId) {
        int m = 0;
        for (Map<String, Object> r : sql.list(ctx, "core.permission", P.of("function_id", functionId)))
            m |= Conv.integer(r, "right_mask");
        return m;
    }

    public Map<String, Object> login(String userId, String password, String tenantId) {
        Map<String, Object> u = sql.one(null, "core.login", P.of("user_id", userId)).orElse(null);
        if (u == null || !"A".equals(Conv.str(u, "status")) || !Passwords.verify(password, Conv.str(u, "password_hash")))
            throw ApiException.unauthorized("Sai tài khoản hoặc mật khẩu");
        Map<String, List<String>> byTenant = new LinkedHashMap<>();
        for (Map<String, Object> r : sql.list(null, "core.user_units", P.of("user_id", userId)))
            byTenant.computeIfAbsent(Conv.str(r, "tenant_id"), k -> new ArrayList<>()).add(Conv.str(r, "unit_code"));
        String tenant = tenantId;
        if (tenant == null) {
            if (byTenant.size() != 1) throw ApiException.badRequest("User thuộc " + byTenant.size() + " tenant — cần tenant_id");
            tenant = byTenant.keySet().iterator().next();
        }
        List<String> units = byTenant.get(tenant);
        if (units == null) throw ApiException.forbidden("User không thuộc tenant " + tenant);
        long now = Instant.now().getEpochSecond();
        String token = jwt.sign(Map.of("sub", userId, "tenant", tenant, "units", units, "iat", now, "exp", now + ttl));
        return Map.of("access_token", token, "token_type", "Bearer", "expires_in", ttl, "tenant_id", tenant, "units", units);
    }
}
