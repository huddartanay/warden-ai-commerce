# Warden test report — Stage 3

**Result: 73 / 73 tests pass.**

```
tests/test_audit_hash.py            9 passed
tests/test_health.py                3 passed
tests/test_mandate_transitions.py   9 passed
tests/test_models_create.py         2 passed
tests/test_seed.py                  2 passed
tests/test_warden_engine.py        18 passed   (pure engine)
tests/test_warden_coordinator.py   13 passed   (DB-integrated service)
tests/test_warden_api.py           17 passed   (HTTP surface)
────────────────────────────────────────────
                                   73 passed
```

Executed via `pytest` in the backend venv against an in-memory SQLite (StaticPool
so every connection shares the same DB). No live Postgres required.

## Required scenario coverage

The spec listed 11 scenarios that Warden tests **must** cover. Every one is
verified at at least one layer, most at two (pure engine + HTTP surface).

| # | Scenario                                          | Engine test                                             | HTTP test                                    |
|---|---------------------------------------------------|---------------------------------------------------------|----------------------------------------------|
| 1 | valid transaction → ALLOW                         | `test_valid_transaction_is_allowed`                     | `test_post_evaluate_allow`                   |
| 2 | amount above cap → BLOCK CAP_EXCEEDED             | `test_amount_above_cap_blocks_with_cap_exceeded`        | `test_post_evaluate_block_cap_exceeded`      |
| 3 | category outside mandate → BLOCK                  | `test_category_outside_mandate_blocks`                  | `test_post_evaluate_block_category_out_of_scope` |
| 4 | expired mandate → BLOCK                           | `test_expired_mandate_blocks_by_status` + `test_expired_by_validity_end_blocks_even_if_status_stale` | (implicit via engine)                        |
| 5 | revoked mandate → BLOCK                           | `test_revoked_mandate_blocks`                           | `test_revoke_endpoint_marks_revoked_and_subsequent_proposals_block` |
| 6 | transaction frequency exceeded → BLOCK            | `test_transaction_frequency_exceeded_blocks`            | `test_post_evaluate_block_after_transaction_limit` |
| 7 | price drift → BLOCK PRICE_DRIFT                   | `test_price_drift_blocks_with_price_drift`              | `test_post_evaluate_block_price_drift`       |
| 8 | duplicate action → original decision              | `test_duplicate_idempotency_key_returns_same_decision_and_no_new_action` (coordinator) + `test_duplicate_of_blocked_action_returns_the_same_block` | `test_post_evaluate_is_idempotent`           |
| 9 | invalid merchant → BLOCK                          | `test_invalid_merchant_blocks`                          | (implicit)                                   |
| 10| invalid customer → BLOCK                          | `test_invalid_customer_blocks`                          | `test_post_evaluate_block_invalid_customer`  |
| 11| valid transaction requiring approval → STEP_UP    | `test_step_up_when_over_configured_threshold_but_within_cap` | `test_post_evaluate_step_up` + `test_approve_endpoint_transitions_step_up_action` |

## Additional coverage beyond the required list

- **Missing mandate** → BLOCK INVALID_MANDATE (`test_missing_mandate_blocks_with_invalid_mandate`, `test_post_evaluate_block_invalid_mandate`)
- **Currency mismatch** → BLOCK (`test_currency_mismatch_blocks`)
- **Partial spend then over-cap** → BLOCK CAP_EXCEEDED (`test_amount_above_remaining_after_partial_spend_blocks`)
- **Step-up threshold with room** → ALLOW (`test_step_up_does_not_fire_when_amount_at_or_below_threshold`)
- **Price drift within tolerance** → ALLOW (`test_price_drift_within_tolerance_is_allowed`)
- **Ordering rule** → categorical BLOCK is surfaced before amount-cap BLOCK when both violated (`test_short_circuit_on_first_block`)
- **Hard-BLOCK beats STEP_UP** → a proposal above both the step-up threshold and the cap returns BLOCK (`test_hard_block_wins_over_step_up`)
- **Reservation semantics** → ALLOW reserves budget so a subsequent proposal sees reduced remaining cap (`test_allow_reserves_budget_and_persists`, `test_second_action_sees_reduced_remaining_budget`)
- **BLOCK does not reserve** (`test_block_does_not_reserve_budget`)
- **STEP_UP does not reserve until approved; approval then reserves** (`test_step_up_action_can_be_approved_and_then_reserves_budget`)
- **Approve endpoint state guard** — non-STEP_UP action cannot be approved (`test_approving_a_non_stepup_action_raises`, `test_approve_endpoint_rejects_non_stepup`); unknown action → 404 (`test_approving_unknown_action_raises`, `test_approve_endpoint_404_when_action_missing`)
- **Revoke** → mandate marked REVOKED and subsequent proposals BLOCK MANDATE_REVOKED (`test_revoking_a_mandate_marks_it_and_blocks_further_proposals`); unknown mandate → error (`test_revoking_unknown_mandate_raises`)
- **Audit** → every evaluate writes `WARDEN_EVALUATED`; revoke writes `MANDATE_REVOKED`; approve writes `HUMAN_APPROVED`; the chain verifies (`test_evaluation_writes_audit_event_and_chain_is_valid`, `test_revoke_emits_mandate_revoked_event`, `test_approve_emits_human_approved_event`)
- **GET mandate / GET action** happy-path and 404 (`test_get_mandate_endpoint`, `test_get_mandate_404`, `test_get_action_endpoint`, `test_get_action_404`)

## Layered test strategy

- **`test_warden_engine.py` (18 tests)** — build `Mandate` objects in memory, call `evaluate()` directly. No DB, no HTTP. Proves the deterministic policy chain in isolation.
- **`test_warden_coordinator.py` (13 tests)** — real SQLite session. Exercises idempotency short-circuit, reservation semantics, `approve_step_up`, `revoke_mandate`, and the audit hash chain end-to-end.
- **`test_warden_api.py` (17 tests)** — full HTTP through FastAPI's `TestClient` against `/warden/evaluate`, `/warden/approve/{id}`, `/warden/revoke-mandate/{id}`, `/warden/mandate/{id}`, `/warden/action/{id}`.

Every layer confirms the same invariant from a different angle. If any single
layer regresses, we'll see exactly where.

## What Warden explicitly does NOT do yet

- No Razorpay call — Stage 4.
- No rollback of the reservation when a payment later fails — Stage 4 will
  introduce compensating updates when the Razorpay payment path is added.
- No STEP_UP band for medium price drift — currently any drift above 1% BLOCKs.
  Configurable later if needed.
- No per-request tolerance override — `WardenConfig` is passed programmatically;
  the HTTP endpoint uses defaults.

## Reproducing

```bash
cd backend
source .venv/bin/activate
pytest
```
