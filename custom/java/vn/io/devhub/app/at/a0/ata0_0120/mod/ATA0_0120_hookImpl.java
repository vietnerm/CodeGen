// Sinh 1 lần bởi CodeGen, SAU ĐÓ do người/AI viết. Generator không ghi đè file này.
// Chỉ dùng API của vn.io.devhub.core (Ctx, Errors, Sql, Codemap…) — guard chặn java.sql/java.net/flowsql.
package vn.io.devhub.app.at.a0.ata0_0120.mod;

import org.springframework.stereotype.Component;
import vn.io.devhub.core.Ctx;
import vn.io.devhub.core.Errors;

@Component
public class ATA0_0120_hookImpl implements ATA0_0120_hook {

    /** VALIDATE · CREATE, UPDATE — end_date phải >= start_date */
    @Override
    public void validateContractDates(Ctx ctx, String action, ATA0_0120_dto dto, Errors errors) {
        if (dto.startDate() != null && dto.endDate() != null && dto.endDate().isBefore(dto.startDate())) {
            errors.add("end_date", "HOOK", "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu");
        }
    }
}
