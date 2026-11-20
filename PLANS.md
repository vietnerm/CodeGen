# PLANS — việc tiếp theo cho agent coding (ZAI)

> Đọc hết file này trước khi sửa code. Làm **từng task theo thứ tự**, mỗi task một nhánh + một PR,
> CI (`codegen.yml`) phải xanh cả `postgresql` và `mysql` mới coi là xong.
> Ngôn ngữ: comment, commit, PR, tài liệu bằng **tiếng Việt**.

---

## 0. Bối cảnh (đọc kỹ)

CodeGen sinh dự án từ **spec YAML theo mã hệ thống** `SYS/SUB/FUNCTION` (vd. `spec/AT/A0/ATA0_0110.yaml`).
Luồng: `spec → validate → IR (JSON, IR_VERSION 1.0) → target pack (Jinja2) → out/`.
AI nhỏ (Qwen3-1.7B) **chỉ viết spec và hook nghiệp vụ nhỏ**; CRUD, SQL, API, OpenAPI, docs, JS SDK, trang, test
đều sinh tất định. Chiến lược hiện tại: **hoàn thiện các agent nhỏ**, chưa phụ thuộc agent lớn.

Trạng thái `main` (sau khi merge PR #11): 185 test API + 45 bước test giao diện xanh trên PostgreSQL & MySQL.

### Thư mục & quyền sở hữu

| Đường dẫn | Nội dung | Ai được sửa |
|---|---|---|
| `spec/ZZ/A0/_core.yaml` | DB core (user, role, function, function_tree, codemap, audit…) | kiến trúc sư — **AI không sửa** |
| `spec/<SYS>/<SUB>/*.yaml` | spec chức năng, `_menu.yaml` = nút menu | AI nhỏ / người |
| `spec/_project.yaml`, `_codemaps.yaml`, `_testdata.yaml` | cấu hình dự án, CODEMAP, dữ liệu test | người |
| `codegen/` (`model.py`, `sqlgen.py`, `ddl.py`, `render.py`, `ai.py`) | generator, **không chứa gì riêng ngôn ngữ** | người/ZAI |
| `targets/<name>/` | target pack: `target.yaml`, `types.yaml`, `templates/*.j2` | người/ZAI |
| `core/java` | devhub-core (Spring Boot 3.3.5, Java 21, FlowSQL) viết tay | người/ZAI |
| `core/js/core.js`, `core/js/page.js` | SDK JS chung: request/login/codemap + dựng trang CRUD từ meta | người/ZAI |
| `core/sql/core.sql` | câu SQL có tên của core | người/ZAI |
| `core/tests/http/run_all.py`, `core/tests/ui/run_ui.py` | test hộp đen API + Playwright | người/ZAI |
| `custom/java/.../*_hookImpl.java` | thân hook nghiệp vụ (không bị ghi đè khi sinh lại) | AI nhỏ / người |
| `scripts/` | pipeline, guard, ai_spec, ai_issue, publish_ui, laya_eval | người/ZAI |
| `out/` | **sinh ra — không bao giờ sửa tay, không commit** | — |

### Lệnh

```bash
pip install -r requirements.txt -r requirements-ci.txt
python -m playwright install --with-deps chromium
python generator.py validate            # kiểm spec
python generator.py build               # sinh out/
DB_TYPE=postgresql scripts/pipeline.sh  # 1 sinh · 2 guard · 3 DB+toàn vẹn · 4 catalog · 5 mvn · 6 app+test API · 6b test UI · 7 toàn vẹn
# cờ: SKIP_APP=1 SKIP_BUILD=1 SKIP_UI=1 KEEP_RUNNING=1
python generator.py context "<mô tả>"   # ngữ cảnh IR cho AI
python generator.py impact ATA0_0120    # phân tích ảnh hưởng
```

### Quy ước BẮT BUỘC (vi phạm = CI đỏ hoặc phá kiến trúc)

1. **Không FOREIGN KEY.** Quan hệ khai báo trong `relations` của spec; engine kiểm tồn tại, RESTRICT/CASCADE/NULLIFY;
   `integrity_sql` phát hiện mồ côi/chu trình.
2. **SQL viết dạng PostgreSQL chuẩn**, transpile sang MySQL bằng sqlglot 30.33.0. Lint cấm: `ON CONFLICT`, `RETURNING`,
   `ILIKE`, `ANY`, toán tử JSON, `LIMIT` (dùng `Sql.page()`), DDL trong catalog, `SELECT *`. DDL sinh theo `types.yaml`.
3. **FlowSQL**: tham số `:name`, transaction bằng `inTransaction` (KHÔNG dùng `@Transactional`); key của row map là **chữ thường**.
4. Hợp đồng core: JWT HS256 (`sub, tenant, units, iat, exp`); quyền R=1 W=2 D=4 X=8;
   lỗi `{code, message, details[{field, code, message}]}`; mật khẩu `pbkdf2_sha256$iter$salt$hash`.
5. CODEMAP theo tenant: `'*'` dùng chung, dòng của tenant ghi đè, `status='I'` là ẩn.
6. File sinh ra có header `SINH TỰ ĐỘNG … KHÔNG SỬA TAY`. Muốn đổi → sửa template/core, không sửa `out/`.
7. Trang sinh ra **không viết logic**: chỉ gọi `core/js/page.js` với `api` module. Mọi phần tử tương tác phải có
   thuộc tính tất định để test: `data-action`, `data-form`, `data-key`, `data-error`, `data-total`, `data-page`.
   Không đổi/xoá các thuộc tính đang có (test UI dựa vào).
8. `render.py` copy file theo thứ tự **nguồn `repo:` trước** — giữ nguyên (lỗi trang trắng cũ do sai thứ tự).
9. Giữ `pinned` versions trong `requirements*.txt`; không thêm phụ thuộc nặng (torch…) vào CI chính.
10. PR tạo bằng `GITHUB_TOKEN` không kích hoạt workflow khác (cần secret `CODEGEN_BOT_TOKEN` nếu muốn).

### Môi trường local (nếu chạy ngoài CI)

PostgreSQL 16 ở `/tmp/pg` cổng 5544, user/pass `app/app`. Sau khi máy khởi động lại:
`rm -f /tmp/pg/data/postmaster.pid && pg_ctl -D /tmp/pg/data start`. CDN Tabler có thể bị chặn local → xem T1.5.

---

## T1. Khung web thống nhất: layout vertical + menu nhiều cấp + nội dung chức năng  ⭐ ưu tiên

**Mục tiêu:** một khối web liên kết. Sau đăng nhập là **một shell** gồm sidebar dọc (menu cây đúng như khai báo,
từng cấp) + navbar + vùng nội dung; bấm chức năng thì nội dung CRUD (như hiện tại, `renderCrudPage`) nạp vào vùng
nội dung, không chuyển trang.

Hiện trạng: `targets/html/templates/index.html.j2` chỉ in `<ul>` lồng nhau; mỗi chức năng là trang rời
`web/pages/<FID>.html` có link "← Menu". API `GET /api/v1/menu` (CoreController) đã trả cây
`[{function_id, function_name, url, right_mask, children[]}]` — chỉ gồm chức năng user có quyền R và tổ tiên của nó,
sắp theo `sort_order`. Nút MENU khai báo ở `_menu.yaml` (`type: MENU`, `parent`, `sort`), chức năng có entity có
`url = /pages/<FID>.html` (model.py dòng ~343).

### T1.1 Cấu hình layout trong spec
- Thêm vào `spec/_project.yaml`:
  ```yaml
  ui:
    layout: vertical-floating      # vertical-floating | vertical-transparent
    theme: light                   # light | dark
    brand: DevHub
  ```
- `model.py`: đọc + validate (`layout` thuộc 2 giá trị trên, mặc định `vertical-floating`), đưa vào IR `project.ui`.
  Cập nhật `schema/` nếu có schema cho `_project.yaml`.
- Ý nghĩa:
  - **vertical-floating**: sidebar dọc cố định bên trái; navbar trên cùng **tách khỏi mép** (margin, bo góc, đổ bóng,
    sticky); nội dung là các card trên nền xám nhạt.
  - **vertical-transparent**: sidebar dọc như trên; navbar **trong suốt**, hoà nền, không viền/bóng; khi cuộn thì
    thêm nền mờ (`backdrop-filter: blur`) để chữ vẫn đọc được.
  - Cả hai: ≥ 992px sidebar mở; < 992px sidebar thành off-canvas, nút ☰ trên navbar.
- Đổi layout = sửa 1 dòng spec → sinh lại, không sửa JS.

### T1.2 `core/js/shell.js` (mới, SDK chung, viết tay)
Export `renderShell(root, { layout, theme, brand })`:
1. Chưa có token → `renderLogin` (giữ nguyên `data-form="login"`), đăng nhập xong dựng shell.
2. Gọi `core.menu()` → dựng **sidebar đệ quy, không giới hạn cấp**:
   - Nút có `children` → nhóm thu/mở được (cấp 1 là tiêu đề nhóm, cấp ≥2 thụt lề theo cấp).
   - Nút có `url` → mục bấm được. Nút không có `url` và không có con thì bỏ.
   - Thuộc tính test: `data-menu="<FID>"` trên mọi nút, `data-level="<n>"`, `aria-expanded` trên nhóm,
     `aria-current="page"` trên mục đang mở.
   - Hiển thị `function_name`; mã `FID` hiện mờ nhỏ bên cạnh (tooltip). Icon: nếu nút có `icon` (T1.4) thì dùng.
   - Ô lọc menu ở đầu sidebar (`data-action="menu-filter"`): lọc theo tên/mã đã bỏ dấu, giữ tổ tiên của mục khớp.
   - Nhớ nhóm đang mở trong `localStorage` (bọc try/catch).
3. **Router theo hash**: `#/ATA0_0110` → `import('/js/api/ATA0_0110.js')` → `renderCrudPage(contentEl, mod.ATA0_0110)`.
   - Đổi hash → xoá nội dung cũ, dựng lại; mở sẵn các nhóm tổ tiên; cập nhật `document.title`.
   - Breadcrumb trên đầu nội dung theo đường đi trong cây: `Hệ thống ATM › Quản lý ATM › ATA0_0110 · Thiết bị ATM`
     (`data-breadcrumb`).
   - Hash rỗng → trang chào (tên user, tenant, danh sách chức năng gần đây nếu muốn).
   - FID không có trong menu (không quyền) → thông báo `E_FORBIDDEN`, không import.
   - Lỗi 401 bất kỳ lúc nào → về màn đăng nhập, đăng nhập lại thì quay về đúng hash.
4. Navbar: nút ☰ (`data-action="sidebar-toggle"`), tên chức năng hiện tại, user + tenant, nút đăng xuất
   (`data-action="logout"`: xoá token, về login).
5. Không sửa hành vi `renderCrudPage`; nếu cần container khác thì thêm tham số tuỳ chọn, mặc định như cũ.

### T1.3 Template
- `targets/html/templates/index.html.j2` → shell: nạp CSS, `<div id="app" class="layout-{{ project.ui.layout }}">`,
  gọi `renderShell(app, {{ project.ui | tojson }})`.
- `page.html.j2` (`/pages/<FID>.html`): **giữ** để link cũ/bookmark không gãy, nhưng chỉ redirect
  `location.replace('/index.html#/<FID>')`.
- `core/js/shell.js` và CSS layout phải được copy vào app như `core.js`/`page.js` (xem khai báo copy trong
  `targets/html/target.yaml` / `targets/java-spring` — nguồn `repo:` copy trước).

### T1.4 Icon menu (tuỳ chọn, nhỏ)
- Cho phép `icon:` (tên icon Tabler, vd. `building-bank`) trong `functions` của `_menu.yaml`/spec chức năng.
- `model.py` validate dạng `^[a-z0-9-]+$`; DDL: thêm cột `icon` vào `zz.function` (sửa `_core.yaml` — **việc này cần
  người duyệt**, ghi rõ trong PR); `core.functions` + `/menu` trả thêm `icon`. Không có icon → chấm tròn mặc định.
- Nếu không muốn đụng core DB, bỏ qua T1.4.

### T1.5 CSS
- File `core/css/layout.css` (viết tay, ~200 dòng) trên nền Tabler: biến CSS cho độ rộng sidebar (260px), bo góc,
  bóng; class `.layout-vertical-floating`, `.layout-vertical-transparent`, `[data-theme=dark]`.
- **Vendor Tabler** (css + icons webfont) vào `core/static/vendor/` thay vì CDN — để chạy offline và test local
  không lỗi tải. Ghi version trong tên thư mục.

### T1.6 Test
- `core/tests/ui/run_ui.py`: chuyển sang đi qua shell:
  đăng nhập ở `/index.html` → chụp `00-shell.png` → với mỗi chức năng: mở bằng cách **bấm menu**
  (`[data-menu=<FID>]`, mở các nhóm cha trước) → kiểm `aria-current`, breadcrumb → chạy tiếp các bước CRUD hiện có
  (selector `data-*` giữ nguyên, chỉ scope vào vùng nội dung).
- Thêm kiểm: user `viewer1` (chỉ R) thấy menu nhưng không có nút tạo/sửa/xoá *(nếu page.js chưa ẩn theo `right_mask`
  thì thêm vào: ẩn nút theo quyền W/D — đây là sửa nhỏ ở page.js, giữ `data-action`)*; tenant `T2` thấy codemap riêng.
- Chụp cả 2 layout: chạy `run_ui.py` thêm 1 lượt rút gọn với `layout=vertical-transparent` (biến môi trường
  `UI_LAYOUT`, generator đọc đè) — chỉ cần ảnh shell + 1 chức năng.
- Mở `#/KHONG_TON_TAI` → thấy thông báo, không lỗi console.

**Xong khi:** CI xanh 2 DB; comment ảnh trên PR có ảnh shell của cả 2 layout, menu đủ cấp
`Hệ thống ATM › Quản lý ATM › ATA0_0110/0120/0131`; không còn link "← Menu".

---

## T2. Agent nhỏ viết thân hook nghiệp vụ

Hiện `scripts/ai_issue.py` tạo spec + **stub** hook (`ATA0_0121_hookImpl`, `ATA0_0131_hookImpl` chỉ có TODO).
Mục tiêu: agent nhỏ viết được hook kiểu `validateDevice`/`validateContractDates` (xem `ATA0_0110_hookImpl.java`,
`ATA0_0120_hookImpl.java` làm mẫu).

1. Spec: cho phép mô tả luật bằng văn bản + ví dụ test trong `hooks`:
   ```yaml
   hooks:
     - name: validateActualDate
       on: [create, update]
       rule: "Ngày thực hiện không được trước ngày dự kiến"
       tests:
         - {input: {plan_date: 2026-05-10, actual_date: 2026-05-09}, error: {field: actual_date, code: E_RULE}}
         - {input: {plan_date: 2026-05-10, actual_date: 2026-05-10}, ok: true}
   ```
2. Generator sinh test HTTP từ `tests` của hook (đưa vào `run_all.py` qua IR).
3. `scripts/ai_hook.py`: dựng prompt gồm interface hook (sinh ra), 2 hook mẫu, danh sách field + kiểu, luật, test →
   model sinh **chỉ thân method** → chèn vào `custom/.../<FID>_hookImpl.java` → `mvn -q compile` + chạy test hook;
   sai thì gửi lỗi compile/test cho model sửa, tối đa 3 vòng; vẫn sai → giữ stub, ghi lý do vào PR.
4. Chặn: chỉ dùng `Errors`, `Conv`, `P`, `java.time`; cấm SQL/IO/reflection (guard kiểm bằng regex import + từ khoá).
5. Làm thật cho `ATA0_0131.validateActualDate`.

**Xong khi:** issue mới có luật → PR có hook đã viết, test hook xanh.

## T3. Issue "change/bug" sửa được spec (không chỉ phân tích)

Hiện `ai_issue.py` với loại change/bug chỉ in phân tích ảnh hưởng. Bổ sung: model trích **thay đổi dạng patch nhỏ**
(thêm/xoá/sửa field, đổi `length`/`required`/`pattern`/`search`, thêm lookup) theo schema JSON hẹp → áp vào YAML
(giữ comment, dùng `ruamel.yaml` nếu cần, pin version) → validate → pipeline → PR kèm bảng ảnh hưởng.
Cấm đổi pk, xoá entity, sửa `_core.yaml`.

## T4. Bảng "ý trong issue ↔ trường sinh ra" trong comment AI

Trong comment PR/issue của `ai_issue.py`: bảng mỗi câu/ý của issue → field/hook/relation tương ứng, ý không khớp ghi
"⚠️ chưa xử lý". Dùng `codegen/ai.py` (`tokens`, bỏ dấu) để ghép — tất định, không cần model.

## T5. Dọn

- PR #10 (Laya eval): chờ chủ repo quyết; không dùng Laya trong pipeline chính (ghép ref 65% < luật tất định 100%).
- README: cập nhật mục giao diện (shell, layout, menu) sau T1.

---

## Ghi chú khi làm

- Commit nhỏ, message tiếng Việt, mô tả "vì sao".
- Không push thẳng `main`; mở PR, đợi CI 2 DB.
- Nếu một yêu cầu trong file này mâu thuẫn với code hiện tại, **ưu tiên giữ test đang xanh** và ghi lại trong PR.
- Khi không chắc về quyết định kiến trúc (sửa core DB, đổi hợp đồng API) → dừng, ghi câu hỏi trong PR.
