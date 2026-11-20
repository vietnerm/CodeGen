# CodeGen

Sinh dự án từ **spec theo mã hệ thống** (SYS/SUB/FUNCTION). Mỗi ngày CI sinh → kiểm → build → chạy → test.
AI nhỏ viết **spec**, **thân hook nghiệp vụ nhỏ** và **patch sửa nhỏ cho issue change/bug** (đều bị ép schema
JSON, chạy lại pipeline); mọi code CRUD, SQL, API, OpenAPI, tài liệu, JS SDK, khung web, test đều sinh
tất định từ template — không thể lệch chuẩn.

```
spec YAML ──validate──▶ IR (JSON, có version) ──▶ target pack ──▶ out/
                │                                   ├─ sql-postgresql / sql-mysql   DDL · seed · test data · toàn vẹn
                │                                   ├─ sql-catalog                  câu SQL có tên, mọi dialect (sqlglot)
                │                                   ├─ openapi · docs               API + tài liệu cho người và agent
                │                                   ├─ java-spring                  trx / mod / dto / hook (FlowSQL)
                │                                   ├─ js-sdk · html                api/<FID>.js qua core.js · trang Tabler
                │                                   └─ test-http                    test hộp đen, chạy với MỌI backend
                └─ sqlglot lint: chặn SQL không chuyển được giữa các DB
```

## Cấu trúc

| Thư mục | Ai sở hữu | Nội dung |
|---|---|---|
| `spec/_project.yaml`, `_codemaps.yaml`, `_testdata.yaml`, `spec/ZZ/**` | kiến trúc sư | dự án, dialect, profile cột chuẩn, CODEMAP, core DB |
| `spec/<SYS>/<SUB>/<FID>.yaml` | **AI / dev** | 1 file = 1 chức năng CRUD |
| `custom/java/**/<FID>_hookImpl.java` | **AI / dev** | luật nghiệp vụ riêng (sinh khung 1 lần, không bị ghi đè) |
| `core/java` | kiến trúc sư | `devhub-core`: JWT, quyền R/W/D/X, Sql (FlowSQL), CODEMAP, lỗi, audit |
| `core/js`, `core/css` | kiến trúc sư | `core.js` (gọi API, token, codemap cache), `page.js` (trang CRUD từ meta), `shell.js` (khung web thống nhất) + `layout.css` |
| `core/sql/core.sql` | kiến trúc sư | SQL của core — cùng lint/chuyển dialect như SQL sinh ra |
| `core/tests/http` | kiến trúc sư | bộ test core contract + CRUD (Python stdlib) |
| `targets/<tên>/` | kiến trúc sư | target pack: `target.yaml` + `types.yaml` + `templates/` + `build.py` |
| `codegen/`, `generator.py` | kiến trúc sư | engine: không chứa gì đặc thù ngôn ngữ |
| `out/` | sinh ra | không commit |

## Chạy

```bash
pip install -r requirements.txt -r requirements-ci.txt
python generator.py validate          # spec + SQL (CI gate)
python generator.py build             # → out/

# Pipeline đầy đủ (cần PostgreSQL hoặc MySQL, JDK 21, Maven)
DB_TYPE=postgresql DB_HOST=localhost DB_PORT=5432 DB_NAME=app DB_USER=app DB_PASS=app \
APP_JWT_SECRET=$(openssl rand -hex 32) bash scripts/pipeline.sh
# → http://localhost:8080/index.html  (maker1 / Passw0rd!)  ·  /openapi/openapi.yaml  ·  /docs/index.md
```

Các bước của `pipeline.sh`: sinh → guard → dựng DB (schema, seed, test data) → kiểm toàn vẹn →
**chạy thật mọi câu SQL trong catalog** → build core + app → chạy app → test HTTP → test giao diện
(shell + bấm menu) → lượt rút gọn layout thứ hai (PostgreSQL) → kiểm toàn vẹn lần nữa.

CI (`.github/workflows/codegen.yml`): mỗi push/PR và 02:17 hằng ngày, ma trận **PostgreSQL + MySQL**.

## Khung web thống nhất (shell)

Sau đăng nhập là **một shell** (`core/js/shell.js`): sidebar dọc menu cây nhiều cấp (đúng `_menu.yaml` + quyền R
theo tenant từ `GET /api/v1/menu`) + navbar + vùng nội dung. Bấm chức năng → router hash `#/<FID>` import
`js/api/<FID>.js` và nạp trang CRUD (`renderCrudPage`) vào vùng nội dung, không chuyển trang; có breadcrumb
theo đường đi cây, ô lọc menu bỏ dấu, nhớ nhóm đang mở, trang chào + chức năng gần đây; `/pages/<FID>.html`
chỉ redirect về hash (link cũ không gãy). User chỉ có quyền R thấy menu nhưng không có nút tạo/sửa/xoá.

