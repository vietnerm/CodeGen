# CodeGen

Sinh dự án từ **spec theo mã hệ thống** (SYS/SUB/FUNCTION). Mỗi ngày CI sinh → kiểm → build → chạy → test.
AI nhỏ chỉ viết **spec** (bị ép đúng JSON schema) và **hook nghiệp vụ nhỏ**; mọi code CRUD, SQL, API,
OpenAPI, tài liệu, JS SDK, trang, test đều sinh tất định từ template — không thể lệch chuẩn.

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
| `core/js` | kiến trúc sư | `core.js` (gọi API, token, codemap cache), `page.js` (trang CRUD từ meta) |
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
**chạy thật mọi câu SQL trong catalog** → build core + app → chạy app → test HTTP → kiểm toàn vẹn lần nữa.

CI (`.github/workflows/codegen.yml`): mỗi push/PR và 02:17 hằng ngày, ma trận **PostgreSQL + MySQL**.

## Thêm 1 chức năng

1. Tạo `spec/AT/A0/ATA0_0130.yaml` (xem `ATA0_0110.yaml`; schema: `schema/function-spec.schema.json`)
   — hoặc để AI làm: Actions → **ai-spec** → Run workflow (mô tả tiếng Việt → spec → chạy toàn bộ
   pipeline → đạt thì mở PR nhánh `ai/*`). Cần bật *Settings → Actions → General → Allow GitHub Actions
   to create and approve pull requests*; thêm secret `CODEGEN_BOT_TOKEN` nếu muốn PR đó chạy cả CI `codegen`.
2. `python generator.py build` → sinh `custom/…/ATA0_0130_hookImpl.java` nếu có hook; viết luật vào đó.
3. Khai báo test cho hook trong spec (`tests:`) — engine test chạy chung.
4. PR → CI chạy toàn bộ pipeline + guard.

API sinh ra cho mỗi function: `GET/POST {base}`, `GET/PUT/DELETE {base}/{pk}` với `base = /api/v1/<sys>/<sub>/<no>`.
Đã có sẵn: quyền theo action, lọc tenant + đơn vị, validate (bắt buộc/độ dài/pattern/enum/khoảng/CODEMAP),
kiểm tham chiếu (không FK), RESTRICT/CASCADE khi xoá, khoá lạc quan `row_version`, audit, phân trang/lọc/sắp xếp.

## Luật giữ chuẩn (tự động)

- **sqlglot lint**: cấm `ON CONFLICT`, `RETURNING`, `ILIKE`, `= ANY`, toán tử JSON/mảng, `LIMIT`, DDL, `SELECT *`
  trong catalog — thao tác đặc thù DB đi qua API của core (`Dialect` cài theo DBType).
- **guard** (`scripts/guard.py`, luật đọc từ `target.yaml`): hook không import `java.sql`, `java.net`, `flowsql`…;
  JS sinh ra không gọi `fetch` trực tiếp; PR nhánh `ai/*` chỉ được sửa `spec/<SYS>/<SUB>/<FID>.yaml` và `*_hookImpl.java`.
- **ai-spec**: output ép theo JSON schema + `generator.py validate`; sai thì đưa lỗi lại cho model (tối đa 3 lần).

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
