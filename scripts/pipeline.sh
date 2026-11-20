#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Pipeline đầy đủ: spec → sinh → guard → DB → kiểm SQL → build → chạy app → test HTTP → toàn vẹn
# Chạy giống nhau ở máy dev và CI.
#
#   DB_TYPE=postgresql DB_HOST=localhost DB_PORT=5432 DB_NAME=app DB_USER=app DB_PASS=app \
#   APP_JWT_SECRET=$(openssl rand -hex 32) bash scripts/pipeline.sh
#
# Biến tuỳ chọn: PORT (8080) · SKIP_BUILD=1 (bỏ mvn, dùng jar có sẵn) · SKIP_APP=1 (dừng sau bước SQL)
#                SKIP_UI=1 (bỏ test giao diện; mặc định chạy nếu đã cài playwright)
#                KEEP_RUNNING=1 (không tắt app sau test)
#
# PR-16 (build-cache): mỗi bước in thời gian (SECONDS, gộp log bằng ::group:: khi chạy CI)
# và ghi out/logs/steps.tsv — số liệu cho docs/metrics.md và comment PR. Sau khi XANH,
# bước 8 ghi .cache/build-state.json (G, dấu vân tay từng FID, sha nguồn Java) + chép jar
# vào .cache/ để lần sau bỏ qua `mvn` khi nguồn Java sinh ra + core/java y hệt lần xanh
# trước (kiểm bằng sha, vẫn chạy app + test — không bao giờ dùng jar của nguồn khác).
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DB_TYPE:=postgresql}" "${DB_HOST:=localhost}" "${DB_NAME:=app}" "${DB_USER:=app}" "${DB_PASS:=app}"
: "${PORT:=8080}"
if [ "$DB_TYPE" = postgresql ]; then : "${DB_PORT:=5432}"; else : "${DB_PORT:=3306}"; fi
: "${APP_JWT_SECRET:?Cần APP_JWT_SECRET (≥ 32 ký tự)}"
export DB_TYPE DB_HOST DB_PORT DB_NAME DB_USER DB_PASS PORT APP_JWT_SECRET

TIMING_TSV="out/logs/steps.tsv"     # <tên bước>\t<số giây> — nguồn cho metrics + comment PR
CUR_STEP=""; STEP_T0=0

begin() {   # $1 = tên bước: in tiêu đề, mở group log CI, bắt đầu bấm giờ
  CUR_STEP="$1"; STEP_T0=$SECONDS
  printf '\n\033[1m▶ %s\033[0m\n' "$1"
  if [ "${CI:-}" = true ]; then printf '::group::%s\n' "$1"; fi
}

end() {     # ghi thời gian bước vừa xong (vì sao: đo baseline PR-16, không cần đo tay)
  local d=$(( SECONDS - STEP_T0 ))
  printf '⏱ %s — %ss\n' "$CUR_STEP" "$d"
  mkdir -p out/logs
  printf '%s\t%s\n' "$CUR_STEP" "$d" >> "$TIMING_TSV"
  if [ "${CI:-}" = true ]; then printf '::endgroup::\n'; fi
  CUR_STEP=""
}

restore_jar() {   # jar nằm ngoài out/ nên còn nguyên sau khi sinh lại out/
  mkdir -p out/app/target
  cp .cache/app.jar out/app/target/app.jar
}

run_sql() {   # $1 = file
  if [ "$DB_TYPE" = postgresql ]; then
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q -f "$1"
  else
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" --default-character-set=utf8mb4 "$DB_NAME" < "$1"
  fi
}

query_sql() { # in kết quả không header
  if [ "$DB_TYPE" = postgresql ]; then
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -At -f "$1"
  else
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -N "$DB_NAME" < "$1"
  fi
}

integrity() {
  local out
  out=$(query_sql "out/sql/$DB_TYPE/99_integrity.sql")
  if [ -n "$out" ]; then echo "✗ dữ liệu không toàn vẹn:"; echo "$out"; return 1; fi
  echo "✓ toàn vẹn dữ liệu: sạch"
}

