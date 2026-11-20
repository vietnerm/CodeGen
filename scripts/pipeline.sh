#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Pipeline đầy đủ: spec → sinh → guard → DB → kiểm SQL → build → chạy app → test HTTP → toàn vẹn
# Chạy giống nhau ở máy dev và CI.
#
#   DB_TYPE=postgresql DB_HOST=localhost DB_PORT=5432 DB_NAME=app DB_USER=app DB_PASS=app \
#   APP_JWT_SECRET=$(openssl rand -hex 32) bash scripts/pipeline.sh
#
# Biến tuỳ chọn: PORT (8080) · SKIP_BUILD=1 (bỏ mvn, dùng jar có sẵn) · SKIP_APP=1 (dừng sau bước SQL)
#                KEEP_RUNNING=1 (không tắt app sau test)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DB_TYPE:=postgresql}" "${DB_HOST:=localhost}" "${DB_NAME:=app}" "${DB_USER:=app}" "${DB_PASS:=app}"
: "${PORT:=8080}"
if [ "$DB_TYPE" = postgresql ]; then : "${DB_PORT:=5432}"; else : "${DB_PORT:=3306}"; fi
: "${APP_JWT_SECRET:?Cần APP_JWT_SECRET (≥ 32 ký tự)}"
export DB_TYPE DB_HOST DB_PORT DB_NAME DB_USER DB_PASS PORT APP_JWT_SECRET

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

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

step "1. Kiểm tra + sinh từ spec"
python generator.py build

step "2. Guard: code viết tay không vượt chuẩn"
python scripts/guard.py

step "3. Dựng DB ($DB_TYPE): schema → seed → dữ liệu test"
for f in 00_schema 10_seed 90_testdata; do echo "  · $f"; run_sql "out/sql/$DB_TYPE/$f.sql"; done
integrity

step "4. Chạy thật mọi câu SQL trong catalog"
if [ "$DB_TYPE" = postgresql ]; then DSN="host=$DB_HOST port=$DB_PORT dbname=$DB_NAME user=$DB_USER password=$DB_PASS"
else DSN="host=$DB_HOST;port=$DB_PORT;user=$DB_USER;password=$DB_PASS;db=$DB_NAME"; fi
python scripts/catalog_check.py --dialect "$DB_TYPE" --dsn "$DSN"

if [ "${SKIP_APP:-0}" = 1 ]; then echo -e "\n✓ ĐẠT tới bước 4 (SKIP_APP=1)"; exit 0; fi

if [ "${SKIP_BUILD:-0}" != 1 ]; then
  step "5. Build core SDK + app"
  mvn -B -q -f core/java/pom.xml install -DskipTests
  mvn -B -q -f out/app/pom.xml package -DskipTests
fi

step "6. Chạy app + test HTTP (core contract + CRUD + hook)"
mkdir -p out/logs
java -jar out/app/target/app.jar > out/logs/app.log 2>&1 &
APP_PID=$!
trap '[ "${KEEP_RUNNING:-0}" = 1 ] || kill $APP_PID 2>/dev/null || true' EXIT
if ! BASE_URL="http://localhost:$PORT" python out/tests/http/run_all.py; then
  echo "── 80 dòng cuối app.log ──"; tail -80 out/logs/app.log; exit 1
fi

step "7. Toàn vẹn dữ liệu sau test"
integrity

echo -e "\n✓ PIPELINE ĐẠT ($DB_TYPE) — app: http://localhost:$PORT/index.html · API: /openapi/openapi.yaml"
