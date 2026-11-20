package vn.io.devhub.core;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/** pbkdf2_sha256$iter$salt_b64$hash_b64 — cùng định dạng generator (Python) băm dữ liệu test. */
public final class Passwords {
    private static final int ITER = 120_000;
    private Passwords() {}

    public static String hash(String password) {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] dk = derive(password, salt, ITER, 32);
        return "pbkdf2_sha256$" + ITER + "$" + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(dk);
    }

    public static boolean verify(String password, String stored) {
        if (password == null || stored == null) return false;
        String[] p = stored.split("\\$");
        if (p.length != 4 || !"pbkdf2_sha256".equals(p[0])) return false;
        try {
            int iter = Integer.parseInt(p[1]);
            byte[] salt = Base64.getDecoder().decode(p[2]);
            byte[] expect = Base64.getDecoder().decode(p[3]);
            return MessageDigest.isEqual(expect, derive(password, salt, iter, expect.length));
        } catch (RuntimeException e) {
            return false;
        }
    }

    private static byte[] derive(String password, byte[] salt, int iter, int len) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), salt, iter, len * 8);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