# mvn chỉ chạy khi nguồn Java (sinh ra + core viết tay) khác lần xanh trước.
# Vì sao: mvn là bước chậm nhất; sinh/đổi HTML hay SQL không ảnh hưởng gì tới jar.
maybe_build() {  # $1 = "đầy đủ" (core SDK + app) | "chỉ app" (dùng sau khi sinh lại out/ ở 6c)
  local mode="$1" out_line dec why
  out_line=$(python generator.py skip-build)
  dec=${out_line%%$'\t'*}
  why=${out_line#*$'\t'}
  if [ "$dec" = skip ]; then
    echo "· bỏ qua mvn — $why"
    restore_jar
    return 0
  fi
  echo "· mvn: $why"
  if [ "$mode" = "đầy đủ" ]; then
    mvn -B -q -f core/java/pom.xml install -DskipTests
  fi
  mvn -B -q -f out/app/pom.xml package -DskipTests
}

begin "1. Kiểm tra + sinh từ spec"
python generator.py build
end

begin "2. Guard: code viết tay không vượt chuẩn"
python scripts/guard.py
end

begin "3. Dựng DB ($DB_TYPE): schema → seed → dữ liệu test"
for f in 00_schema 10_seed 90_testdata; do echo "  · $f"; run_sql "out/sql/$DB_TYPE/$f.sql"; done
integrity
end

begin "4. Chạy thật mọi câu SQL trong catalog"
if [ "$DB_TYPE" = postgresql ]; then DSN="host=$DB_HOST port=$DB_PORT dbname=$DB_NAME user=$DB_USER password=$DB_PASS"
else DSN="host=$DB_HOST;port=$DB_PORT;user=$DB_USER;password=$DB_PASS;db=$DB_NAME"; fi
python scripts/catalog_check.py --dialect "$DB_TYPE" --dsn "$DSN"
end

if [ "${SKIP_APP:-0}" = 1 ]; then echo -e "\n✓ ĐẠT tới bước 4 (SKIP_APP=1)"; exit 0; fi

if [ "${SKIP_BUILD:-0}" != 1 ]; then
  begin "5. Build core SDK + app"
  maybe_build "đầy đủ"
  end
else
  echo "(SKIP_BUILD=1 — dùng jar có sẵn)"
fi

begin "6. Chạy app + test HTTP (core contract + CRUD + hook)"
mkdir -p out/logs
java -jar out/app/target/app.jar > out/logs/app.log 2>&1 &
APP_PID=$!
trap '[ "${KEEP_RUNNING:-0}" = 1 ] || kill $APP_PID 2>/dev/null || true' EXIT
if ! BASE_URL="http://localhost:$PORT" python out/tests/http/run_all.py; then
  echo "── 80 dòng cuối app.log ──"; tail -80 out/logs/app.log; exit 1
fi
end

if [ "${SKIP_UI:-0}" != 1 ] && python -c "import playwright" 2>/dev/null; then
  begin "6b. Test giao diện (Playwright) + chụp màn hình → out/ui/"
  run_sql "out/sql/$DB_TYPE/90_testdata.sql"     # dữ liệu sạch: không dùng lại bản ghi test API để lại
  if ! BASE_URL="http://localhost:$PORT" python out/tests/ui/run_ui.py; then
    echo "── xem ảnh trong out/ui/ ──"; cat out/ui/report.md 2>/dev/null | head -60; exit 1
  fi
  end

  # 6c. Lượt rút gọn cho LAYOUT THỨ HAI: UI_LAYOUT đè ui.layout khi sinh lại (chỉ PostgreSQL —
  # publish ảnh vào PR chạy ở matrix postgresql, tránh tốn thời gian 2 DB cho cùng 1 ảnh)
  if [ "$DB_TYPE" = postgresql ]; then
    begin "6c. Test giao diện layout thứ hai (UI_LAYOUT=vertical-transparent, rút gọn)"
    kill $APP_PID 2>/dev/null || true; wait $APP_PID 2>/dev/null || true
    KEEP_UI="${TMPDIR:-/tmp}/ui.keep"             # generator build xoá lại out/ — giữ ảnh layout 1 NGOÀI out/
    rm -rf "$KEEP_UI"; cp -r out/ui "$KEEP_UI"
    UI_LAYOUT=vertical-transparent python generator.py build > /dev/null
    rm -rf out/ui; mv "$KEEP_UI" out/ui
    mkdir -p out/logs
    maybe_build "chỉ app"                          # Java không đọc ui.layout → thường được bỏ qua
    java -jar out/app/target/app.jar > out/logs/app-layout2.log 2>&1 &
    APP_PID=$!
    if ! BASE_URL="http://localhost:$PORT" UI_OUT=out/ui2 python out/tests/ui/run_ui.py --quick; then
      echo "── xem ảnh layout 2 trong out/ui2/ ──"; cat out/ui2/report.md 2>/dev/null | head -40; exit 1
    fi
    python scripts/merge_ui2.py layout-vertical-transparent
    end
  fi
else
  echo "(bỏ qua test giao diện: SKIP_UI=1 hoặc chưa cài playwright)"
fi

begin "7. Toàn vẹn dữ liệu sau test"
integrity
end

begin "8. Ghi state build xanh (.cache) cho lần chạy sau"
python generator.py save-state
if [ -f out/app/target/app.jar ]; then cp out/app/target/app.jar .cache/app.jar; fi
end

echo -e "\n✓ PIPELINE ĐẠT ($DB_TYPE) — app: http://localhost:$PORT/index.html · API: /openapi/openapi.yaml"
