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
Customer mandate
      ↓
AI Buyer Agent        (LLM — intent, search, cart proposal; NO financial authority)
      ↓
Product discovery
      ↓
Cart proposal
      ↓
WARDEN                (deterministic — the authority)
      ↓
ALLOW / STEP_UP / BLOCK
      ↓
Razorpay Test APIs    (only after authorization)
      ↓
Payment result
      ↓
Tamper-evident audit trail   (append-only, hash-chained)
```

### Components

1. **AI Buyer Agent** — LLM-powered intent understanding, catalog search, cart proposal. No financial authority.
2. **Merchant Catalog Service** — structured product/pricing/category/availability data.
3. **Warden Core** — deterministic mandate + policy engine, spend/velocity/category/price-drift checks, idempotency, decision routing, state machine.
4. **Explainer** — optional LLM that turns Warden decisions into natural language. Cannot modify the decision.
5. **Razorpay Payment Service** — test mode only. Financial tools reachable only after Warden authorization.
6. **Audit Service** — append-only, hash-chained, complete transaction history.

## Core principle

The LLM must **never** be trusted with financial authorization. All financially
sensitive decisions are deterministic. Warden is the authority.

## Tech stack

- **Frontend:** Next.js · TypeScript · Tailwind CSS
- **Backend:** Python · FastAPI
- **Database:** PostgreSQL
- **AI:** LLM with structured outputs / tool calling
- **Payments:** Razorpay Test Mode APIs

## Repository layout

```
backend/    FastAPI service — Warden Core, catalog, mandates, Razorpay, audit
frontend/   Next.js judge dashboard + demo control panel
docs/        Design notes and stage plans
```

## Build plan (MVP first, one stage at a time)

Staged, incremental delivery. Each stage: inspect → implement only that stage →
run → test → fix → report → then advance.

Status: **repo scaffolded.** Awaiting Stage 1.
