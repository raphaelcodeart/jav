# Jav Platform — Architecture

Status: Living document. Updated at the end of every implementation phase (see `implementation-progress.md`).

## 1. Context

Jav is a management portal for gyms and judo clubs (JAV = Judo Arte e Vida):
families manage their athletes, monthly fees, payment proofs, medical
certificates and competition entries; the club office manages plans,
competitions and results; instructors take attendance and award belts. The
club domain is specified in `club-portal.md`.

It is built on a generic base inherited from an earlier management platform:
a multilevel commercial network of promoters with a deterministic commission
engine, contracts and "pratiche" (customer data once, N contracts, one bank
transfer), a catalog with orders, an internal Shop (`jav_market`) whose
catalog the admin writes, an internal credit wallet (JavCash), documents,
support tickets, notifications, a documentation feed, accounting views and
full audit. Payments are bank transfers (confirmed by an admin, or — for club
fees — declared by the parent with an uploaded proof) and JavCash credit;
there is no card payment provider.

Commission/career-plan rules are **configurable and provisional** — see
`open-questions.md`.

## 2. Style: modular monolith, not microservices

One deployable backend (FastAPI) with clearly separated domain packages, one deployable
frontend (Next.js BFF), one worker (Celery) that imports the backend's domain code
directly rather than re-implementing it. Microservices are explicitly rejected for v1:
the commission engine must have exactly one authoritative implementation, and splitting
it across network-separated services would risk divergent logic and would add
operational cost (service discovery, distributed tracing, inter-service auth) with no
present benefit. This can be revisited if/when a specific bounded context needs
independent scaling or independent deploy cadence — see `adr/0001-modular-monolith.md`.

```
Browser
   │
   ▼
Caddy (host, HTTPS) → nginx (127.0.0.1:8081, internal router)
   │
   ▼
Next.js BFF (apps/dashboard)  ── same-origin cookie session, proxies to API
   │
   ▼
FastAPI (apps/api)
   │
   ▼
PostgreSQL 16+ ── relational data, commercial network, commission ledger, audit,
   │              full-text search, pgvector (AI, Phase G)
   ▼
Celery + Redis (apps/worker) ── async jobs: notifications, document processing,
   │                             commission batch runs, embeddings
   ▼
S3-compatible storage (MinIO) ── documents, payment proofs, certificates, photos
```

## 3. Domain boundaries (module map)

Each of these is a Python package under `apps/api/app/domains/<name>/` with its own
`models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `tests/`. Domains
depend on each other only through service-layer calls, never by reaching into another
domain's ORM internals directly from a router.

| Domain | Responsibility | Phase |
|---|---|---|
| `auth` | login, sessions, tokens, password reset, email verification | B |
| `users` | user accounts, profile | B |
| `organizations` | tenants, org membership | B |
| `rbac` | roles, permissions, policy evaluation (RBAC+ABAC) | B |
| `audit` | append-only audit log | B |
| `storage` | document upload/download, S3 client wrapper | B (stub), D (full) |
| `network` | agent nodes, edges, closure table, snapshots, moves | C |
| `referral` | promoter codes, referral events/sessions, attribution | C |
| `customers` | customer profiles, companies, addresses | D |
| `catalog` | products, product versions, pricing. **`pricing.py` is the single place VAT, who-may-buy-what, and where-a-JavCash-credit-comes-from are decided** — every money figure in the app derives from it, server-side only (see `business-rules.md#contract-economics`) | D |
| `contracts` | contract state machine, events, pratiche (N contracts, one bank transfer), payment plans and instalments confirmed by an admin | D |
| `documents` | document metadata, versions, permissions | D |
| `ranks` | qualifications / career plan, versioned thresholds | E |
| `commissions` | plan versions, calculators, ledger, simulator | E |
| `renewals` / `reversals` | renewal & storno events | E |
| `notifications` | in-app notifications (approvals, rank changes, tickets) | E (built) |
| `documentation` | admin-authored news/training posts for customers & promoters | E (built) |
| `wallets` | internal EUR wallet per user (JavCash), admin cashback, peer transfers | E (built) |
| `jav_market` / `carts` / `marketplaces` / `shop_categories` | the internal Shop (equipment, judogi, ...): admin-written catalog with variants, cart, orders paid by bank transfer and/or JavCash, shared rules in `marketplaces/rules.py` | built |
| `orders` | orders of catalog products, bank transfer + JavCash | built |
| `accounting` | per-customer and org-wide money movements and details | built |
| `club` | athletes (children managed by a parent account), age-based plans, monthly/enrolment/competition fees, payment proofs (auto-accepted), medical certificates, belts, courses and attendance, competitions and results, Jav Ranking, achievements, scheduled jobs | built (backend) |
| `reports` | aggregate reporting endpoints | F |
| `ai` | pgvector ingestion, hybrid search, assistant | G |

