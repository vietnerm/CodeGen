# Số liệu pipeline (PR-16 mục 1)

Vì sao có file này: không đo thì không biết cache có lợi bao nhiêu và không biết bước nào
đáng tối ưu tiếp. `scripts/pipeline.sh` tự bấm giờ từng bước (`SECONDS`), in `⏱ <bước> — <gi>s`
và ghi `/tmp/codegen-steps-<DB>.tsv`; comment PR tự ghim bảng này (kèm bảng FID thay đổi).
Số liệu CI (2 DB, mvn lạnh) sẽ được cập nhật qua từng comment PR — đây là nguồn trung thực nhất.

## Baseline đo tại máy dev — PostgreSQL 16.4, Java 21 (Temurin), Maven 3.9.9, m2 đã ấm

Cùng một pipeline chạy 2 lần liên tiếp, không sửa gì giữa hai lần:

| Bước | Run có mvn thật (s) | Run bỏ qua mvn (s) |
|---|---|---|
| 1. Kiểm tra + sinh từ spec | 1 | 1 |
| 2. Guard: code viết tay không vượt chuẩn | 0 | 0 |
| 3. Dựng DB (postgresql): schema → seed → dữ liệu test | 0 | 1 |
| 4. Chạy thật mọi câu SQL trong catalog | 0 | 0 |
| 5. Build core SDK + app | **9** | **0** (khôi phục jar từ `.cache/`) |
| 6. Chạy app + test HTTP (core contract + CRUD + hook) | 7 | 7 |
| 6b. Test giao diện (Playwright) + chụp màn hình | 11 | 10 |
| 7. Toàn vẹn dữ liệu sau test | 0 | 0 |
| 8. Ghi state build xanh (`.cache`) | 0 | 1 |
| 9. Test giao diện layout thứ hai (UI_LAYOUT, rút gọn) | 12 | 11 |
| **Tổng** | **~40** | **~31** |

Đọc số liệu:

- Máy dev m2 ấm thì mvn chỉ chiếm ~23% tổng thời gian. Ở CI đo lần đầu (run 44721884152) mvn
  chỉ ~13–14s vì setup-java@v4 có cache maven — m2 không lạnh như dự đoán; nhưng bước 5 vẫn
  là bước đơn lớn nhất → đó là chỗ cache nhắm tới (Mức B(i), bỏ qua khi nguồn Java y hệt lần
  xanh trước). App lớn dần thì mvn lớn theo.
- Bỏ qua mvn phải đảm bảo jar khớp nguồn: state được ghi ở bước 8 (trước lượt layout thứ hai)
  và kèm jar layout mặc định; bước 9 luôn mvn lại vì `static/index.html` của layout 2 phải vào
  đúng jar (thử nghiệm run 2 — xem commit "ghi state ở bước 8 TRƯỚC lượt layout thứ hai").
- Thử nghiệm xác nhận: run 4/5 bỏ qua mvn ở bước 5, toàn bộ test HTTP + 75 bước UI + layout 2
  vẫn xanh; `python generator.py changes` báo "không có gì đổi về IR".

## MySQL và số liệu CI

- Sandbox máy dev không có MySQL/MariaDB server — MySQL đo ở CI (môi trường thật của dự án).
- Mỗi lần chạy CI, `codegen.yml` in `⏱` từng bước trong log (gộp `::group::`) và comment PR
  có bảng "Thời gian từng bước" — lấy số đó để cập nhật bảng dưới đây ở các PR sau.

| Môi trường | mvn thật (s) | bỏ qua mvn (s) | Ghi chú |
|---|---|---|---|
| CI ubuntu-latest · PostgreSQL | 12 | _(chờ run có .cache v3)_ | run 44728532119 · G key = G state = 2d11794c…, tất định |
| CI ubuntu-latest · MySQL | 12 | _(chờ run có .cache v3)_ | run 44728532119 · sai lệch 2–3s giữa các run là bình thường |
