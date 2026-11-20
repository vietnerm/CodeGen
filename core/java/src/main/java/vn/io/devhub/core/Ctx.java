package vn.io.devhub.core;

import java.util.List;

/** Ngữ cảnh request lấy từ JWT. Code sinh ra truyền Ctx vào mọi lệnh Sql — core tự gắn tenant/đơn vị. */
public record Ctx(String userId, String tenantId, List<String> units) {
    public Ctx {
        units = units == null ? List.of() : List.copyOf(units);
    }

    public boolean hasUnit(String unit) {
        return unit != null && units.contains(unit);
    }

    public String primaryUnit() {
        return units.isEmpty() ? null : units.get(0);
    }
}
