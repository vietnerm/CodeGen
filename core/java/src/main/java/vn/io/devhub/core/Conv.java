package vn.io.devhub.core;

import java.math.BigDecimal;
import java.time.*;
import java.util.Map;
import vn.io.devhub.flowsql.Rows;

/** Đọc giá trị từ row FlowSQL (key chữ thường) sang kiểu Java — xử lý khác biệt giữa driver. */
public final class Conv {
    private Conv() {}

    public static String str(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        return v == null ? null : v.toString();
    }

    public static Integer integer(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        return v == null ? null : (v instanceof Number n ? n.intValue() : Integer.valueOf(v.toString()));
    }

    public static Long lng(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        return v == null ? null : (v instanceof Number n ? n.longValue() : Long.valueOf(v.toString()));
    }

    public static BigDecimal dec(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        if (v == null) return null;
        if (v instanceof BigDecimal b) return b;
        return new BigDecimal(v.toString());
    }

    public static Boolean bool(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        if (v == null) return null;
        if (v instanceof Boolean b) return b;
        String s = v.toString();
        return "1".equals(s) || "Y".equalsIgnoreCase(s) || "true".equalsIgnoreCase(s);
    }

    public static LocalDate date(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        if (v == null) return null;
        if (v instanceof LocalDate d) return d;
        if (v instanceof java.sql.Date d) return d.toLocalDate();
        if (v instanceof LocalDateTime t) return t.toLocalDate();
        return LocalDate.parse(v.toString().substring(0, 10));
    }

    public static OffsetDateTime ts(Map<String, Object> r, String k) {
        Object v = Rows.get(r, k);
        if (v == null) return null;
        if (v instanceof OffsetDateTime t) return t;
        if (v instanceof java.sql.Timestamp t) return t.toInstant().atOffset(ZoneOffset.UTC);
        if (v instanceof LocalDateTime t) return t.atOffset(ZoneOffset.UTC);   // MySQL DATETIME (UTC)
        if (v instanceof Instant t) return t.atOffset(ZoneOffset.UTC);
        return OffsetDateTime.parse(v.toString());
    }
}
