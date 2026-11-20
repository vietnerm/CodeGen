// Sinh 1 lần bởi CodeGen, SAU ĐÓ do người/AI viết. Generator không ghi đè file này.
// Chỉ dùng API của vn.io.devhub.core (Ctx, Errors, Sql, Codemap…) — guard chặn java.sql/java.net/flowsql.
package vn.io.devhub.app.at.a0.ata0_0110.mod;

import java.time.LocalDate;
import org.springframework.stereotype.Component;
import vn.io.devhub.core.Ctx;
import vn.io.devhub.core.Errors;

@Component
public class ATA0_0110_hookImpl implements ATA0_0110_hook {

    /** VALIDATE · CREATE, UPDATE — Ngày lắp đặt không được ở tương lai */
    @Override
    public void validateDevice(Ctx ctx, String action, ATA0_0110_dto dto, Errors errors) {
        if (dto.installDate() != null && dto.installDate().isAfter(LocalDate.now())) {
            errors.add("install_date", "HOOK", "Ngày lắp đặt không được ở tương lai");
        }
    }
}
