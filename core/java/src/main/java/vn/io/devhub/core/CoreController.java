package vn.io.devhub.core;

import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** API dùng chung của core: đăng nhập, CODEMAP, menu. */
@RestController
@RequestMapping("/api/v1")
public class CoreController {
    private final Auth auth;
    private final Codemap codemap;
    private final Sql sql;

    public CoreController(Auth auth, Codemap codemap, Sql sql) {
        this.auth = auth;
        this.codemap = codemap;
        this.sql = sql;
    }

    public record TokenRequest(String userId, String password, String tenantId) {}

    @PostMapping("/auth/token")
    public Map<String, Object> token(@RequestBody TokenRequest req) {
        if (req == null || req.userId() == null || req.password() == null)
            throw ApiException.badRequest("Cần user_id và password");
        return auth.login(req.userId(), req.password(), req.tenantId());
    }

    @GetMapping("/codemap/{group}")
    public ResponseEntity<List<Map<String, Object>>> codemap(
            @RequestHeader(value = "Authorization", required = false) String authz,
            @PathVariable("group") String group,
            @RequestParam(value = "lang", defaultValue = "vi") String lang,
            @RequestParam(value = "parent", required = false) String parent) {
        Ctx ctx = auth.authenticate(authz);
        Map<String, Object> g = codemap.group(group)
                .filter(r -> "A".equals(Conv.str(r, "status")))
                .orElseThrow(() -> ApiException.notFound("Không có nhóm CODEMAP " + group));
        return ResponseEntity.ok()
                .eTag("\"" + group + "-" + Conv.lng(g, "data_version") + "-" + ctx.tenantId() + "\"")
                .body(codemap.list(ctx, group, parent, lang));
    }

    /** Cây chức năng có quyền R (kèm tổ tiên để dựng menu). */
    @GetMapping("/menu")
    public List<Map<String, Object>> menu(@RequestHeader(value = "Authorization", required = false) String authz) {
        Ctx ctx = auth.authenticate(authz);
        Map<String, Integer> masks = new HashMap<>();
        for (Map<String, Object> r : sql.list(ctx, "core.user_masks", Map.of()))
            masks.merge(Conv.str(r, "function_id"), Conv.integer(r, "right_mask"), (a, b) -> a | b);
        Map<String, Map<String, Object>> all = new LinkedHashMap<>();
        for (Map<String, Object> r : sql.list(ctx, "core.functions", Map.of())) {
            Map<String, Object> n = new LinkedHashMap<>();
            n.put("function_id", Conv.str(r, "function_id"));
            n.put("function_name", Conv.str(r, "function_name"));
            n.put("url", Conv.str(r, "url"));
            n.put("parent", Conv.str(r, "parent_function_id"));
            n.put("right_mask", masks.getOrDefault(Conv.str(r, "function_id"), 0));
            n.put("children", new ArrayList<Map<String, Object>>());
            all.put(Conv.str(r, "function_id"), n);
        }
        Set<String> keep = new HashSet<>();
        for (var e : masks.entrySet()) {
            if ((e.getValue() & 1) == 0) continue;
            String cur = e.getKey();
            Set<String> seen = new HashSet<>();
            while (cur != null && all.containsKey(cur) && seen.add(cur)) {
                keep.add(cur);
                cur = (String) all.get(cur).get("parent");
            }
        }
        List<Map<String, Object>> roots = new ArrayList<>();
        for (var n : all.values()) {
            if (!keep.contains((String) n.get("function_id"))) continue;
            Object parent = n.remove("parent");
            if (parent != null && keep.contains((String) parent)) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> ch = (List<Map<String, Object>>) all.get(parent).get("children");
                ch.add(n);
            } else {
                roots.add(n);
            }
        }
        return roots;
    }
}
