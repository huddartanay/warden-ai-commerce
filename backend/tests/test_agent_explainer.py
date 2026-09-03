"""Explainer tests — read-only decisions become natural language."""

from __future__ import annotations

from decimal import Decimal

from app.agents import BuyerAgent, Explainer, MockLLMClient
from app.models.enums import DecisionResult, ReasonCode
from app.seed import seed_data


def test_explainer_produces_expected_template_for_cap_exceeded():
    exp = Explainer(llm=MockLLMClient()).explain_decision(
        result=DecisionResult.BLOCK,
        reason_code=ReasonCode.CAP_EXCEEDED,
        warden_explanation="₹3499 > remaining ₹2000",
    )
    assert exp.result == DecisionResult.BLOCK
    assert exp.reason_code == ReasonCode.CAP_EXCEEDED
    assert "spending limit" in exp.natural_language.lower()
    # Warden explanation is preserved unchanged.
    assert exp.warden_explanation == "₹3499 > remaining ₹2000"


def test_explainer_handles_every_reason_code():
    """The mock has a template for every reason we ship."""
    ex = Explainer(llm=MockLLMClient())
    for code in ReasonCode:
        exp = ex.explain_decision(
            result=DecisionResult.BLOCK if code != ReasonCode.OK else DecisionResult.ALLOW,
            reason_code=code,
            warden_explanation="test",
        )
        assert isinstance(exp.natural_language, str) and exp.natural_language
        assert exp.reason_code == code


def test_explainer_does_not_mutate_the_stored_decision(session):
    """Sanity: explain_action reads from the DB, does not touch the row."""
    seed_data(session)
    session.commit()

    agent = BuyerAgent(llm=MockLLMClient())
    run = agent.run(
        session,
        natural_language="Restock my coffee. Spend up to ₹1500.",
        customer_id="cust_priya_regular",
        idempotency_key="explain_1",
    )
    session.commit()

    from sqlalchemy import select

    from app.models import Decision

    before = session.execute(select(Decision).where(Decision.action_id == run.warden.action_id)).scalar_one()
    before_snapshot = (before.result, before.reason_code, before.explanation)

    Explainer(llm=MockLLMClient()).explain_action(session, run.warden.action_id)

    after = session.execute(select(Decision).where(Decision.action_id == run.warden.action_id)).scalar_one()
    after_snapshot = (after.result, after.reason_code, after.explanation)

    assert before_snapshot == after_snapshot


def test_explain_action_returns_none_for_missing(session):
    seed_data(session)
    session.commit()
    assert Explainer(llm=MockLLMClient()).explain_action(session, "act_ghost") is None
