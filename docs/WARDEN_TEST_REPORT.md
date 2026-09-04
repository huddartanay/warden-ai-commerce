# Warden test report

**Current result: 108 / 108 tests pass, 0 warnings.**

```
tests/test_agent_api.py                12   Agent HTTP
tests/test_agent_buyer.py               7   Agent E2E pipeline (incl. "Restock my coffee")
tests/test_agent_explainer.py           4   Explainer (read-only)
tests/test_agent_tools.py               9   Agent tools
tests/test_architectural_invariants.py  3   Guardrails (no forbidden imports)
tests/test_audit_hash.py                9   Hash chain determinism + tamper detection
tests/test_health.py                    3   /health/live and /health/ready
tests/test_mandate_transitions.py       9   Mandate state machine
tests/test_models_create.py             2   Schema + FK round-trip
tests/test_seed.py                      2   Seed inserts + idempotency
tests/test_warden_api.py               17   Warden HTTP
tests/test_warden_coordinator.py       13   Warden coordinator (DB-integrated)
tests/test_warden_engine.py            18   Warden engine (pure)
────────────────────────────────────────────
                                      108   ✅
```

Executed via `pytest` in the backend venv. `WARDEN_LLM_MODE=mock` is forced in
`conftest.py` before any app import, so no test ever contacts the network.

## Warden-spec scenario coverage (Stage 3)

The Stage 3 spec listed 11 required scenarios. Each is covered at at least one
layer, most at two.

| # | Scenario                                          | Engine test                                             | HTTP test                                    |
|---|---------------------------------------------------|---------------------------------------------------------|----------------------------------------------|
| 1 | valid transaction → ALLOW                         | `test_valid_transaction_is_allowed`                     | `test_post_evaluate_allow`                   |
| 2 | amount above cap → BLOCK CAP_EXCEEDED             | `test_amount_above_cap_blocks_with_cap_exceeded`        | `test_post_evaluate_block_cap_exceeded`      |
| 3 | category outside mandate → BLOCK                  | `test_category_outside_mandate_blocks`                  | `test_post_evaluate_block_category_out_of_scope` |
| 4 | expired mandate → BLOCK                           | `test_expired_mandate_blocks_by_status` + `test_expired_by_validity_end_blocks_even_if_status_stale` | (implicit)                                   |
| 5 | revoked mandate → BLOCK                           | `test_revoked_mandate_blocks`                           | `test_revoke_endpoint_marks_revoked_and_subsequent_proposals_block` |
| 6 | transaction frequency exceeded → BLOCK            | `test_transaction_frequency_exceeded_blocks`            | `test_post_evaluate_block_after_transaction_limit` |
| 7 | price drift → BLOCK PRICE_DRIFT                   | `test_price_drift_blocks_with_price_drift`              | `test_post_evaluate_block_price_drift`       |
| 8 | duplicate action → original decision              | `test_duplicate_idempotency_key_returns_same_decision_and_no_new_action` + `test_duplicate_of_blocked_action_returns_the_same_block` | `test_post_evaluate_is_idempotent`           |
| 9 | invalid merchant → BLOCK                          | `test_invalid_merchant_blocks`                          | (implicit)                                   |
| 10 | invalid customer → BLOCK                          | `test_invalid_customer_blocks`                          | `test_post_evaluate_block_invalid_customer`  |
| 11 | valid transaction requiring approval → STEP_UP    | `test_step_up_when_over_configured_threshold_but_within_cap` | `test_post_evaluate_step_up` + `test_approve_endpoint_transitions_step_up_action` |

## Agent-layer coverage (Stage 4)

- **`test_restock_coffee_end_to_end_allows`** — the canonical NL→cart→Warden→NL-explanation showcase.
- **`test_agent_respects_mandate_cap_when_intent_asks_more`** — a user asking for more than the mandate cap gets a cart clipped to the cap.
- **`test_low_confidence_intent_escalates_to_step_up`** — agent-level STEP_UP when confidence < threshold, even if Warden ALLOWed.
- **`test_missing_customer_mandate_raises`** — no active mandate → clean error.
- **`test_idempotent_intent_returns_same_warden_action`** — repeat pipeline call returns the persisted decision without re-running the LLM.
- **`test_impossible_budget_returns_agent_block_without_calling_warden`** — empty cart short-circuits to an agent BLOCK; no zero-total proposal reaches Warden.
- **`test_bulk_customer_high_amount_step_ups_via_warden`** — mandate B's step-up threshold is honored end-to-end.

## Architectural invariants (defence-in-depth)

`test_architectural_invariants.py` performs static AST checks:

1. **`test_warden_package_never_imports_llm_or_agents`** — `app/warden/` may not import `app.agents`, `anthropic`, `openai`, or `razorpay`.
2. **`test_agents_package_never_imports_razorpay`** — the agent may propose, never pay.
3. **`test_only_the_coordinator_persists_decisions`** — only `app/warden/coordinator.py` may `session.add(Decision(...)` or call `apply_successful_action(...)`.

If any of these break, the pitch is compromised — the tests fail hard.

## Real-database verification

The full stack — Alembic migrations 001 and 002, seed script, HTTP API — was
exercised against a live **PostgreSQL 18** instance (ephemeral, port 5555, temp
data directory), not just SQLite. Results:

- Migrations `001_initial` and `002_mandate_step_up` apply cleanly on PG.
- Seed inserts (1 merchant, 4 catalog items, 3 mandates) round-trip.
- `/health/ready` reports `db_ok=True`.
- `/agent/purchase-intent` end-to-end run: `agent_verdict=ALLOW`, cart `₹1499.00`,
  Warden decision persisted with `action_id=act_...`.
- Reservation persisted on the mandate: `current_period_spend=1499.00`,
  `current_period_transactions=1`, `status=EXHAUSTED` (tx_limit=1).

## Layered test strategy

- **Pure engine** — `Mandate` objects in memory, `evaluate()` called directly. No DB.
- **Coordinator** — real SQLite session. Idempotency, reservation, audit chain.
- **HTTP** — FastAPI `TestClient` against every Warden and Agent endpoint.
- **Architectural** — AST scan of the source tree.

## What Warden explicitly does NOT do yet

- No Razorpay call — Stage 5.
- No rollback of the reservation when a payment later fails — Stage 5 will
  introduce compensating updates.
- No STEP_UP band for medium price drift — currently any drift above 1% BLOCKs.

## Reproducing

```bash
cd backend
source .venv/bin/activate
pytest
```
