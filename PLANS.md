# PLANS v2 — Lộ trình Spec-Driven, chia theo agent nhỏ

> Bản này **thay** PLANS v1 (T1–T4 đã xong qua PR #11–#15).
> Nền: tài liệu "CodeGen — Lộ trình mở rộng Spec-Driven" (20/11/2026, 5 giai đoạn, PR-16…PR-21) — **đã duyệt có
> điều chỉnh**, các điều chỉnh ghi ở mục 2. Khi tài liệu đó và file này lệch nhau, **theo file này**.
>
> Làm tuần tự từng PR. Mỗi PR một nhánh, CI `codegen.yml` xanh cả PostgreSQL và MySQL mới tính xong.
> Commit/PR/comment tiếng Việt, commit nhỏ, ghi "vì sao". Quyết định đụng hợp đồng core hoặc `_core.yaml` → dừng, hỏi trong PR.

---

## 1. Nguyên tắc số 1: mỗi việc AI = một agent nhỏ, hẹp, kiểm được

Model là Qwen3-1.7B chạy CPU. Nó chỉ làm tốt khi: **đầu vào ngắn, đầu ra là JSON schema hẹp, giá trị chọn trong danh
sách có sẵn, và có bộ kiểm tất định phía sau**. Vì vậy mọi tính năng mới trong lộ trình phải đi kèm **một agent riêng**
(nếu cần AI), không nhồi thêm việc vào agent cũ.

### 1.1 Hợp đồng chung của một agent

```
agents/<tên>/
  agent.yaml        # tên, mô tả, đầu vào, max_tries (≤3), model, nhiệt độ, ngân sách token
  prompt.md         # system prompt (tiếng Việt, kết thúc /no_think)
  fewshot.yaml      # 2–4 ví dụ thật, ngắn
  schema.py         # build_schema(ir, ctx) -> JSON schema ĐỘNG: enum lấy từ IR/registry (field có thật, codemap có thật…)
  apply.py          # apply(result, repo) -> danh sách file đã sửa (TẤT ĐỊNH, không gọi model)
  check.py          # check(repo) -> [lỗi]  (validate, guard, compile, test hẹp) — lỗi được gửi lại model ở vòng sau
eval/<tên>/cases.yaml   # ≥10 case: input → kỳ vọng; chạy đêm, báo % đúng
```

Một runner chung `scripts/agents/run.py <tên> --input ...` lo: dựng context (`generator.py context`), gọi model
(llama-cpp / `OLLAMA_URL`), ép `response_format` theo schema, vòng sửa ≤ `max_tries`, ghi log
"model trích …", trả JSON kết quả + danh sách file đổi + lý do thất bại. **Agent không tự gọi model, không tự ghi file
ngoài `apply.py`, không tự chạy pipeline.**

Quy tắc phân vai:
- **Model chỉ trích/chọn**, không bao giờ viết YAML/SQL/JS trực tiếp. Riêng agent `hook` được viết thân method Java,
  đã có guard.
- **Phần tất định làm trước, model làm phần còn lại.** Ví dụ agent UI: luật tất định đề xuất component mặc định theo kiểu
  field; model chỉ gom section/đổi thứ tự/đặt nhãn.
- **Agent không đủ chắc thì nói "không làm"**: mỗi schema có nhánh `{"skip": "lý do"}`; ghi vào PR, không đoán bừa.
- **Mỗi agent tối đa một commit** trong PR, message dạng `agent:<tên> — <tóm tắt>`, để dễ revert riêng.

### 1.2 Danh sách agent (hiện có → sẽ có)

| Agent | Việc | Đầu ra model (hẹp) | Kiểm tất định | Có từ |
|---|---|---|---|---|
| `router` | Phân loại issue → cần chạy agent nào | `{agents:[spec|change|hook|command|ui], fid?}` enum | FID tồn tại; tổ hợp hợp lệ | **PR-16a (mới)** |
| `spec` | Chức năng mới → danh sách field | field list (ai_spec hiện tại) | validate + example | có (ai_spec) |
| `change` | Sửa/lỗi → patch nhỏ lên spec | `ops[]` (ai_change hiện tại) | validate, cấm đổi pk | có (ai_change) |
| `hook` | Luật + test → thân method Java | `{code}` | guard + mvn compile + test hook | có (ai_hook) |
| `command` | Mô tả hành động → command | `{id,label,position,set_fields,require,confirm}` enum từ field/codemap | validate + test sinh tự động | **PR-18** |
| `ui` | Bố cục form/list theo registry | `{sections[], components{}}` tên component enum từ registry | validate registry + test UI custom | **PR-19** |
| `fix` | CI đỏ → sửa đúng chỗ | patch như `change`, chỉ trên spec/hook AI vừa tạo | chạy lại bước pipeline đã đỏ | **PR-21b (tuỳ chọn)** |

`router` là bài phân loại nhãn cố định — đây là chỗ hợp với Laya (PR #10) nếu sau này muốn: chạy song song luật từ khoá,
so trên `eval/router/cases.yaml`, chỉ thay khi thắng rõ.

`ai_issue.py` thành **điều phối viên mỏng**: router → chạy từng agent theo thứ tự cố định
`spec → change → command → ui → hook` → pipeline → PR + comment (bảng ánh xạ ý ↔ thứ sinh ra, ảnh giao diện,
agent nào skip và vì sao).

---

## 2. Điều chỉnh so với tài liệu lộ trình

| # | Tài liệu đề xuất | Điều chỉnh | Lý do |
|---|---|---|---|
| A | GĐ1 fingerprint theo **file** spec của chức năng | Fingerprint theo **lát IR** của chức năng + chức năng phụ thuộc (dùng `impact`) | Đổi `ATA0_0110` (thêm field, đổi `device_name`) làm đổi lookup/JOIN của `ATA0_0120`, `0131` dù file của chúng không đổi. Hash theo file sẽ bỏ sót → cache stale (R1). |
| B | GĐ1 `build --changed-only` ghi tăng vào `out/` | **Bỏ.** Luôn render full (vài giây). Cache chỉ dùng để **quyết định bỏ qua bước nặng** (mvn, catalog, test chọn lọc) | Render không phải chỗ chậm; ghi tăng sinh ra cả lớp rủi ro stale + test byte-diff phức tạp mà không lợi gì. |
| C | GĐ1 test byte-diff toàn `out/` để chứng minh tương thích ngược | Giữ, nhưng dùng cho **mục đích khác**: script `scripts/outdiff.py base..head` so `out/` của nhánh base và PR, liệt kê file đổi — dùng ở PR-18/19 để chứng minh spec cũ sinh y hệt | Khi không còn ghi tăng thì byte-diff chính là bằng chứng "không phá cái cũ". |
| D | GĐ2 bảng shadow `zz.sync_state` "không đụng `_core.yaml`" | Bảng nào trong schema `zz` cũng phải khai ở `_core.yaml` (DDL sinh từ đó). Vẫn chọn shadow table (Q1-a) nhưng **thêm vào `_core.yaml` trong PR riêng nhỏ, chờ duyệt** | Không có đường tắt; tách PR nhỏ để duyệt nhanh. |
| E | GĐ2 "đường ghi menu/codemap từ giao diện nếu chưa có thì bổ sung kèm" | **Ra khỏi PR-17.** PR-17 chỉ làm sync + API core tối thiểu `PUT /api/v1/admin/codemap/...` để test đánh dấu override. Màn hình quản trị menu/codemap làm sau, **sinh bằng chính CodeGen** (module ZZ) | Giữ PR-17 nhỏ; màn quản trị là dogfooding tốt cho GĐ3–4. |
| F | GĐ4 "spec cũ không có `ui` → out/ byte-identical" | Byte-identical áp cho **file sinh từ spec** (`api/*.js` meta, trang). `core/js/*` được phép cải thiện chế độ `auto` (vd. codemap hiện badge + nhãn thay vì mã thô, ngày dd/MM/yyyy) miễn giữ hợp đồng `data-*` | Hợp đồng là DOM/`data-*`, không phải pixel. Cải thiện auto có lợi cho mọi chức năng mà không cần AI. |
| G | Thứ tự PR-16 → 21 | Thêm **PR-16a Agent kit** trước PR-17; PR-18/19 mỗi cái kèm agent của nó | Mục tiêu hiện tại là hoàn thiện agent nhỏ; mỗi tính năng spec mới phải có agent dùng được ngay. |

Chốt Q1–Q6 (mặc định nếu chủ repo không nói khác): **Q1-a** (shadow table, PR riêng), **Q2-a** (X=8 = quyền chạy
command), **Q3-a** (`commands`, giữ `actions`), **Q4-a** (PR chạy full, đổi sau khi có số liệu), **Q5** auto mặc định /
override luôn giữ + báo drift / dòng file biến mất: codemap → `status=I`, function → xoá, **Q6-a** (hoãn P4c).
Q2 và Q3 là hợp đồng — ghi vào README mục "Hợp đồng core" trong PR-18.

---

## 3. Trình tự PR

```
PR-16  build-cache (đo + changes)     ──┐
PR-16a agent kit + router              ──┼─▶ PR-17 sync YML→DB ─▶ PR-18 commands + agent command
                                         │                       ─▶ PR-19 UI P4a + agent ui ─▶ PR-20 UI P4b
                                         └──────────────────────────────────────────────────▶ PR-21 docs/DX (+21b agent fix)
```
PR-16 và PR-16a độc lập, làm song song được.

---

### PR-16 `feat/build-cache` — đo và biết "cái gì đổi" (2 ngày)

1. **Đo baseline trước khi code**: chạy pipeline 2 DB, ghi thời gian từng bước (sinh, mvn, DB, catalog, test API, test
   UI) vào `docs/metrics.md`. Thêm in thời gian từng bước trong `pipeline.sh` (`::group::` + `SECONDS`).
2. `codegen/fingerprint.py`:
   - `G` = sha256 của `schema/**`, `spec/_project.yaml`, `spec/ZZ/A0/_core.yaml`, `codegen/**`, `targets/**`, `core/**`,
     `requirements*.txt`.
   - `fp(fid)` = sha256 của JSON chuẩn hoá (sort_keys) **lát IR**: function + entity + relations + lookup_fields +
     codemap nhóm nó dùng + testdata của entity + hooks/tests.
   - Phụ thuộc: tập FID bị ảnh hưởng = FID đổi ∪ `impact(fid)` (cha/con/lookup).
3. CLI `generator.py changes [--base <ref>|--state .cache/build-state.json] [--json]` → bảng
   `FID | trạng thái (mới/đổi/xoá/giữ) | lý do (file nào, phụ thuộc gì)`; `G` đổi → "ALL".
   `generator.py clear-cache`.
4. `pipeline.sh`: sau bước xanh, ghi `.cache/build-state.json` (G, fp từng FID, sha của `out/app/**`).
   **Mức B (i) duy nhất bật ở PR này:** bỏ `mvn package` khi sha `out/app/**` + `core/java/**` trùng lần xanh trước
   (vẫn chạy app + test). `.cache/` vào `.gitignore`; CI dùng `actions/cache` key `G + sha base`.
5. `scripts/outdiff.py <dirA> <dirB>` → danh sách file khác (dùng cho mục 2-C).
6. Comment PR (mở rộng `publish_ui.py`, cùng 1 comment marker): bảng `changes` + thời gian từng bước.

**Xong khi:** `changes` đúng cho 4 tình huống có test (`tests/test_fingerprint.py`): đổi 0131 → chỉ 0131; đổi field
được lookup của 0110 → 0110, 0120, 0131; đổi `_codemaps.yaml` nhóm STATUS_AI → các FID dùng nhóm đó; đổi
`targets/` → ALL. Baseline có trong PR.

---

### PR-16a `feat/agent-kit` — khung agent chung + router (2–3 ngày)

1. Tạo `scripts/agents/run.py` + `scripts/agents/llm.py` (gom `ask()`/load model/`response_format`/retry đang lặp ở
   `ai_spec.py`, `ai_hook.py`, `ai_change.py`). Giữ nguyên hành vi: cùng model, cùng `/no_think`, portable llama build.
2. Chuyển 3 agent hiện có sang cấu trúc `agents/<tên>/` (mục 1.1) **không đổi kết quả**: chạy `eval/` trước/sau, đính
   kèm số liệu. Giữ `scripts/ai_spec.py`… làm wrapper mỏng gọi runner để workflow cũ không vỡ.
3. Agent `router`: luật từ khoá tất định trước (dùng `codegen/ai.py tokens`), model chỉ khi luật không chắc. Có
   `eval/router/cases.yaml` ≥ 20 case lấy từ issue thật + tự viết.
4. `ai_issue.py` thành điều phối viên (mục 1.2). Comment issue/PR có mục "Agent đã chạy": tên, kết quả, số vòng, skip vì sao.
5. Workflow `agent-eval.yml` (cron đêm + dispatch): chạy `eval/*` mọi agent, ghi bảng % đúng vào job summary.

**Xong khi:** 3 agent cũ qua runner cho kết quả eval không giảm; issue thử loại "new" và "change" vẫn ra PR xanh;
router ≥ 90% trên eval.

---

### PR-17 `feat/yml-db-sync` — không mất dữ liệu runtime (3 ngày)

**PR-17-pre (nhỏ, chờ duyệt):** thêm vào `_core.yaml` bảng
`zz.sync_state(table_name, row_key, source[file|override], file_hash, db_updated_at, is_locked)`, pk
`(table_name, row_key)`, không FK.

1. `codegen/sync.py` (tách lớp lưu trữ để sau đổi sang cột thật chỉ sửa 1 file): sinh SQL sync thay cho
   DELETE/INSERT trong `ddl.py` cho `zz.function`, `zz.function_tree`, `zz.codemap_group`, `zz.codemap`,
   `zz.codemap_label` — chỉ tenant `'*'`. Áp đúng bảng 6 tài liệu + Q5. SQL chuẩn, qua lint sqlglot (không
   `ON CONFLICT` → dùng UPDATE … WHERE / INSERT … SELECT … WHERE NOT EXISTS).
2. `SYNC_CONFIG=auto|manual|off` (off = seed cũ y hệt; so bằng `outdiff`). `manual` → in báo cáo drift
   `out/sql/sync_report.md`, không ghi.
3. Core API tối thiểu (Java, `CoreController` hoặc `AdminController`): `PUT /api/v1/admin/codemap/{group}/{code}`
   (đổi nhãn/thứ tự) và `PUT /api/v1/admin/function/{fid}` (đổi tên/sort) — quyền: chức năng `ZZA0_0200` mới, bit W;
   cùng transaction ghi `sync_state.source=override`.
4. Script backfill một lần: đánh `source=file` cho DB cũ.
5. Test HTTP mới (`core/tests/http/test_sync.py`, chạy trong bước 6): seed → sửa qua API → chạy sync lại → còn nguyên;
   khoá `is_locked` không bị đụng; đổi YML áp lên dòng `file`; `manual` không ghi.

**Xong khi:** test trên xanh 2 DB; `SYNC_CONFIG=off` sinh SQL y hệt main.

---

### PR-18 `feat/commands` — hành động nghiệp vụ + agent `command` (5 ngày)

Theo chương 6 tài liệu (khoá `commands`, thuộc tính bảng 7, `require` chỉ 3 dạng: bằng, `notNull`, `row_version`).
Bổ sung:
1. Route `POST /api/v1/{FID}/commands/{id}`; batch nhận `{ids:[…]}`, **cả lô một transaction, lỗi trả theo
   `ids[i].field`** (giống `payments[0].field`). Kiểm bit X → `E_FORBIDDEN`; require sai → `E_RULE` đúng field;
   ghi `audit_log` action `CMD_<id>`. Sinh vào trx/mod Java, catalog SQL (`cmd.<id>`), OpenAPI, docs, js-sdk
   (`api.cmd.<id>(key|ids)`).
2. `page.js`: nút theo `meta.commands`, `data-action="cmd-<id>"`, batch có checkbox `data-select`; `confirm` dùng hộp
   thoại DOM của trang (không `window.confirm` — test và agent trình duyệt bị chặn bởi dialog native). Ẩn nút khi thiếu X.
3. Test sinh tất định từ spec: happy path, mỗi require vi phạm, viewer thiếu X; UI test bấm `cmd-*` + chụp ảnh.
4. Spec thật: `ATA0_0110.close_device`, `ATA0_0131.close_schedule` (row), `ATA0_0131.reopen_selected` (batch).
5. **Agent `command`**: input = câu mô tả hành động + IR của FID; schema động: `set_fields`/`require` chỉ nhận field có
   thật, giá trị codemap có thật (enum), `position` enum. `apply.py` chèn vào spec bằng ruamel (giữ comment).
   `check.py` = validate + test command của FID. Router nhận diện "nút/hành động/khoá/duyệt/chốt…". ≥ 10 case eval.
6. `outdiff`: spec không có `commands` → file sinh từ spec y hệt main.

---

### PR-19 `feat/ui-components-a` — registry P4a + agent `ui` (3–4 ngày)

Theo chương 7 tài liệu (registry `targets/html/ui-components.yaml` có `version`, `ui.mode: auto|custom`, P4a: sections+
cols, status-badge, select-single, textarea, number-format). Bổ sung:
1. **Auto tốt hơn (mục 2-F)** trong `page.js`: field có codemap → badge nhãn ở bảng; DATE → định dạng VN; DECIMAL →
   phân cách nghìn. Không đổi `data-*`.
2. Renderer: `core/js/components/<tag>.js`, mỗi file một hàm thuần `(field, value, params) → Node`; page.js tra theo tag.
3. `generator.py schema` xuất catalog component từ registry; tài liệu component sinh từ registry.
4. **Agent `ui`**: luật tất định đề xuất trước (codemap → status-badge/select-single, TEXT > 200 → textarea, DECIMAL →
   number-format, pk + field bắt buộc lên section đầu). Model chỉ trả `{sections:[{title, cols, fields}], overrides}`
   với field/component là enum. `check.py` = validate + UI test chế độ custom + chụp ảnh. ≥ 10 case eval.
5. `ATA0_0131` chuyển `ui.mode: custom` như Phụ lục A làm mẫu.

### PR-20 `feat/ui-components-b` — P4b (2 ngày)
date/datetime-picker, checkbox/radio cho BOOL, view-mode card-list. Mở rộng enum của agent `ui`. P4c hoãn (Q6-a).

### PR-21 `docs/dx` — tài liệu và trải nghiệm (3 ngày)
Theo chương 8 tài liệu (README 5 phần, `examples/` 4 mẫu chạy được, CONTRIBUTING, pre-commit, lỗi validate có
`file:dòng` + did-you-mean). Thêm mục **"Viết một agent mới"** theo mục 1.1, kèm checklist.

### PR-21b `feat/agent-fix` (tuỳ chọn) — agent sửa khi CI đỏ
Chỉ chạy trên PR do agent tạo. Input: tên bước đỏ + 60 dòng log cuối + spec/hook AI vừa sinh. Đầu ra: patch như
`change` hoặc thân hook mới. Tối đa 2 lượt trên một PR, sau đó gắn nhãn `needs-human`.

---

## 4. Bất biến (giữ từ PLANS v1 và tài liệu 2.3)

1. Không FOREIGN KEY; quan hệ ở `relations`, engine kiểm.
2. SQL dạng PostgreSQL chuẩn → sqlglot 30.33.0 → MySQL; lint cấm `ON CONFLICT`, `RETURNING`, `ILIKE`, `ANY`, JSON op,
   `LIMIT`, DDL trong catalog, `SELECT *`. Chạy thật trên cả 2 DB.
3. FlowSQL: `:param`, `inTransaction` (không `@Transactional`), key row chữ thường.
4. Hợp đồng core: JWT HS256 (`sub, tenant, units`), R=1 W=2 D=4 X=8 (X = chạy command sau PR-18), lỗi
   `{code, message, details[{field, code, message}]}`, PBKDF2.
5. Hợp đồng `data-*`: `data-action, data-form, data-key, data-total, data-error, data-page, data-menu,
   data-breadcrumb` (+ `data-select`, `cmd-<id>` sau PR-18) — không đổi tên, không bỏ.
6. `render.py` copy nguồn `repo:` trước.
7. `out/` không commit, không sửa tay. AI chỉ chạm `spec/<SYS>/<SUB>/`, `custom/`, hookImpl — qua `apply.py`.
8. Mở rộng schema ⇒ cập nhật cùng lúc `generator.py schema`, schema động của agent liên quan, tài liệu, `eval/`.
9. Không thêm phụ thuộc nặng (torch…) vào CI chính; agent chạy CPU, model ≤ 2B.

## 5. KPI (theo tài liệu bảng 10, thêm 2 dòng cho agent)

| KPI | Mục tiêu |
|---|---|
| K1–K5 | như tài liệu |
| K6 — độ đúng từng agent trên `eval/` | router ≥ 90%, spec/change/command ≥ 80%, ui ≥ 80%, hook: test xanh ≥ 70% |
| K7 — issue → PR xanh không cần người sửa | đo hằng tuần trong `docs/metrics.md`, mục tiêu tăng dần qua từng PR |
