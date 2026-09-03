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

## Stages

- **Stage 1 (this stage):** scaffold, health, DB connection, frontend shell.
- Later: models + migrations, mandate engine, catalog, AI buyer agent, Warden
  decision engine, Razorpay integration, audit chain, judge dashboard, demo
  control panel.
