package vn.io.devhub.core;

import java.util.Map;

public record PageQuery(int page, int size, String sort, String dir, Map<String, Object> filters) {
    public PageQuery {
        if (page < 0) throw ApiException.badRequest("page phải >= 0");
        if (size < 1 || size > 200) throw ApiException.badRequest("size phải trong 1..200");
        dir = dir == null ? "asc" : dir.toLowerCase();
        if (!dir.equals("asc") && !dir.equals("desc")) throw ApiException.badRequest("dir phải asc|desc");
        filters = filters == null ? Map.of() : filters;
    }
}
