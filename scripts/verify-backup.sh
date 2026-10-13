#!/usr/bin/env bash
# Prova di ripristino (cron, domenica 05:00): un backup mai ripristinato non
# è una garanzia. Ripristina l'ultima copia di scripts/backup.sh in un
# database usa e getta, controlla che abbia le stesse tabelle del database
# vero e righe nelle tabelle principali, poi lo cancella. Non tocca mai il
# database vero. Se la prova fallisce lo staff riceve una notifica.
# Usage: scripts/verify-backup.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
BACKUP_DIR="./backups"

# shellcheck disable=SC1091
[ -f .env ] && source .env
PG_USER="${POSTGRES_USER:-jav}"
LIVE_DB="${POSTGRES_DB:-jav}"
TEST_DB="${LIVE_DB}_backup_check"

psql_in() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U "$PG_USER" -v ON_ERROR_STOP=1 -At -d "$1" -c "$2"
}
cleanup() {
  psql_in postgres "DROP DATABASE IF EXISTS $TEST_DB" >/dev/null 2>&1 || true
}
fail() {
  echo "!! Prova di ripristino FALLITA: $1" >&2
  ./scripts/notify-staff.sh "$ENV" "Prova del backup non riuscita" "$1 Vedi backups/backup.log sul server."
  cleanup
  exit 1
}
trap 'fail "Errore durante il ripristino di prova."' ERR

LATEST="$(find "$BACKUP_DIR" -maxdepth 1 -name "jav_${ENV}_*.sql.gz" | sort | tail -1)"
[ -n "$LATEST" ] || fail "Nessun backup del database trovato."
# Più vecchio di due giorni: il backup notturno non sta girando.
[ -n "$(find "$LATEST" -mmin -2880)" ] || fail "L'ultimo backup ($LATEST) ha più di due giorni."

echo "==> Restoring $LATEST into $TEST_DB"
cleanup
psql_in postgres "CREATE DATABASE $TEST_DB" >/dev/null
gunzip -c "$LATEST" | docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "$PG_USER" -v ON_ERROR_STOP=1 -q -d "$TEST_DB" >/dev/null

TABLES_SQL="select count(*) from information_schema.tables where table_schema = 'public'"
LIVE_TABLES="$(psql_in "$LIVE_DB" "$TABLES_SQL")"
TEST_TABLES="$(psql_in "$TEST_DB" "$TABLES_SQL")"
[ "$LIVE_TABLES" = "$TEST_TABLES" ] || fail "Il backup ha $TEST_TABLES tabelle, il database vero $LIVE_TABLES."
for table in organizations users wallets alembic_version; do
  rows="$(psql_in "$TEST_DB" "select count(*) from $table")"
  [ "$rows" -gt 0 ] || fail "Nel backup la tabella $table è vuota."
done
USERS_LIVE="$(psql_in "$LIVE_DB" "select count(*) from users")"
USERS_TEST="$(psql_in "$TEST_DB" "select count(*) from users")"

cleanup
echo "==> Restore OK: $TEST_TABLES tables, $USERS_TEST users in the backup ($USERS_LIVE now)"
