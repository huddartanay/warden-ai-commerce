# Warden

**Let AI create demand. Let Warden decide when money can move.**

Warden is a deterministic trust and authorization layer that sits between AI buyer
agents and Razorpay payment infrastructure. AI agents can understand intent, search
catalogs, and propose carts — but they are never allowed to freely move money. Every
proposed financial action is evaluated by Warden and receives exactly one verdict:

- **ALLOW** — satisfies all deterministic policies
- **STEP_UP** — requires human approval
- **BLOCK** — violates a hard rule

Razorpay is only ever called after an ALLOW (or a human-approved STEP_UP). A BLOCK
never reaches Razorpay.

## Thesis

> AI buyers can create demand, but merchants need a trust layer before that demand
> can safely become a transaction.

- **AI** creates demand.
- **Warden** governs autonomy.
- **Razorpay** executes payment.
- **Audit** proves what happened.

## Architecture

```
Customer mandate → AI Buyer Agent → Cart proposal
      → WARDEN (deterministic) → ALLOW / STEP_UP / BLOCK
      → Razorpay Test APIs → Payment result → Tamper-evident audit trail
```

Full breakdown: [docs/architecture.md](docs/architecture.md).

**The two hard rules:**

1. `backend/app/warden/` never calls an LLM.
2. `backend/app/payments/` is only reachable after a Warden ALLOW.

## Repository layout

```
backend/
  app/
    api/         HTTP routes (currently: /health/live, /health/ready)
    models/      SQLAlchemy ORM — 8 tables + enums
    schemas/     Pydantic contracts (added alongside routes)
    services/    Business services (mandate state machine live; more coming)
    warden/      Deterministic policy engine — the authority
    agents/      AI Buyer + Explainer — proposals only, no financial authority
    payments/    Razorpay adapter — only invoked after ALLOW
    audit/       Append-only, hash-chained audit log (writer + verifier)
    config.py    Settings (pydantic-settings, reads .env)
    db.py        SQLAlchemy engine + session
    main.py      FastAPI app factory
    seed.py      python -m app.seed loads Priya's D2C Coffee demo data
  alembic/       Migrations
  alembic.ini
  tests/         pytest suite
  requirements.txt
  .env.example
  pytest.ini

frontend/
  app/           Next.js 14 app-router pages
  lib/           API client
  package.json
  tsconfig.json
  tailwind.config.ts
  postcss.config.mjs
  next.config.mjs
  .env.local.example

docs/
  architecture.md
```

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (running locally, or via Docker)

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit DATABASE_URL etc. as needed
uvicorn app.main:app --reload --port 8000
```

Backend endpoints:

- <http://localhost:8000/> — service info
- <http://localhost:8000/docs> — interactive OpenAPI docs
- <http://localhost:8000/health/live> — liveness
- <http://localhost:8000/health/ready> — readiness (with DB probe)

Run tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

### Migrations + seed

```bash
cd backend
source .venv/bin/activate

# Apply all migrations against the DB pointed at by DATABASE_URL
alembic upgrade head

# Load demo data (Priya's D2C Coffee, 4 products, 3 mandates). Idempotent.
python -m app.seed
```

The seed script also accepts `--url` and `--create-tables` for ad-hoc SQLite:

```bash
python -m app.seed --url sqlite:///demo.db --create-tables
```

### 2. PostgreSQL

The default `DATABASE_URL` in `.env.example` expects:

- host `localhost`, port `5432`
- user `warden`, password `warden`
- database `warden`

Create it once (any equivalent works):

```bash
createuser warden --pwprompt   # set password: warden
createdb  warden --owner=warden
```

If Postgres isn't running yet:

```bash
# Homebrew:
brew services start postgresql@18

# or ad-hoc:
pg_ctl -D /opt/homebrew/var/postgresql@18 -l ~/pg.log start
```

Verify:

```bash
pg_isready
psql -U warden -d warden -c 'SELECT 1;'
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Then open <http://localhost:3000>. The landing page fetches
`/health/ready` from the backend and shows two status tiles: **Backend** and
**Database**.

## How the frontend and backend communicate

- The frontend reads `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
  to know where the backend lives.
- All calls go through `frontend/lib/api.ts`.
- The backend runs FastAPI with permissive CORS for origins listed in
  `CORS_ORIGINS` (default `http://localhost:3000`).
- Server components fetch with `cache: "no-store"` so status is always live.

## Environment variables

**Backend (`backend/.env`)**

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://warden:warden@localhost:5432/warden` | Postgres connection string (SQLAlchemy + psycopg3) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | `` | Razorpay Test Mode (used in a later stage) |
| `ANTHROPIC_API_KEY` | `` | LLM (used in a later stage) |

