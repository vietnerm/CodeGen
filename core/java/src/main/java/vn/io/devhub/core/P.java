package vn.io.devhub.core;

import java.util.HashMap;
import java.util.Map;

/** Map tham số cho phép null (Map.of không cho). */
public final class P {
    private P() {}

    public static Map<String, Object> of(Object... kv) {
        if (kv.length % 2 != 0) throw new IllegalArgumentException("P.of cần cặp key/value");
        Map<String, Object> m = new HashMap<>();
        for (int i = 0; i < kv.length; i += 2) m.put((String) kv[i], kv[i + 1]);
        return m;
    }
}
