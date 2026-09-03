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
`POST /agent/purchase-intent`, `POST /agent/search`, `POST /agent/build-cart`,
`POST /agent/explain`. LLM abstraction with `AnthropicLLMClient` (live) and
`MockLLMClient` (deterministic). `WARDEN_LLM_MODE=auto|live|mock` — offline
demos work end-to-end without a network. **104 pytest cases green.** Warden
authorization logic is unchanged. LLM never appears in the decision path.
Next: Razorpay Test integration, judge dashboard.
