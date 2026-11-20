package vn.io.devhub.core;

import java.sql.SQLException;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import vn.io.devhub.flowsql.FlowSqlException;

/** Mọi lỗi → {"code","message","details"} theo core contract. */
@RestControllerAdvice
public class ErrorAdvice {
    private static final Logger log = LoggerFactory.getLogger(ErrorAdvice.class);

    public record ErrorBody(String code, String message, List<ApiException.Detail> details) {}

    private static ResponseEntity<ErrorBody> body(int status, String code, String msg, List<ApiException.Detail> d) {
        return ResponseEntity.status(status).body(new ErrorBody(code, msg, d == null ? List.of() : d));
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorBody> api(ApiException e) {
        return body(e.status(), e.code(), e.getMessage(), e.details());
    }

    @ExceptionHandler(FlowSqlException.class)
    public ResponseEntity<ErrorBody> sql(FlowSqlException e) {
        SQLException s = null;
        for (Throwable t = e; t != null; t = t.getCause()) if (t instanceof SQLException x) { s = x; break; }
        String state = s == null || s.getSQLState() == null ? "" : s.getSQLState();
        int vendor = s == null ? 0 : s.getErrorCode();
        if ("23505".equals(state) || vendor == 1062) return body(409, "E_DUPLICATE", "Bản ghi đã tồn tại", null);
        if ("23514".equals(state) || vendor == 3819)
            return body(400, "E_VALIDATION", "Vi phạm ràng buộc dữ liệu (CHECK)", null);
        if (state.startsWith("23")) return body(409, "E_CONSTRAINT", "Vi phạm ràng buộc dữ liệu", null);
        log.error("Lỗi SQL", e);
        return body(500, "E_INTERNAL", "Lỗi hệ thống", null);
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class,
                       MissingServletRequestParameterException.class})
    public ResponseEntity<ErrorBody> badRequest(Exception e) {
        return body(400, "E_BAD_REQUEST", "Yêu cầu không hợp lệ: " + e.getClass().getSimpleName(), null);
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ErrorBody> notFound(NoResourceFoundException e) {
        return body(404, "E_NOT_FOUND", "Không tìm thấy", null);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorBody> other(Exception e) {
        log.error("Lỗi không xử lý", e);
        return body(500, "E_INTERNAL", "Lỗi hệ thống", null);
    }

}
