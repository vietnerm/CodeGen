package vn.io.devhub.core;

import java.util.ArrayList;
import java.util.List;

/** Gom lỗi validate theo trường rồi ném 1 lần (400 E_VALIDATION). */
public class Errors {
    private final List<ApiException.Detail> items = new ArrayList<>();

    public Errors add(String field, String code, String message) {
        items.add(new ApiException.Detail(field, code, message));
        return this;
    }

    public boolean has(String field) {
        return items.stream().anyMatch(d -> field.equals(d.field()));
    }

    public boolean isEmpty() { return items.isEmpty(); }

    public void throwIfAny() {
        if (!items.isEmpty()) {
            throw new ApiException(400, "E_VALIDATION", "Dữ liệu không hợp lệ", items);
        }
    }
}
