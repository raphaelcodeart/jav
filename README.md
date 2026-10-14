# Jav

Gestionale e portale per palestre e club di judo (JAV = Judo Arte e Vida):
le famiglie gestiscono atleti, quote mensili, prove di pagamento, certificati
medici, iscrizioni alle gare e il Jav Ranking; la segreteria gestisce piani,
gare e risultati; gli istruttori segnano presenze e cinture. Sotto c'è una
base gestionale completa: rete commerciale multilivello con motore
provvigionale deterministico, contratti e pratiche, catalogo e ordini, Shop,
portafoglio interno JavCash, assistenza, notifiche, contabilità, audit.

Si paga con **bonifico** (confermato dall'amministrazione, o dichiarato dal
genitore caricando la prova per le quote del club) e con credito JavCash. Non
ci sono pagamenti con carta né integrazioni con fornitori esterni.

See `docs/` for the full documentation set — start with `docs/club-portal.md`
(the club domain), `docs/architecture.md` and `docs/implementation-progress.md`
(what's actually built vs. planned).

**Working on this with an AI agent?** Read `CLAUDE.md` first. It is loaded
automatically by Claude Code and holds the things the code does not say out
loud: that this deployment is live, that the containers run baked images, the
exact test invocation that does not wipe the real database, and what has to be
updated alongside a change.

**Installing on a new server, or for a new club?** Go straight to
`docs/server-migration-guide.md` — §12 is an ordered runbook from a bare server
to a working installation, each step with its own verification, and §11 lists
what to customize first. The one command that creates a real, empty club is
`python -m app.seed.bootstrap` — permissions, roles, ranks, commission plan,
one administrator — instead of the demo data.

**Using the app day to day?** See `docs/user-guide.md` (in Italian).

**Login requires HTTPS.** The session cookie is `Secure`; real browsers silently
drop it over plain HTTP (a real login attempt just reloads to `/login` with no
visible error). HTTPS is terminated by Caddy on the host
(`infrastructure/caddy/jav.caddy`, `docs/server-migration-guide.md` §4.6).

## Stack

- **Backend**: FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, Celery + Redis, MinIO
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript strict, TanStack Query/Table, Tailwind CSS 4
- **Monorepo**: pnpm workspace (`apps/api`, `apps/dashboard`, `apps/worker`)
- **Edge**: Caddy on the host (HTTPS) → nginx (internal router, `127.0.0.1:8081`)

## Quickstart (Docker Compose)

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, JWT_SECRET_KEY, MINIO_ROOT_USER/PASSWORD, S3_ACCESS_KEY/SECRET_KEY
# (S3_SECRET_KEY = MINIO_ROOT_PASSWORD, same value), NEXT_PUBLIC_APP_URL, PUBLIC_APP_BASE_URL

docker compose -f docker-compose.dev.yml up -d --build
```

This starts Postgres, Redis, MinIO, the API (the single Alembic migration
`0001_schema_iniziale.py` runs automatically on startup), the Celery worker +
beat, the dashboard, and nginx in front of them on `127.0.0.1:8081`. Put Caddy
(or any HTTPS reverse proxy) in front of that port.

- API docs (OpenAPI): `/backend/docs` through nginx, only with
  `ENABLE_API_DOCS=true` (the dashboard's own BFF routes already own `/api/*`)
- MinIO console: `http://127.0.0.1:9001`

Load demo data (promoters, customers, contracts in every state, commissions):

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```

The seed script prints the demo organization ID and login credentials
(password `DemoPass123!` for all seeded users).

For a **real** club, do not run that. Run the bootstrap instead — it creates
only what the application cannot start without plus a single administrator,
and it is idempotent:

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m app.seed.bootstrap \
    --organization-name "Nome Club" \
    --legal-name "Nome Club A.S.D." \
    --admin-email "segreteria@club.it"
```

The generated password is printed once and is not recoverable.

## Verifying the system

```bash
scripts/health-check.sh dev
docker compose -f docker-compose.dev.yml ps    # every service healthy
```

Run the backend test suite: see `CLAUDE.md` §2 for the exact invocation (a
throwaway container on the stack's network, against a `jav_test` database).
`conftest.py` drops and recreates every table at the start of the run, so the
database name must be `jav_test` — never `jav`.

Run the frontend checks:

```bash
cd apps/dashboard
pnpm install
pnpm typecheck
pnpm lint
pnpm build
```

## Repository layout

```
/apps
  /api         FastAPI backend -- domains/ (incl. club/), alembic/, tests/, seed/
  /dashboard   Next.js 16 App Router BFF + UI
  /worker      Shares apps/api's image (see apps/worker/README.md) -- no separate package
/infrastructure
  /nginx       Internal router config (HTTP only, behind Caddy)
  /caddy       The Caddy site for the host
/scripts       deploy / backup (nightly, + weekly restore test) / restore / health-check / migrate / rollback
               dump-schema (regenerates docs/database-schema.sql)
/docs          Club spec, architecture, data model, business rules, ADRs, security model, ...
CLAUDE.md      Operating instructions for AI agents working on this repo
```

## What's implemented vs. planned

Built: the club portal backend (athletes, age-based plans, automatic fees,
payment proofs, medical certificates, belts, courses and attendance,
competitions, Jav Ranking, achievements, reminders), commercial network,
contracts and pratiche, commissions, support tickets, the JavCash wallet, the
Shop, notifications (in-app + branded email) and accounting. In progress: the
UI redesign and the club portal UI. Not built: card payments (by choice),
CI/CD, MFA enforcement, antivirus scanning of uploads, and the AI/pgvector
layer (`docs/ai-architecture.md` is a design doc only). See
`docs/implementation-progress.md` for the current state and
`docs/open-questions.md` for every placeholder awaiting a decision.
