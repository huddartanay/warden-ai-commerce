# Architecture

## One-line

Warden is a deterministic authorization boundary that separates *AI intent* from
*financial action*.

## Flow

```
Customer mandate
      ↓
AI Buyer Agent        (agents/) — LLM, no financial authority
      ↓
Merchant Catalog       (services/, models/) — structured product data
      ↓
Cart proposal          (typed proposal → warden/)
      ↓
WARDEN CORE            (warden/) — deterministic policies
      ↓
ALLOW / STEP_UP / BLOCK
      ↓
Razorpay Test APIs     (payments/) — only reachable after ALLOW
      ↓
Audit Trail            (audit/) — append-only, hash-chained
```

## Deterministic checks Warden performs

- mandate exists / active / matches customer + merchant
- category allowed
- amount within remaining spend cap
- velocity / frequency
- price hasn't drifted from last observed
- idempotency (no duplicate action for the same logical proposal)

Idempotency key:
```
sha256(mandate_id || cart_id || period)
```

## Audit hash chain

```
current_hash = SHA256(previous_hash || canonicalized_event_data)
```

## Package layout (backend/app/)

| Package     | Responsibility                                            | May call LLM? | May call Razorpay? |
|-------------|-----------------------------------------------------------|---------------|--------------------|
| `api/`      | HTTP routes, DTOs, dependency wiring                      | no            | no                 |
| `models/`   | SQLAlchemy ORM models                                     | no            | no                 |
| `schemas/`  | Pydantic request/response contracts                       | no            | no                 |
| `services/` | Cross-cutting business services (catalog, mandates, cart) | no            | no                 |
| `warden/`   | Deterministic policy engine + decision routing            | **no**        | no                 |
| `agents/`   | AI Buyer + Explainer                                      | yes           | **no**             |
| `payments/` | Razorpay adapter                                          | no            | yes                |
| `audit/`    | Append-only hash-chained audit writer                     | no            | no                 |

The two hard rules:

1. `warden/` is pure Python. No LLM calls.
2. `payments/` is only invoked from the post-ALLOW path routed by `warden/`.

## Health endpoints

- `GET /health/live` — process is up. DB-independent.
- `GET /health/ready` — reports DB reachability. Returns `status: "degraded"` when
  DB is down, but still `HTTP 200` so operators see the check payload.

## Concurrency: atomic spend-cap enforcement (Stage 7)

Two concurrent proposals against the same mandate would otherwise both read
`remaining = 500`, both pass `amount_within_cap`, and both get ALLOWed — a
real race that would violate the cap. Warden closes this with **optimistic
concurrency**, not row locking, so it works identically on Postgres and on
the SQLite-backed test harness.

**Mechanism**

1. `mandate.version` is an integer column, monotonically increasing.
2. `evaluate_proposal` reads the mandate + its `version`, runs the pure
   engine, and — only for `ALLOW` — performs a single UPDATE:
   ```sql
   UPDATE mandates
      SET current_period_spend = ?, current_period_transactions = ?,
          status = ?, version = version + 1
    WHERE id = ? AND version = <observed_version>
   ```
   If `rowcount != 1`, some other proposal moved the row first.
3. On CAS conflict, the coordinator expires the ORM object, re-reads the
   mandate, and re-runs the engine (up to 3 retries). Because the mandate's
   spend is now higher, the engine will typically flip to
   `BLOCK CAP_EXCEEDED` naturally, without special-casing.
4. If all 3 retries lose their CAS, the outcome is
   `BLOCK CONCURRENT_UPDATE` — a distinct reason so a judge dashboard can
   distinguish "you hit contention" from "you hit the cap".

**Why optimistic over pessimistic (`SELECT FOR UPDATE`)?**

- SQLite has no meaningful `FOR UPDATE`; the test suite would have to skip
  the invariant entirely.
- Optimistic CAS keeps write transactions short — no held locks, no
  deadlock class to reason about.
- Contention on a single mandate is expected to be low (one customer, one
  agent). The retry ceiling is 3, which is more than enough for the
  observed contention pattern, and the terminal BLOCK is safe.

**Enforcement test:** `tests/test_concurrency.py::test_concurrent_proposals_cannot_double_spend_cap`
runs N=8 threads against a mandate that can only satisfy one proposal and
asserts exactly one ALLOW, N-1 BLOCKs, zero STEP_UPs.

## Stages

- **Stage 1 (this stage):** scaffold, health, DB connection, frontend shell.
- Later: models + migrations, mandate engine, catalog, AI buyer agent, Warden
  decision engine, Razorpay integration, audit chain, judge dashboard, demo
  control panel.