Layout chọn trong `spec/_project.yaml` → `ui:` — **đổi 1 dòng → sinh lại, không sửa JS**:

```yaml
ui:
  layout: vertical-floating      # vertical-floating: navbar card tách mép · vertical-transparent: navbar trong suốt, cuộn thì nền mờ
  theme: light                   # light | dark
  brand: DevHub
```

≥992px sidebar mở; <992px thành off-canvas với nút ☰. Tabler + icons webfont được **vendor vào
`core/static/vendor/`** (ghi version trong tên thư mục) — chạy offline, không phụ thuộc CDN.

## Test giao diện có chụp màn hình

`core/tests/ui/run_ui.py` (Playwright, Chromium headless) chạy sau test API trong `pipeline.sh` — với MỌI chức năng:
đăng nhập ở `/index.html` (chụp `00-shell.png`) → **bấm menu** mở chức năng (mở nhóm cha trước, từ cây menu thật
`GET /api/v1/menu`) → kiểm `aria-current` + breadcrumb → danh sách → form tạo (kèm dòng chi tiết nếu có
master–detail) → tạo → lỗi trùng khoá → sửa → xoá, mỗi bước 1 ảnh và đối chiếu lại qua API. Thêm: viewer chỉ R
không có nút ghi; tenant T2 thấy codemap riêng trên UI; `#/KHONG_TON_TAI` → E_FORBIDDEN không import.
Selector lấy tất định từ metadata (`name` = tên cột, `data-menu`, `data-action`, `data-key`, `data-form`,
`data-breadcrumb` do `shell.js`/`page.js` gắn) — không đoán theo chữ hiển thị.

- Ảnh: `out/ui/<FID>/NN-buoc.png`, báo cáo `out/ui/report.md` (artifact của CI); lượt rút gọn layout thứ hai
  (`UI_LAYOUT` đè khi sinh) nằm ở `out/ui/<layout>/` và được gộp vào cùng comment để duyệt cả 2 layout
- PR (và issue/PR do AI tạo): ảnh được đẩy lên nhánh `ui-screenshots` (giữ 30 lần gần nhất) và bot cập nhật
  **một** comment có ảnh từng bước — người duyệt xem giao diện ngay trong PR
- `SKIP_UI=1` để bỏ qua khi chạy tay

## Thêm 1 chức năng

1. Tạo `spec/AT/A0/ATA0_0130.yaml` (xem `ATA0_0110.yaml`; schema: `schema/function-spec.schema.json`)
   — hoặc để AI làm: Actions → **ai-spec** → Run workflow (mô tả tiếng Việt → spec → chạy toàn bộ
   pipeline → đạt thì mở PR nhánh `ai/*`). Cần bật *Settings → Actions → General → Allow GitHub Actions
   to create and approve pull requests*; thêm secret `CODEGEN_BOT_TOKEN` nếu muốn PR đó chạy cả CI `codegen`.
2. `python generator.py build` → sinh `custom/…/ATA0_0130_hookImpl.java` nếu có hook; hook mô tả luật bằng văn bản
   + test ngay trong spec, AI nhỏ viết thân qua `scripts/ai_hook.py` (compile + chạy test hook, tối đa 3 vòng):
   ```yaml
   hooks:
     - name: validateActualDate
       'on': [create, update]      # nháy bắt buộc: YAML 1.1 hiểu 'on' là bool
       rule: Ngày thực hiện không được trước ngày dự kiến
       tests:
         - {input: {actual_date: '2026-05-09'}, error: {field: actual_date, code: E_RULE}}
         - {input: {actual_date: '2026-05-10'}, ok: true}
   ```
3. Test hook sinh tất định vào engine HTTP (đúng như test khai báo ở `tests:` của function).
4. PR → CI chạy toàn bộ pipeline + guard.

API sinh ra cho mỗi function: `GET/POST {base}`, `GET/PUT/DELETE {base}/{pk}` với `base = /api/v1/<sys>/<sub>/<no>`.
Đã có sẵn: quyền theo action, lọc tenant + đơn vị, validate (bắt buộc/độ dài/pattern/enum/khoảng/CODEMAP),
kiểm tham chiếu (không FK), RESTRICT/CASCADE khi xoá, khoá lạc quan `row_version`, audit, phân trang/lọc/sắp xếp.

## Quan hệ giữa bảng/chức năng (khai báo trong spec, sinh tất định)

```yaml
relations:
  - {cols: [device_id], parent: ATA0_0110, on_delete: RESTRICT, lookup: [device_name]}     # tham chiếu + hiện tên
  - {cols: [contract_no], parent: ATA0_0120, composition: true, as: payments}               # dòng chi tiết
```

