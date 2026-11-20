// Sinh 1 lần bởi CodeGen, SAU ĐÓ do người/AI viết. Generator không ghi đè file này.
// Chỉ dùng API của vn.io.devhub.core (Ctx, Errors, Sql, Codemap…) — guard chặn java.sql/java.net/flowsql.
package vn.io.devhub.app.at.a0.ata0_0131.mod;

import org.springframework.stereotype.Component;
import vn.io.devhub.core.Ctx;
import vn.io.devhub.core.Errors;

@Component
public class ATA0_0131_hookImpl implements ATA0_0131_hook {

    /** VALIDATE · CREATE, UPDATE — Ngày thực hiện không được trước ngày dự kiến */
    @Override
    public void validateActualDate(Ctx ctx, String action, ATA0_0131_dto dto, Errors errors) {
        // TODO: Ngày thực hiện không được trước ngày dự kiến
    }
}
