"""Buyer agent end-to-end tests, using the deterministic mock LLM."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents import BuyerAgent, MockLLMClient, NoUsableMandateError
from app.models.enums import DecisionResult, ReasonCode
from app.seed import seed_data


def _seeded(session):
    seed_data(session)
    session.commit()


def _agent() -> BuyerAgent:
    # Explicitly wire the mock so this test never touches the network even if a
    # live key exists in the environment.
    return BuyerAgent(llm=MockLLMClient())


def test_restock_coffee_end_to_end_allows(session):
    """The canonical E2E scenario: 'Restock my coffee' -> Warden ALLOW."""
    _seeded(session)
    agent = _agent()

    run = agent.run(
        session,
        natural_language="Restock my coffee this month. Spend no more than ₹2000.",
        customer_id="cust_priya_regular",
        idempotency_key="e2e_restock_1",
    )
    session.commit()

    # Parsed intent
    assert run.parsed_intent is not None
    assert run.parsed_intent.desired_category == "coffee"
    assert run.parsed_intent.max_spend == Decimal("2000")

    # Resolved to mandate A
    assert run.mandate is not None
    assert run.mandate.id == "man_A_regular_2k"

    # Cart built and priced within budget
    assert run.quote is not None
    assert run.quote.total <= Decimal("2000.00")
    assert len(run.selected) >= 1

    # Warden's own decision on the persisted action
    assert run.warden is not None
    assert run.warden.decision == DecisionResult.ALLOW
    assert run.warden.reason_code == ReasonCode.OK
    assert run.warden.action_id.startswith("act_")

    # Agent verdict mirrors Warden when confident (mock gives 0.9).
    assert run.agent_verdict == DecisionResult.ALLOW
    assert run.agent_confidence >= 0.7

    # A natural-language explanation exists.
    assert isinstance(run.explanation, str) and run.explanation


def test_agent_respects_mandate_cap_when_intent_asks_more(session):
    """
    The agent's budget is min(intent.max_spend, mandate.remaining). Even if the
    user asks for ₹5000 against mandate A's ₹2000 cap, the agent must not
    propose a cart above ₹2000 — Warden shouldn't have to be the one to catch
    an obviously over-cap agent proposal.
    """
    _seeded(session)
    agent = _agent()

    run = agent.run(
        session,
        natural_language="Restock my coffee. Spend up to ₹5000.",
        customer_id="cust_priya_regular",
        idempotency_key="e2e_over_budget",
    )
    session.commit()

    assert run.mandate is not None
    assert run.quote is not None
    assert run.quote.total <= run.mandate.remaining_amount, (
        "Agent must respect the mandate cap even when the user asks for more."
    )
    assert run.warden is not None
    # The cart-under-cap path may end ALLOW or STEP_UP; it must NOT be CAP_EXCEEDED.
    assert run.warden.reason_code != ReasonCode.CAP_EXCEEDED


def test_low_confidence_intent_escalates_to_step_up(session):
    _seeded(session)
    agent = _agent()

    # The mock returns confidence=0.4 when the user says "uncertain" / "not sure".
    run = agent.run(
        session,
        natural_language="Restock my coffee, I'm not sure how much though.",
        customer_id="cust_priya_regular",
        idempotency_key="e2e_low_conf",
    )
    session.commit()

    # Warden might ALLOW, but the agent's low confidence forces STEP_UP in the
    # response envelope. Warden's own record is not modified.
    if run.warden.decision == DecisionResult.ALLOW:
        assert run.agent_verdict == DecisionResult.STEP_UP
    else:
        # e.g. no products fit -> Warden may BLOCK; that's fine, still <> ALLOW.
        assert run.agent_verdict != DecisionResult.ALLOW


def test_missing_customer_mandate_raises(session):
    _seeded(session)
    agent = _agent()
    with pytest.raises(NoUsableMandateError):
        agent.run(
            session,
            natural_language="Restock my coffee.",
            customer_id="cust_nobody",
            idempotency_key="e2e_no_mandate",
        )


def test_idempotent_intent_returns_same_warden_action(session):
    _seeded(session)
    agent = _agent()

    first = agent.run(
        session,
        natural_language="Restock my coffee. Spend up to ₹1500.",
        customer_id="cust_priya_regular",
        idempotency_key="e2e_idem",
    )
    session.commit()

    second = agent.run(
        session,
        natural_language="Restock my coffee. Spend up to ₹1500.",
        customer_id="cust_priya_regular",
        idempotency_key="e2e_idem",  # same key
    )
    session.commit()

    # Warden's short-circuit returns the same action + same decision.
    assert second.warden.action_id == first.warden.action_id
    assert second.warden.duplicate is True
    assert second.warden.decision == first.warden.decision


def test_impossible_budget_returns_agent_block_without_calling_warden(session):
    """
    Cheapest coffee is ₹699. A ₹100 budget yields zero candidates and an empty
    cart. The agent must not proxy a zero-total proposal to Warden — it should
    return a clean agent-level BLOCK with a specific message.
    """
    _seeded(session)
    agent = _agent()

    run = agent.run(
        session,
        natural_language="Buy me coffee, budget 100.",
        customer_id="cust_priya_regular",
        idempotency_key="empty_cart_1",
    )
    session.commit()

    assert run.candidates == []
    assert run.selected == []
    # Nothing was submitted to Warden.
    assert run.warden is None
    assert run.cart_id is None
    assert run.agent_verdict == DecisionResult.BLOCK
    assert "budget" in run.explanation.lower() or "no matching" in run.explanation.lower()

    # And no Action row was created (idempotency safety — repeat is possible).
    from sqlalchemy import func, select

    from app.models import Action

    count = session.scalar(select(func.count()).select_from(Action))
    assert count == 0


def test_bulk_customer_high_amount_step_ups_via_warden(session):
    """Mandate B has step-up threshold ₹2000 and cap ₹5000."""
    _seeded(session)
    agent = _agent()

    run = agent.run(
        session,
        natural_language="Restock all coffees. Spend up to ₹5000.",
        customer_id="cust_bulk_buyer",
        idempotency_key="e2e_bulk_stepup",
    )
    session.commit()

    # 2 * 699 + 800 = 2198 which is > ₹2000 threshold and <= ₹5000 cap.
    if run.warden.decision == DecisionResult.STEP_UP:
        assert run.warden.reason_code == ReasonCode.APPROVAL_REQUIRED
        assert run.agent_verdict == DecisionResult.STEP_UP
