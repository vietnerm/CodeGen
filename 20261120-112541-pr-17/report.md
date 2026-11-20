## Test giao diện — 75 đạt · 0 hỏng · 11s

### ✅ ATA0_0110 — Thiết bị ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập vào shell, sidebar menu dựng đúng | ✓ | `ATA0_0110/00-shell.png` |
| bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| nạp trang danh sách qua shell (bấm menu) | ✓ | `ATA0_0110/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0110/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0110/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0110/04-loi-trung-khoa.png` |
| sửa device_name | ✓ | `ATA0_0110/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0110/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0110/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| mở #/KHONG_TON_TAI → E_FORBIDDEN, không import | ✓ | `ATA0_0110/08-loi-khong-co-quyen.png` |
| viewer: bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| viewer chỉ R: không có nút tạo/sửa/xoá | ✓ |  |
| viewer chỉ R: không có lỗi JavaScript | ✓ |  |
| viewer chỉ R: xem được danh sách | ✓ | `ATA0_0110/90-viewer-chi-xem.png` |
| không có lỗi JavaScript trên trang | ✓ |  |
| T2: bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| tenant T2 có mã riêng DEVICE_TYPE.KIOSK trên UI | ✓ |  |
| tenant T2 ẩn DEVICE_TYPE.CRM trên UI | ✓ |  |
| codemap theo tenant: chụp màn hình | ✓ | `ATA0_0110/95-tenant-codemap.png` |
| codemap theo tenant: không có lỗi JavaScript | ✓ |  |

### ✅ ATA0_0120 — Hợp đồng bảo trì ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập vào shell, sidebar menu dựng đúng | ✓ | `ATA0_0120/00-shell.png` |
| bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| nạp trang danh sách qua shell (bấm menu) | ✓ | `ATA0_0120/01-danh-sach.png` |
| điền form tạo mới + dòng chi tiết | ✓ | `ATA0_0120/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0120/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| lưu kèm 1 dòng payments | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0120/04-loi-trung-khoa.png` |
| sửa vendor_name | ✓ | `ATA0_0120/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0120/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0120/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| viewer: bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| viewer chỉ R: không có nút tạo/sửa/xoá | ✓ |  |
| viewer chỉ R: không có lỗi JavaScript | ✓ |  |
| viewer chỉ R: xem được danh sách | ✓ | `ATA0_0120/90-viewer-chi-xem.png` |
| không có lỗi JavaScript trên trang | ✓ |  |

### ✅ ATA0_0121 — Lịch thanh toán hợp đồng

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập vào shell, sidebar menu dựng đúng | ✓ | `ATA0_0121/00-shell.png` |
| bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| nạp trang danh sách qua shell (bấm menu) | ✓ | `ATA0_0121/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0121/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0121/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0121/04-loi-trung-khoa.png` |
| sửa note | ✓ | `ATA0_0121/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0121/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0121/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| viewer: bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| viewer chỉ R: không có nút tạo/sửa/xoá | ✓ |  |
| viewer chỉ R: không có lỗi JavaScript | ✓ |  |
| viewer chỉ R: xem được danh sách | ✓ | `ATA0_0121/90-viewer-chi-xem.png` |
| không có lỗi JavaScript trên trang | ✓ |  |

### ✅ ATA0_0131 — Lịch bảo dưỡng thiết bị ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập vào shell, sidebar menu dựng đúng | ✓ | `ATA0_0131/00-shell.png` |
| bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| nạp trang danh sách qua shell (bấm menu) | ✓ | `ATA0_0131/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0131/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0131/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0131/04-loi-trung-khoa.png` |
| sửa service_person | ✓ | `ATA0_0131/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0131/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0131/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| viewer: bấm menu mở chức năng, breadcrumb đúng | ✓ |  |
| viewer chỉ R: không có nút tạo/sửa/xoá | ✓ |  |
| viewer chỉ R: không có lỗi JavaScript | ✓ |  |
| viewer chỉ R: xem được danh sách | ✓ | `ATA0_0131/90-viewer-chi-xem.png` |
| không có lỗi JavaScript trên trang | ✓ |  |