**Frontend (`frontend/.env.local`)**

| Var | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Base URL the browser calls |

## Build stage

**Stage 1 — done:** scaffold, health, DB connection, frontend shell.
**Stage 2 — done:** 8-table ORM model, Alembic migrations, seed data, mandate
state machine, hash-chained audit writer.
**Stage 3 — done:** Warden Core policy engine + coordinator + HTTP API. 73
tests. See [docs/WARDEN_TEST_REPORT.md](docs/WARDEN_TEST_REPORT.md).
**Stage 4 — done:** AI Buyer Agent + Explainer + demo mode.
**Stage 7 — done:** Concurrency, agent identity, adversarial resilience.
Four features, four commits:
(1) Atomic spend-cap enforcement via `mandate.version` + optimistic CAS
in `coordinator.evaluate_proposal`; bounded 3-retry loop; new
`CONCURRENT_UPDATE` reason.
`tests/test_concurrency.py::test_concurrent_proposals_cannot_double_spend_cap`
runs N=8 threads against a mandate that can only satisfy one proposal.
(2) Agent identity + HMAC signing. `app/warden/auth.py` (pure) verifies
`X-Agent-Id` + `X-Agent-Signature` before any policy check runs;
`AgentCredential` scoped per mandate; auth failure = BLOCK
`AGENT_AUTH_FAILED` + `AGENT_AUTH_FAILED` audit event with the engine
never invoked. Extended architectural invariant
`test_warden_auth_module_is_pure` bans LLM/razorpay/network imports in
`warden/auth.py`.
(3) Structuring detection via `mandate.rolling_window_seconds` +
`mandate.rolling_window_max_amount`; new pure policy
`check_rolling_window_spend` ordered before `check_amount_within_cap`;
new `CUMULATIVE_SPEND_EXCEEDED` reason with a judge-dashboard-ready
detail string. `test_demo_agent_structuring_attack_detected` proves the
6th of 6 ₹1000 proposals within a 90s window trips it.
(4) `DEMO_MODE`-gated `POST /audit/demo/corrupt/{seq}` +
`POST /audit/demo/restore` so a presenter can show live tamper detection
via `GET /audit/verify`. Refuses (403) unless the env flag is set.
`test_audit_verify_detects_tampering` (from Stage 6) + 3 new tamper
tests cover the loop. **166 pytest cases green.**

**Stage 6 — done:** Audit + failure-recovery layer.
Central event catalog (`app/audit/events.py`) with 19 named event types;
every stage now emits its full set (`MANDATE_CREATED`, `INTENT_RECEIVED`,
`CART_CREATED`, `WARDEN_EVALUATED`, `BLOCKED`, `STEP_UP_REQUESTED`,
`DUPLICATE_DETECTED`, `HUMAN_APPROVED`, `PAYMENT_CREATED`,
`PAYMENT_COMPLETED`, `PAYMENT_FAILED`, `PAYMENT_PENDING_UNRESOLVED`,
`REFUND_REQUESTED`, `REFUND_COMPLETED`, `RESOLUTION_APPLIED`, …).
New `resolutions` table + resolution queue; auto-populated on STEP_UP
(REQUIRES_HUMAN) and payment-uncertain outcomes (PENDING_UNRESOLVED).
Endpoints: `GET /audit/action/{id}` · `GET /audit/mandate/{id}` ·
`GET /audit/verify` · `GET /audit/resolution-queue` ·
`POST /audit/resolve/{action_id}` · `POST /warden/execute-payment/…`
(from Stage 5). **151 pytest cases green**, including the showcase
`test_demo_payment_failure_never_double_charges` that walks a failed
capture through the full recovery lifecycle proving no double charge.
Next: judge dashboard.

**Stage 5 — done:** Razorpay TEST-MODE integration.
`app/payments/` is the only package that imports the Razorpay SDK; only
`app/warden/coordinator.py` may import `app/payments/`. Enforced by
`test_architectural_invariants.py`.
Endpoints:
`POST /warden/execute-payment/{action_id}` (create order + link, idempotent),
`POST /warden/simulate-capture/{action_id}` (mock/test capture),
`POST /warden/refund/{action_id}` (rolls back mandate reservation).
`/agent/purchase-intent` auto-executes payment on Warden ALLOW.
`RAZORPAY_MODE=auto|live|mock` — offline demos work end-to-end; live client
refuses `rzp_live_` keys. **134 pytest cases green** including three E2E
scenarios (ALLOW→order, BLOCK→no razorpay, duplicate→same order).
Next: judge dashboard.
