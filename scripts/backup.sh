#!/usr/bin/env bash
# Il backup notturno (cron, 04:00 -- vedi `crontab -l`), sullo stesso disco
# del server. Salva l'essenziale che GitHub non ha (scelta dell'utente,
# Session 89: niente copia fuori dal server, niente file caricati):
#
# 1. il database -- pg_dump compresso in ./backups/, con rotazione: tutto
#    degli ultimi 7 giorni, poi uno a settimana fino a 5 settimane, poi uno
#    al mese fino a 6 mesi (~17 copie da ~20 MB invece di una al giorno);
# 2. il file .env (chiavi Stripe, email, password) -- in ./backups/env/,
#    una copia solo quando cambia, leggibile solo da root.
#
# Protegge da errori, cancellazioni e aggiornamenti andati male, NON dalla
# perdita del server: i backup stanno sullo stesso disco. Se qualcosa
# fallisce lo staff riceve una notifica nell'app.
# Ripristino: scripts/restore.sh; prova automatica: scripts/verify-backup.sh.
# Usage: scripts/backup.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="./backups"
BACKUP_FILE="${BACKUP_DIR}/jav_${ENV}_${TIMESTAMP}.sql.gz"
ENV_DIR="${BACKUP_DIR}/env"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

# Un backup che fallisce in silenzio è peggio di nessun backup: lo staff lo
# deve sapere. Best effort -- se anche l'app è giù, resta backups/backup.log.
CURRENT_STEP="avvio"
alert_staff() {
  echo "!! Backup FALLITO: $CURRENT_STEP" >&2
  ./scripts/notify-staff.sh "$ENV" "Backup notturno non riuscito" \
    "Passo fallito: $CURRENT_STEP. Vedi backups/backup.log sul server."
}
trap alert_staff ERR

mkdir -p "$BACKUP_DIR" "$ENV_DIR"
chmod 700 "$ENV_DIR"

# shellcheck disable=SC1091
# Every value in .env must be quoted if it contains spaces (e.g.
# COMPANY_BANK_HOLDER="Jav") -- plain `source` parses it as bash,
# not as a dotenv file, so an unquoted space breaks this line with a
# confusing "command not found" and aborts the whole backup silently
# (confirmed live: COMPANY_BANK_HOLDER=Jav without quotes did
# exactly this before it was fixed).
[ -f .env ] && source .env

# --- 1. Database --------------------------------------------------------------
CURRENT_STEP="copia del database"
echo "==> Dumping database to $BACKUP_FILE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-jav}" "${POSTGRES_DB:-jav}" | gzip > "$BACKUP_FILE"
gzip -t "$BACKUP_FILE"
# Quasi vuoto vuol dire che qualcosa è andato storto anche senza errori.
if [ "$(stat -c %s "$BACKUP_FILE")" -lt 100000 ]; then
  echo "Dump sospettosamente piccolo: $BACKUP_FILE" >&2
  false
fi
echo "Backup complete: $BACKUP_FILE"

CURRENT_STEP="rotazione delle copie del database"
echo "==> Rotating ${ENV} database backups (7 days all, then weekly to 5 weeks, monthly to 6 months)"
python3 - "$BACKUP_DIR" "$ENV" <<'PY'
import re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

folder, env = Path(sys.argv[1]), sys.argv[2]
pattern = re.compile(rf"jav_{re.escape(env)}_(\d{{8}}T\d{{6}}Z)\.sql\.gz$")
now = datetime.now(timezone.utc)
dumps = sorted(
    ((datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), p)
     for p in folder.iterdir() if (m := pattern.match(p.name))),
    reverse=True,
)
keep, weeks, months = set(), set(), set()
for when, path in dumps:  # dal più recente: di ogni settimana/mese resta il più nuovo
    age = now - when
    week, month = tuple(when.isocalendar()[:2]), (when.year, when.month)
    if age <= timedelta(days=7):
        keep.add(path)
    elif age <= timedelta(days=35) and week not in weeks:
        keep.add(path)
    elif age <= timedelta(days=183) and month not in months:
        keep.add(path)
    weeks.add(week)
    months.add(month)
if dumps:
    keep.add(dumps[0][1])  # l'ultimo non si tocca mai
for _, path in dumps:
    if path not in keep:
        print(f"removed {path}")
        path.unlink()
PY

# --- 2. .env -----------------------------------------------------------------
CURRENT_STEP="copia del file .env"
LAST_ENV="$(find "$ENV_DIR" -name 'env_*' | sort | tail -1)"
if [ -f .env ] && { [ -z "$LAST_ENV" ] || ! cmp -s .env "$LAST_ENV"; }; then
  install -m 600 .env "$ENV_DIR/env_${TIMESTAMP}"
  echo "==> .env changed: saved $ENV_DIR/env_${TIMESTAMP}"
fi

echo "==> Done. Space used by backups: $(du -sh "$BACKUP_DIR" | cut -f1)"
