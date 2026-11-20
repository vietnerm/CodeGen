package vn.io.devhub.core;

import vn.io.devhub.flowsql.DBType;

/**
 * Phần SQL đặc thù DB mà catalog KHÔNG được chứa (sqlglot lint chặn) — core cài theo DBType.
 * Thêm DB mới = thêm 1 hằng ở đây + DBType trong FlowSQL + dialect trong _project.yaml.
 */
public enum Dialect {
    POSTGRESQL("postgresql", " LIMIT :_limit OFFSET :_offset"),
    MYSQL("mysql", " LIMIT :_limit OFFSET :_offset");

    private final String dir;
    private final String pageSuffix;

    Dialect(String dir, String pageSuffix) {
        this.dir = dir;
        this.pageSuffix = pageSuffix;
    }

    /** Thư mục catalog: sql/&lt;dir&gt;/ */
    public String dir() { return dir; }

    public String pageSuffix() { return pageSuffix; }

    public static Dialect of(DBType t) {
        if (t == null) return POSTGRESQL;
        return switch (t) {
            case POSTGRESQL -> POSTGRESQL;
            case MYSQL, MARIADB, H2 -> MYSQL;      // H2 của FlowSQL chạy chế độ MySQL
        };
    }
}
