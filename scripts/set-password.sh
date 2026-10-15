#!/usr/bin/env bash
# Imposta una password nuova per un account, dall'host.
#
#   ./scripts/set-password.sh persona@example.com
#
# La password si scrive due volte e non compare a schermo né nei log: passa
# al container in una variabile d'ambiente, viene cifrata (argon2, come al
# login) e si salva solo l'impronta. Sblocca anche l'account se era bloccato
# da troppi tentativi. Non manda email.
set -euo pipefail
cd "$(dirname "$0")/.."

email="${1:-}"
if [[ -z "$email" ]]; then
  echo "Uso: $0 email" >&2
  exit 1
fi
read -r -s -p "Nuova password per $email: " pw1; echo
read -r -s -p "Ripetila: " pw2; echo
if [[ "$pw1" != "$pw2" ]]; then
  echo "Le due password non coincidono." >&2
  exit 1
fi
if (( ${#pw1} < 10 )); then
  echo "Usa almeno 10 caratteri." >&2
  exit 1
fi

NEW_PASSWORD="$pw1" TARGET_EMAIL="$email" docker compose -f docker-compose.dev.yml exec -T \
  -e NEW_PASSWORD -e TARGET_EMAIL api python - <<'PY'
import asyncio, os
from sqlalchemy import func, select
from app import celery_app  # noqa: F401  (tutti i modelli)
from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.users.models import User

async def main():
    email = os.environ["TARGET_EMAIL"].strip().lower()
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().all()
        if len(users) != 1:
            print("Nessun account con questa email." if not users else "Più account con questa email: non cambio niente.")
            raise SystemExit(1)
        user = users[0]
        user.password_hash = hash_password(os.environ["NEW_PASSWORD"])
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()
        print(f"Password impostata per {email}.")

asyncio.run(main())
PY
