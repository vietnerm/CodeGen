package vn.io.devhub.core;

import java.util.List;

/** Lỗi nghiệp vụ chuẩn của core contract. ErrorAdvice đổi thành {"code","message","details"}. */
public class ApiException extends RuntimeException {
    public record Detail(String field, String code, String message) {}

    private static final long serialVersionUID = 1L;
    private final int status;
    private final String code;
    private final transient List<Detail> details;

    public ApiException(int status, String code, String message, List<Detail> details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details == null ? List.of() : List.copyOf(details);
    }

    public ApiException(int status, String code, String message) {
        this(status, code, message, List.of());
    }

    public int status() { return status; }
    public String code() { return code; }
    public List<Detail> details() { return details; }

    public static ApiException badRequest(String msg) { return new ApiException(400, "E_BAD_REQUEST", msg); }
    public static ApiException unauthorized(String msg) { return new ApiException(401, "E_UNAUTHORIZED", msg); }
    public static ApiException forbidden(String msg) { return new ApiException(403, "E_FORBIDDEN", msg); }
    public static ApiException scope(String msg) { return new ApiException(403, "E_SCOPE", msg); }
    public static ApiException notFound(String msg) { return new ApiException(404, "E_NOT_FOUND", msg); }
    public static ApiException conflict(String msg) { return new ApiException(409, "E_CONFLICT", msg); }
    public static ApiException duplicate(String msg) { return new ApiException(409, "E_DUPLICATE", msg); }
    public static ApiException restrict(String msg, List<Detail> d) { return new ApiException(409, "E_RESTRICT", msg, d); }
}
