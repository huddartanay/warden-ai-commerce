# Warden — Trust Infrastructure for AI Commerce

> **AI proposes. Warden authorizes. Razorpay executes. Audit proves.**

Submission for the Razorpay AI Builder Internship 2026 — Track 1: AI Growth & Agentic Commerce.

| | |
|---|---|
| 🌐 **Live demo** | `LIVE_URL_HERE` |
| 💻 **Repository** | `REPO_URL_HERE` |
| 🎥 **5-minute demo video** | `VIDEO_URL_HERE` |

> Deploy + record in ~15 minutes with the step-by-step guide in [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Why Warden

AI buyer agents can already search catalogs, understand natural-language intent, and
build carts. Soon they'll be doing it at scale on behalf of real customers.

The dangerous part isn't the "buyer" — it's the "authorization." An LLM that can call
`capture_payment` directly is one prompt-injection away from draining someone's bank
account. A merchant that lets an AI freely charge cards is one silent bug away from
regulatory catastrophe.

**Warden is the deterministic authorization boundary between AI intent and money movement.**

- **AI** proposes the purchase (understands intent, searches catalog, builds a cart).
- **Warden** decides whether it can proceed (rule-based, no LLM in the decision path).
- **Razorpay** executes the payment — but only if Warden ALLOWed it first.
- **Audit** records every step in a SHA-256 hash-chained log that can be re-verified live.

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
**Stage 9 — done:** Product-level UI/UX overhaul (9/10 hackathon target).
Light-first fintech palette (warm off-white background, white surfaces,
charcoal text, restrained blue, emerald / amber / rose for
ALLOW / STEP-UP / BLOCK). New surfaces above the workspace: KPI cards
(Protected value, Allowed, Blocked, Pending review, Success rate — all
backend-derived, no fake metrics), FlowIndicator (AI Buyer → Warden →
Razorpay → Audit with per-stage state including "Not called — Warden
blocked" for the BLOCK path), plus a strong TopBar (LIVE DEMO ·
Razorpay Test Mode · Backend connected · Audit verified — no localhost
URL exposed). Three panels rebuilt: AI Buyer with intent quote /
discovery / cart / status structure and short safe agent-status
summary (never raw chain-of-thought); Warden hero with prominent
Mandate card, 8 pillar checks in a two-column grid, big
ALLOW / STEP-UP / BLOCK badge, "Why this was allowed / blocked / review
required" explanation, and Razorpay action indicator; Audit vertical
timeline with per-row hash-chain preview, clickable rows to
transaction detail, Verify chain button, and "N entries verified" pill.
Demo scenarios moved to a secondary card below the workspace with
Successful Purchase marked primary and running-state feedback. New
RecentTransactions table with Time / Action / Amount / Decision /
Reason / Razorpay / Status columns, rows clickable to the detail
page. HumanApprovalCard rewritten with premium copy for both
STEP_UP_PENDING and PENDING_UNRESOLVED. Empty state redesigned as
intentional "Warden is ready" panel with the flow diagram.
Backend `/demo/summary` extended with `allowed_count`, `blocked_count`,
`step_up_count`, `protected_value`, `blocked_value`, and
`recent_actions[]` so the KPIs and transactions table stay 100%
backend-driven — no fake decisions in frontend. Backend suite still
166/166 green. Frontend `npm run build` clean.

**Stage 8 — done:** Judge dashboard (Next.js + TS + Tailwind).
Three-panel main screen — **AI Buyer** (intent, agent reasoning, selected
products, cart, confidence, current action), **Warden hero** (7 pillar
checks: Mandate · Customer · Category · Spend · Velocity · Price ·
Idempotency, then a large ALLOW / STEP-UP / BLOCK badge with reason code
and explanation), **Audit Trail** (live chronological event stream, each
row hash-chained and clickable to `/transaction/[actionId]`).
Top bar tracks backend health, audit-chain verification badge, action
counter, pending-review counter. Live 3-second polling of `/demo/summary`
and `/health/ready`. Human approval card renders automatically when the
current action is `STEP_UP_PENDING` or `PENDING_UNRESOLVED`.
Six one-click demo scenarios wired to backend `POST /demo/scenario/{name}`
so nothing is faked in the UI: Successful Purchase, Cap Exceeded, Step-Up,
Duplicate, Price Drift, Payment Failure. `POST /demo/reset` clears state
between demos; `POST /audit/verify` re-hashes the chain live.
Transaction detail page shows mandate + cart + Warden checks + decision
+ reason + Razorpay refs + timestamps + full per-row hash chain, with
inline approve / reconcile buttons.
Backend + frontend both work in demo mode without external APIs
(`WARDEN_LLM_MODE=mock`, `RAZORPAY_MODE=mock`). Backend suite still
166/166 green. Frontend `npm run build` clean.

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
