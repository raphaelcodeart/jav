# Deployment

## Local development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Then:
- Dashboard: http://localhost:3000
- API docs (OpenAPI): http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Migrations

```bash
docker compose -f docker-compose.dev.yml exec api alembic upgrade head
```

or via helper script: `scripts/migrate.sh`

## Seed demo data

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```

## Scripts

All real and in active use (not skeletons -- verified against a live server, see
`docs/server-migration-guide.md §8` for the actual bugs found running them):

- `scripts/deploy.sh` — pulls, builds, migrates, restarts with health-check gating.
- `scripts/backup.sh` — every night at 04:00 (cron): `pg_dump` (real data), gzipped,
  in `./backups/` (gitignored on purpose — never commit these), rotated **7 days all,
  then one per week to 5 weeks, then one per month to 6 months** (~17 copies × ~20 MB);
  plus a copy of `.env` in `./backups/env/` (root-only, saved only when it changes).
  A dump smaller than 100 KB counts as a failure. Any failure notifies the staff in the
  app (`scripts/notify-staff.sh`). By choice, only the essentials, on
  the server — **not** the MinIO uploads and **no** off-server copy (a lost disk takes
  the backups with it). See `server-migration-guide.md §4.8` for the separate
  `mc mirror` procedure for the uploads.
- `scripts/verify-backup.sh` — every Sunday at 05:00 (cron): restores the latest dump
  into a throwaway `jav_backup_check` database, checks it has the same tables as
  the live one and rows in the core tables, then drops it; alerts the staff if the
  restore fails or the latest dump is older than two days. Never touches the live DB.
- Cron, Sunday 05:30: `docker image prune -f && docker builder prune -f` (dangling images
  and build cache only, never volumes) — rebuilds filled the disk to 97% on 2026-10-02.
- `scripts/dump-schema.sh` — regenerates `docs/database-schema.sql`, a structure-only
  (no data) `pg_dump`, portable across servers. Run after any new Alembic migration so
  this stays in sync; it's the artifact `docs/server-migration-guide.md` points to for
  "what does the database actually look like."
- `scripts/restore.sh` — restores from a named backup, verifies checksum before restore.
- `scripts/health-check.sh` — curls health/readiness endpoints for api/dashboard, checks
  postgres/redis connectivity.
- `scripts/migrate.sh` — wraps `alembic upgrade head` with a pre-migration backup.
- `scripts/rollback.sh` — `alembic downgrade -1` with an explicit confirmation prompt.
- No certificate script: HTTPS is terminated by Caddy on the host, which renews
  the Let's Encrypt certificate by itself (see `server-migration-guide.md §4.6`).

## Environments
`development` (this repo's default), `staging`, `production` — see `network-model.md`
for the topology differences. Production additionally requires: real S3-compatible
storage credentials, SMTP credentials (or leave unset and every email falls back to
being logged instead of delivered -- functional, just not delivered), and Caddy on the
host for HTTPS (see `server-migration-guide.md §4.6`).

**Payments**: bank transfer (an IBAN in Impostazioni organizzazione is all it needs;
an admin confirms each transfer) and JavCash credit. Club fees are paid by the parent
uploading a proof, which marks them paid at once (see `club-portal.md`). There is no
card payment provider.

## What is NOT yet production-ready (be explicit, don't overclaim)
CI/CD pipeline (no automated lint/test/build-on-push -- run them by hand, see
`README.md`), off-server backup copies and a backup of the MinIO uploads (today's
backups stay on the same disk as the database), monitoring stack
(Prometheus/Grafana/Loki), MFA enforcement, antivirus scanning of uploaded
documents (pluggable interface exists, no scanner wired in), and the AI/pgvector layer (`docs/ai-architecture.md` is a
design document only, no code). See `implementation-progress.md` and
`server-migration-guide.md §9` for the full, currently-accurate list -- bank-transfer
payments, notifications (in-app and email), the internal wallet/cashback system, the
club portal backend and document uploads are real, not on this list.
