"""
AI Buyer Agent.

Scripted pipeline (Python orchestration + two focused LLM calls):

    natural language intent
        -> parse_intent (LLM)
        -> resolve mandate (Python)
        -> search_catalog (Python)
        -> select_products (LLM)
        -> quote_cart (Python)
        -> persist Cart (Python)
        -> Warden.evaluate_proposal (Python)

Guardrails:
  - Nothing here mutates a mandate's spend/counters or calls Razorpay.
  - Warden's authorization decision is untouched. The agent may only add its
    own STEP_UP escalation on top when its confidence is below the threshold.
  - If the resolved mandate is missing / not usable, we still forward a
    proposal to Warden so it can BLOCK deterministically with the right
    reason code (no shortcut BLOCKs from the agent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Action, Cart, Decision, MandateStatus
from app.models.enums import DecisionResult, ReasonCode
from app.agents.llm_client import LLMClient, get_llm_client
from app.agents.tools import (
    MandateView,
    ProductView,
    Quote,
    check_mandate,
    find_active_mandate_for_customer,
    quote_cart,
    search_catalog,
)
from app.warden import (
    CheckResult,
    Proposal,
    WardenOutcome,
    evaluate_proposal,
)


# ---- Public shape returned to the API ---------------------------------------


@dataclass
class ParsedIntent:
    desired_category: str
    max_spend: Decimal | None
    quantity_hint: int | None
    urgency: str
    confidence: float
    rationale: str

    def to_dict(self) -> dict:
        return {
            "desired_category": self.desired_category,
            "max_spend": str(self.max_spend) if self.max_spend is not None else None,
            "quantity_hint": self.quantity_hint,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class SelectedItem:
    catalog_item_id: str
    quantity: int
    unit_price: Decimal

    def to_dict(self) -> dict:
        return {
            "catalog_item_id": self.catalog_item_id,
            "quantity": self.quantity,
            "unit_price": str(self.unit_price),
        }


@dataclass
class AgentRun:
    intent_text: str
    parsed_intent: ParsedIntent | None
    mandate: MandateView | None
    candidates: list[ProductView] = field(default_factory=list)
    selected: list[SelectedItem] = field(default_factory=list)
    quote: Quote | None = None
    cart_id: str | None = None
    warden: WardenOutcome | None = None
    agent_confidence: float = 0.0
    agent_verdict: DecisionResult = DecisionResult.BLOCK
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "intent_text": self.intent_text,
            "parsed_intent": self.parsed_intent.to_dict() if self.parsed_intent else None,
            "mandate": self.mandate.to_dict() if self.mandate else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "selected": [s.to_dict() for s in self.selected],
            "quote": self.quote.to_dict() if self.quote else None,
            "cart_id": self.cart_id,
            "warden": _warden_to_dict(self.warden),
            "agent_confidence": self.agent_confidence,
            "agent_verdict": self.agent_verdict.value,
            "explanation": self.explanation,
        }


def _warden_to_dict(w: WardenOutcome | None) -> dict | None:
    if w is None:
        return None
    return {
        "action_id": w.action_id,
        "decision": w.decision.value,
        "reason_code": w.reason_code.value,
        "explanation": w.explanation,
        "duplicate": w.duplicate,
        "checks_performed": [
            {
                "name": c.name,
                "ok": c.ok,
                "verdict": c.verdict,
                "reason_code": c.reason_code.value if c.reason_code else None,
                "detail": c.detail,
            }
            for c in w.checks
        ],
    }


# ---- Errors -----------------------------------------------------------------


class AgentError(Exception):
    pass


class NoUsableMandateError(AgentError):
    pass


# ---- Pipeline ---------------------------------------------------------------


class BuyerAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or get_llm_client()
        self._threshold = float(get_settings().agent_confidence_threshold)

    # -- individual steps ----------------------------------------------------

    def parse_intent(
        self, natural_language: str, mandate: MandateView | None
    ) -> ParsedIntent:
        allowed_categories = mandate.allowed_categories if mandate else []
        system = (
            "You are the intent parser of the Warden AI Buyer Agent. "
            "Given a customer's natural-language purchase request and the "
            "customer's mandate, extract a structured intent.\n"
            "Schema: {desired_category: string, max_spend: string|null, "
            "quantity_hint: int|null, urgency: 'high'|'normal'|'low', "
            "confidence: number in [0,1], rationale: string}. "
            "desired_category MUST be one of the mandate's allowed_categories "
            "when they are provided."
        )
        user_msg = (
            f"Customer intent: {natural_language!r}\n"
            f"Allowed categories on this mandate: {allowed_categories}\n"
            "Extract the intent as JSON."
        )
        raw = self._llm.complete_json(
            system=system,
            user=user_msg,
            purpose="parse_intent",
            context={"allowed_categories": allowed_categories},
        )
        return ParsedIntent(
            desired_category=str(raw.get("desired_category") or ""),
            max_spend=(
                Decimal(str(raw["max_spend"])) if raw.get("max_spend") not in (None, "") else None
            ),
            quantity_hint=(int(raw["quantity_hint"]) if raw.get("quantity_hint") else None),
            urgency=str(raw.get("urgency") or "normal"),
            confidence=float(raw.get("confidence") or 0.0),
            rationale=str(raw.get("rationale") or ""),
        )

    def select_products(
        self,
        candidates: list[ProductView],
        *,
        budget: Decimal,
        quantity_hint: int | None,
    ) -> tuple[list[SelectedItem], float, str]:
        system = (
            "You are the product selector for the Warden AI Buyer Agent. "
            "Choose which catalog items and quantities to include in a cart "
            "so that the total does not exceed the budget. Respond as JSON: "
            "{selected_items: [{catalog_item_id, quantity, unit_price}], "
            "confidence: number in [0,1], rationale: string}."
        )
        user_msg = (
            "Candidates:\n"
            + "\n".join(
                f"- {c.id}: {c.name} ({c.category}) ₹{c.price}" for c in candidates
            )
            + f"\n\nBudget: ₹{budget}\nQuantity hint: {quantity_hint}"
        )
        raw = self._llm.complete_json(
            system=system,
            user=user_msg,
            purpose="select_products",
            context={
                "candidates": [c.to_dict() for c in candidates],
                "budget": str(budget),
                "quantity_hint": quantity_hint,
            },
        )
        items: list[SelectedItem] = []
        for it in raw.get("selected_items", []) or []:
            try:
                items.append(
                    SelectedItem(
                        catalog_item_id=str(it["catalog_item_id"]),
                        quantity=int(it.get("quantity") or 1),
                        unit_price=Decimal(str(it.get("unit_price") or "0")),
                    )
                )
            except Exception:
                continue
        return (
            items,
            float(raw.get("confidence") or 0.0),
            str(raw.get("rationale") or ""),
        )

    # -- full pipeline -------------------------------------------------------

    def run(
        self,
        session: Session,
        *,
        natural_language: str,
        customer_id: str,
        mandate_id: str | None = None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> AgentRun:
        when = now or datetime.now(tz=timezone.utc)

        run = AgentRun(intent_text=natural_language, parsed_intent=None, mandate=None)

        # 0) Idempotency short-circuit. If the same key has been processed,
        # skip the whole pipeline (no LLM, no cart rebuild) and return the
        # original decision. Mirrors Warden's own idempotency semantics but
        # further up the stack so we never touch a mandate whose state may
        # have moved on since the original decision.
        existing = session.execute(
            select(Action).where(Action.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            existing_decision = session.execute(
                select(Decision).where(Decision.action_id == existing.id)
            ).scalar_one_or_none()
            outcome = _outcome_from_persisted(existing, existing_decision)
            run.warden = outcome
            run.agent_verdict = _combine_verdicts(
                warden=outcome.decision,
                agent_confidence=1.0,  # cached decision — no new confidence
                threshold=self._threshold,
            )
            run.explanation = (
                f"Duplicate of a previous request; returning the original "
                f"{outcome.decision.value} decision."
            )
            run.cart_id = existing.cart_id
            return run

        # 1) Resolve mandate.
        mandate = _resolve_mandate(session, mandate_id=mandate_id, customer_id=customer_id)
        run.mandate = mandate
        if mandate is None:
            raise NoUsableMandateError(
                f"No usable mandate for customer {customer_id} "
                f"(mandate_id={mandate_id!r}). Provide an ACTIVE mandate."
            )

        # 2) Parse intent (LLM).
        parsed = self.parse_intent(natural_language, mandate)
        run.parsed_intent = parsed

        # 3) Search catalog.
        # Budget = min(intent.max_spend if any, mandate.remaining_amount).
        budget = mandate.remaining_amount
        if parsed.max_spend is not None:
            budget = min(budget, parsed.max_spend)

        # Category must be inside allowed_categories to have any chance of ALLOW.
        # We still search that category; if empty, we let Warden BLOCK.
        cat_to_use = parsed.desired_category
        candidates = search_catalog(
            session,
            merchant_id=mandate.merchant_id,
            category=cat_to_use,
            max_price=budget if budget > 0 else None,
            available_only=True,
        )
        run.candidates = candidates

        # 4) Select products (LLM). Skip if no candidates and let Warden decide.
        if candidates:
            selected, sel_confidence, _ = self.select_products(
                candidates, budget=budget, quantity_hint=parsed.quantity_hint
            )
        else:
            selected, sel_confidence = [], 0.2
        run.selected = selected

        # 5) Quote.
        quote = quote_cart(
            session,
            selections=[
                {"catalog_item_id": s.catalog_item_id, "quantity": s.quantity}
                for s in selected
            ],
        )
        run.quote = quote

        # 5a) No-cart short-circuit.
        # If the LLM found no candidate that fits (empty selection, or every
        # line got dropped), there is no financial action to authorize. Return
        # a clean agent-level BLOCK rather than sending a zero-total proposal
        # to Warden (which would rightly BLOCK on PRICE_DRIFT — quoted_price=0
        # trips its own guard — but for a misleading reason).
        if not selected or quote.total <= 0:
            run.agent_confidence = min(parsed.confidence, sel_confidence)
            run.agent_verdict = DecisionResult.BLOCK
            run.warden = None
            run.cart_id = None
            if not candidates:
                run.explanation = (
                    "No matching products under this mandate. "
                    f"Nothing in category '{parsed.desired_category}' fits within "
                    f"budget ₹{budget}."
                )
            else:
                run.explanation = (
                    "The AI buyer could not assemble a cart within the "
                    f"₹{budget} budget while respecting the mandate."
                )
            return run

        # 6) Persist Cart.
        period = when.strftime("%Y-%m")
        cart_id = f"cart_{uuid4().hex[:20]}"
        cart_row = Cart(
            id=cart_id,
            mandate_id=mandate.id,
            merchant_id=mandate.merchant_id,
            items=[line.to_dict() for line in quote.items],
            total_amount=quote.total,
            currency=quote.currency or mandate.currency,
            period=period,
            created_at=when,
        )
        session.add(cart_row)
        session.flush()
        run.cart_id = cart_id

        # 7) Assemble the Proposal for Warden.
        #    quoted_price: what the agent thinks the cart totals.
        #    current_price: recomputed from catalog right now (same total unless
        #    the price drifted between candidate lookup and now).
        current_quote = quote_cart(
            session,
            selections=[
                {"catalog_item_id": s.catalog_item_id, "quantity": s.quantity}
                for s in selected
            ],
        )
        proposal = Proposal(
            mandate_id=mandate.id,
            customer_id=mandate.customer_id,
            merchant_id=mandate.merchant_id,
            cart_id=cart_id,
            amount=quote.total,
            currency=quote.currency or mandate.currency,
            category=parsed.desired_category,
            quoted_price=quote.total,
            current_price=current_quote.total,
            idempotency_key=idempotency_key,
        )

        # 8) Warden decides.
        outcome = evaluate_proposal(session, proposal, now=when)
        run.warden = outcome

        # 9) Compute agent-level verdict.
        run.agent_confidence = min(parsed.confidence, sel_confidence)
        run.agent_verdict = _combine_verdicts(
            warden=outcome.decision,
            agent_confidence=run.agent_confidence,
            threshold=self._threshold,
        )

        # 10) Explanation for the response envelope (LLM/template).
        exp = self._llm.complete_json(
            system="You explain a Warden decision in one sentence.",
            user=(
                f"Result: {outcome.decision.value}\n"
                f"Reason: {outcome.reason_code.value}\n"
                f"Detail: {outcome.explanation}"
            ),
            purpose="explain",
            context={
                "result": outcome.decision.value,
                "reason_code": outcome.reason_code.value,
                "explanation": outcome.explanation,
            },
        )
        run.explanation = str(exp.get("natural_language") or outcome.explanation)

        return run


# ---- Helpers ----------------------------------------------------------------


def _resolve_mandate(
    session: Session, *, mandate_id: str | None, customer_id: str
) -> MandateView | None:
    if mandate_id:
        return check_mandate(session, mandate_id)
    return find_active_mandate_for_customer(session, customer_id=customer_id)


def _outcome_from_persisted(action: Action, decision: Decision | None) -> WardenOutcome:
    """Rebuild a WardenOutcome from persisted rows for the idempotency path."""
    if decision is None:
        return WardenOutcome(
            action_id=action.id,
            decision=DecisionResult.BLOCK,
            reason_code=ReasonCode.SYSTEM_ERROR,
            explanation="Existing action has no recorded decision.",
            duplicate=True,
        )
    return WardenOutcome(
        action_id=action.id,
        decision=decision.result,
        reason_code=decision.reason_code,
        explanation=decision.explanation,
        checks=[],
        duplicate=True,
    )


def _combine_verdicts(
    *, warden: DecisionResult, agent_confidence: float, threshold: float
) -> DecisionResult:
    """
    Agent verdict layered on top of Warden.

      Warden = BLOCK     -> BLOCK (Warden always wins on the safe side)
      Warden = STEP_UP   -> STEP_UP
      Warden = ALLOW     -> STEP_UP if agent_confidence < threshold, else ALLOW

    Warden's own persisted decision is never modified.
    """
    if warden == DecisionResult.BLOCK:
        return DecisionResult.BLOCK
    if warden == DecisionResult.STEP_UP:
        return DecisionResult.STEP_UP
    if agent_confidence < threshold:
        return DecisionResult.STEP_UP
    return DecisionResult.ALLOW
