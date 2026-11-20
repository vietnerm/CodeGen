## Test giao diện — 43 đạt · 1 hỏng · 21s

### ❌ ATA0_0110 — Thiết bị ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập, mở trang danh sách | ✓ | `ATA0_0110/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0110/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0110/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0110/04-loi-trung-khoa.png` |
| sửa device_name | ✓ | `ATA0_0110/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0110/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| bước giao diện bị kẹt | ✗ Locator.wait_for: Timeout 15000ms exceeded. | `ATA0_0110/07-loi.png` |
| không có lỗi JavaScript trên trang | ✓ |  |

### ✅ ATA0_0120 — Hợp đồng bảo trì ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập, mở trang danh sách | ✓ | `ATA0_0120/01-danh-sach.png` |
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
| không có lỗi JavaScript trên trang | ✓ |  |

### ✅ ATA0_0121 — Lịch thanh toán hợp đồng

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập, mở trang danh sách | ✓ | `ATA0_0121/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0121/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0121/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0121/04-loi-trung-khoa.png` |
| sửa note | ✓ | `ATA0_0121/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0121/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0121/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| không có lỗi JavaScript trên trang | ✓ |  |

### ✅ ATA0_0131 — Lịch bảo dưỡng thiết bị ATM

| Bước | Kết quả | Ảnh |
|---|---|---|
| đăng nhập, mở trang danh sách | ✓ | `ATA0_0131/01-danh-sach.png` |
| điền form tạo mới | ✓ | `ATA0_0131/02-form-tao.png` |
| tạo xong, dòng mới hiện trong danh sách | ✓ | `ATA0_0131/03-da-tao.png` |
| dữ liệu lưu đúng (kiểm qua API) | ✓ |  |
| tạo trùng khoá → hiện lỗi E_DUPLICATE | ✓ | `ATA0_0131/04-loi-trung-khoa.png` |
| sửa service_person | ✓ | `ATA0_0131/05-form-sua.png` |
| sửa xong, danh sách cập nhật | ✓ | `ATA0_0131/06-da-sua.png` |
| giá trị sửa đã lưu (kiểm qua API) | ✓ |  |
| xoá xong, dòng biến mất | ✓ | `ATA0_0131/07-da-xoa.png` |
| đã xoá (kiểm qua API) | ✓ |  |
| không có lỗi JavaScript trên trang | ✓ |  |