## 4. Request flow & security boundary

The Next.js app never talks to Postgres/Redis directly. It holds an HttpOnly/Secure/
SameSite=Lax session cookie, and its Route Handlers proxy authenticated requests to
FastAPI, attaching the access token server-side. FastAPI is the **only** place
authorization is enforced — the frontend hiding a button is a UX nicety, never a
security control. Every domain query that touches org-scoped or branch-scoped data
applies the tenant/branch filter in the repository layer, not only in the router.

## 5. Data integrity rules (non-negotiable, see `business-rules.md` for detail)

- Money, percentages and quantities used in economic calculations: `Decimal` in Python,
  `NUMERIC` in Postgres, or integer cents. Never `float`.
- The commercial network's source of truth is Postgres (closure table). No graph
  database in v1 (see `adr/0002-no-graph-db-v1.md`). pgvector is used only for
  semantic/document search, never for the org chart (see `adr/0003-pgvector-scope.md`).
- Consolidated commission ledger movements are immutable; corrections are new movements.
- Contract attribution is frozen via `network_snapshot_id` at activation time; later
  network moves never rewrite historical attribution or past calculations.
- **A contract's economics are frozen at creation too** (`net_amount_cents`,
  `vat_rate`, `vat_amount_cents`, `gross_amount_cents`, `customer_kind`): editing a
  product's price or VAT rate can never restate a contract somebody already signed.
  Same rule, one layer down, as the network snapshot above.
- **No economic value is ever taken from the client.** Prices, VAT, commissions,
  cashback, bonuses and wallet amounts are computed from database rows inside the
  service layer; the browser sends identifiers and intent, never amounts.
- **Exactly-once for anything that moves money** is enforced by a UNIQUE constraint on
  a deterministic key, not by an application flag that could drift: `wallet_
  transactions.idempotency_key`, `commission_movements.idempotency_key`,
  `uq_commission_calculations_contract_trigger`. Readable guards (e.g.
  `contracts.cashback_credited_at`) exist on top of those, never instead of them.
- **A notification can never fail an operation that already committed.** Mail sent
  after a commit goes through `core/email.py::send_html_email_best_effort`, which
  never raises — the one exception being password-reset links and OTP codes, where the
  email IS the deliverable (see `server-migration-guide.md §8 #17` for the
  double-credit bug this rule exists to prevent).

## 6. Repository layout (target)

```
/apps
  /api         FastAPI backend (domains/, alembic/, tests/)
  /dashboard   Next.js 16 App Router BFF + UI
  /worker      Celery worker + beat, imports apps/api domain code
/packages
  /shared-types   Types shared between dashboard and worker/scripts (generated from OpenAPI where possible)
  /config         Shared lint/tsconfig bases
/infrastructure
  /docker
  /nginx
  /postgres
  /monitoring
/scripts       deploy/backup/restore/health-check/migrate/rollback
/docs          this documentation set
```

`packages/ui`, `packages/api-client`, `packages/eslint-config`, `packages/typescript-config`
are placeholders reserved for Phase F when the dashboard grows multiple apps; not
created empty in Phase B to avoid dead scaffolding (YAGNI — added the moment a second
consumer needs them).

## 7. What is implemented vs. planned

See `implementation-progress.md` for the authoritative, continuously-updated status.
This document describes target architecture, not necessarily current state.
