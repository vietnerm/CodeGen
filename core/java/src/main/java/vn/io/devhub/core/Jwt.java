package vn.io.devhub.core;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** JWT HS256 tối giản (chỉ JDK + Jackson). Claims chuẩn core contract: sub, tenant, units, iat, exp. */
public final class Jwt {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Base64.Encoder B64 = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder D64 = Base64.getUrlDecoder();
    private static final String HEADER = B64.encodeToString("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));

    private final byte[] key;

    public Jwt(String secret) {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32)
            throw new IllegalStateException("app.jwt.secret (APP_JWT_SECRET) phải ≥ 32 byte");
        this.key = secret.getBytes(StandardCharsets.UTF_8);
    }

    public String sign(Map<String, Object> claims) {
        try {
            String body = B64.encodeToString(JSON.writeValueAsBytes(claims));
            String data = HEADER + "." + body;
            return data + "." + B64.encodeToString(hmac(data));
        } catch (Exception e) {
            throw new IllegalStateException("Ký JWT lỗi", e);
        }
    }

    /** Trả claims nếu chữ ký đúng và còn hạn; ngược lại ném 401. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> verify(String token, long nowEpochSec) {
        String[] parts = token.split("\\.");
        if (parts.length != 3 || !HEADER.equals(parts[0])) throw ApiException.unauthorized("Token không hợp lệ");
        byte[] expect = hmac(parts[0] + "." + parts[1]);
        byte[] got;
        try {
            got = D64.decode(parts[2]);
        } catch (IllegalArgumentException e) {
            throw ApiException.unauthorized("Token không hợp lệ");
        }
        if (!MessageDigest.isEqual(expect, got)) throw ApiException.unauthorized("Sai chữ ký token");
        Map<String, Object> claims;
        try {
            claims = JSON.readValue(D64.decode(parts[1]), Map.class);
        } catch (Exception e) {
            throw ApiException.unauthorized("Token không hợp lệ");
        }
        Object exp = claims.get("exp");
        if (!(exp instanceof Number n) || n.longValue() < nowEpochSec) throw ApiException.unauthorized("Token hết hạn");
        return claims;
    }

    private byte[] hmac(String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
