package vn.io.devhub.core;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Đọc catalog SQL sinh ra (classpath: sql/&lt;dialect&gt;/index.txt + *.sql).
 * Định dạng (chung mọi ngôn ngữ):
 *   -- name: ATA0_0110.get
 *   -- params: a, b
 *   -- khoá: giá trị
 *   SELECT ...;
 */
public final class SqlCatalog {
    public record Stmt(String name, String sql, List<String> params, Map<String, String> meta) {
        public String meta(String k) { return meta.get(k); }
    }

    private static final Pattern NAME = Pattern.compile("^--\\s*name:\\s*(\\S+)\\s*$");
    private static final Pattern META = Pattern.compile("^--\\s*([a-z_]+):\\s*(.*)$");

    private final Map<String, Stmt> stmts = new LinkedHashMap<>();

    public static SqlCatalog load(String dialectDir) {
        SqlCatalog c = new SqlCatalog();
        String base = "sql/" + dialectDir + "/";
        String index = read(base + "index.txt");
        for (String f : index.split("\\R")) {
            if (!f.isBlank()) c.parse(read(base + f.trim()), base + f.trim());
        }
        if (c.stmts.isEmpty()) throw new IllegalStateException("Catalog SQL rỗng: " + base);
        return c;
    }

    public Stmt get(String name) {
        Stmt s = stmts.get(name);
        if (s == null) throw new IllegalStateException("Không có câu SQL '" + name + "' trong catalog");
        return s;
    }

    public Optional<Stmt> find(String name) { return Optional.ofNullable(stmts.get(name)); }

    public int size() { return stmts.size(); }

    void parse(String text, String where) {
        String name = null;
        Map<String, String> meta = new LinkedHashMap<>();
        List<String> params = List.of();
        StringBuilder sql = new StringBuilder();
        for (String line : (text + "\n-- name: __end__").split("\\R")) {
            Matcher m = NAME.matcher(line);
            if (m.matches()) {
                if (name != null) {
                    String s = sql.toString().trim();
                    if (s.endsWith(";")) s = s.substring(0, s.length() - 1).trim();
                    if (stmts.put(name, new Stmt(name, s, params, Map.copyOf(meta))) != null)
                        throw new IllegalStateException(where + ": trùng câu SQL " + name);
                }
                name = m.group(1);
                meta = new LinkedHashMap<>();
                params = List.of();
                sql.setLength(0);
                continue;
            }
            if (name == null) continue;
            Matcher mm = META.matcher(line);
            if (mm.matches() && sql.isEmpty()) {
                if ("params".equals(mm.group(1))) {
                    params = Arrays.stream(mm.group(2).split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList();
                } else {
                    meta.put(mm.group(1), mm.group(2).trim());
                }
                continue;
            }
            sql.append(line).append('\n');
        }
    }

    private static String read(String path) {
        try (InputStream in = SqlCatalog.class.getClassLoader().getResourceAsStream(path)) {
            if (in == null) throw new IllegalStateException("Không thấy resource " + path);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("Đọc " + path + " lỗi", e);
        }
    }
}