| Khai báo | Sinh ra |
|---|---|
| `parent` + `on_delete` | kiểm tồn tại khi lưu (400 `REFERENCE`), RESTRICT/CASCADE/NULLIFY khi xoá cha, index, kiểm toàn vẹn |
| `lookup` | SELECT có LEFT JOIN, trường chỉ đọc trong API/OpenAPI, ô chọn có gợi ý trên trang |
| `composition` + `as` | cha nhận/trả mảng `as`; gửi mảng ⇒ thay toàn bộ dòng trong 1 transaction; khoá số trống ⇒ tự đánh số; xoá cha ⇒ xoá dòng; bảng chi tiết sửa trực tiếp trên trang |

## AI hiểu hệ thống qua IR (không phải trí nhớ của model)

```bash
python generator.py context "lịch bảo dưỡng cho thiết bị ATM"   # bảng/chức năng/codemap liên quan
python generator.py impact ATA0_0120                              # đổi chức năng này ảnh hưởng tới đâu
python generator.py schema                                        # JSON schema động: chỉ nhận chức năng/codemap/cột đang có
```

`ai_spec.py` chia việc cho hợp model nhỏ: **model chỉ trích danh sách trường** từ mô tả (schema nhỏ, `ref`/`codemap`
chỉ nhận giá trị đang có); **code ghép spec đầy đủ tất định** — profile, độ dài, tiền tệ, trạng thái, quan hệ + lookup
(kiểu/độ dài cột tham chiếu copy từ khoá bảng cha), hook từ luật nghiệp vụ. Validator kiểm cả `example` (pattern/enum/
độ dài/khoảng/codemap) và đưa lỗi lại cho model. Quyền test khai báo theo mẫu (`ATA0_*`) nên chức năng mới tự có quyền.

## Issue → AI tự xử lý

Tạo issue bằng form **🤖 AI: chức năng** (nhãn `ai`), workflow `ai-issue`:

- **Chức năng mới** → tìm ngữ cảnh trong IR → AI viết spec + **AI viết thân hook** (nếu nêu luật) → guard →
  pipeline đầy đủ → PR `Closes #N` + comment kết quả (gồm **bảng ý trong issue ↔ trường/hook/quan hệ sinh ra**,
  ý không khớp ghi ⚠️ chưa xử lý)
- **Sửa / Lỗi** → AI trích **patch nhỏ** (thêm/sửa/xoá field, thêm lookup) áp vào spec giữ comment → validate
  tối đa 3 vòng → đạt: pipeline + PR `spec(FID): AI sửa theo issue #N`; không đạt: phân tích ảnh hưởng
  (bảng, quan hệ, lookup, master–detail, file sinh) → comment + nhãn `needs-human`. Cấm đổi pk, xoá entity,
  sửa `_core.yaml`
- Comment `/ai` để chạy lại. Chỉ chạy với OWNER/MEMBER/COLLABORATOR.

## Luật giữ chuẩn (tự động)

- **sqlglot lint**: cấm `ON CONFLICT`, `RETURNING`, `ILIKE`, `= ANY`, toán tử JSON/mảng, `LIMIT`, DDL, `SELECT *`
  trong catalog — thao tác đặc thù DB đi qua API của core (`Dialect` cài theo DBType).
- **guard** (`scripts/guard.py`, luật đọc từ `target.yaml`): hook chỉ import được `Ctx/Errors/Conv/P` + `java.time`
  + `@Component`, thân hook cấm SQL/IO/reflection; hook không import `java.sql`, `java.net`, `flowsql`…;
  JS sinh ra không gọi `fetch` trực tiếp; PR nhánh `ai/*` chỉ được sửa `spec/<SYS>/<SUB>/<FID>.yaml` và
  `*_hookImpl.java`.
- **ai-spec / ai-hook / ai-change**: output ép theo JSON schema + `generator.py validate`; sai thì đưa lỗi lại
  cho model (tối đa 3 lần); hook/change hỏng sau 3 vòng thì trả stub/spec gốc và ghi lý do vào PR.

## CODEMAP

`zz.codemap_group` (định nghĩa, `attr_fields` cùng định dạng field) · `zz.codemap` (`tenant_id='*'` = chung;
dòng của tenant cùng mã **ghi đè**, `status='I'` = ẩn) · `zz.codemap_label` (đa ngôn ngữ).
Mã `system: true` sinh thành hằng số (`Codes.java`, `codes.js`) — code chỉ rẽ nhánh theo các mã này.
API: `GET /api/v1/codemap/{group}?lang=&parent=` (ETag theo `data_version`).

## Mở rộng

- **Ngôn ngữ backend mới** (vd C++ Drogon): thêm `targets/cpp-drogon/` (manifest + types + templates) và core SDK
  tương ứng đọc **cùng catalog SQL** (`-- name:` + `:param`). Đạt khi qua cùng `core/tests/http`. Không sửa generator.
- **DB mới**: thêm dialect vào `_project.yaml`, `targets/sql-<db>/types.yaml`, `Dialect` trong core và `DBType` trong FlowSQL.
- Đổi cấu trúc IR → tăng `IR_VERSION` (`codegen/model.py`); target khai báo `ir_versions`.
