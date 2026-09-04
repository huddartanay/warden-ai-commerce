"""Agent HTTP endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents import (
    BuyerAgent,
    Explainer,
    NoUsableMandateError,
    check_mandate,
    find_active_mandate_for_customer,
    get_llm_client,
    quote_cart,
    search_catalog,
)
from app.db import get_db
from app.models.enums import DecisionResult, ReasonCode
from app.schemas.agent import (
    BuildCartRequest,
    ExplainRequest,
    ExplainResponse,
    PurchaseIntentRequest,
    PurchaseIntentResponse,
    SearchRequest,
    SearchResponse,
)
from app.models.enums import ActionStatus
from app.warden import (
    Proposal,
    RazorpayError,
    evaluate_proposal,
    execute_payment,
)
from uuid import uuid4

router = APIRouter(prefix="/agent", tags=["agent"])


def _new_cart_id() -> str:
    return f"cart_{uuid4().hex[:20]}"


@router.post("/purchase-intent", response_model=PurchaseIntentResponse)
def purchase_intent(body: PurchaseIntentRequest, db: Session = Depends(get_db)) -> PurchaseIntentResponse:
    agent = BuyerAgent()  # uses get_llm_client() -> mock/live by config
    try:
        run = agent.run(
            db,
            natural_language=body.natural_language,
            customer_id=body.customer_id,
            mandate_id=body.mandate_id,
            idempotency_key=body.idempotency_key,
        )
    except NoUsableMandateError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    payment_payload: dict | None = None

    # Auto-execute Razorpay flow only when both:
    #   - the agent verdict is ALLOW (Warden ALLOWed AND confidence >= threshold)
    #   - the caller opted in (default True)
    # BLOCK / STEP_UP intentionally short-circuit: no Razorpay call.
    if (
        body.auto_execute_on_allow
        and run.agent_verdict == DecisionResult.ALLOW
        and run.warden is not None
        and run.warden.decision == DecisionResult.ALLOW
    ):
        try:
            pex = execute_payment(db, run.warden.action_id)
            payment_payload = {
                "action_id": pex.action_id,
                "action_status": pex.action_status.value,
                "order": {
                    "id": pex.order.id,
                    "ref_type": pex.order.ref_type,
                    "razorpay_id": pex.order.razorpay_id,
                    "status": pex.order.status,
                } if pex.order else None,
                "payment_link": {
                    "id": pex.payment_link.id,
                    "ref_type": pex.payment_link.ref_type,
                    "razorpay_id": pex.payment_link.razorpay_id,
                    "status": pex.payment_link.status,
                    "short_url": (pex.payment_link.raw_response or {}).get("short_url"),
                } if pex.payment_link else None,
                "duplicate": pex.duplicate,
            }
        except RazorpayError as e:
            # Payment service already wrote the failure audit + status.
            payment_payload = {"error": str(e), "action_id": run.warden.action_id}

    db.commit()

    body_dict = run.to_dict()
    body_dict["payment"] = payment_payload
    return PurchaseIntentResponse(**body_dict)


@router.post("/search", response_model=SearchResponse)
def search_endpoint(body: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    results = search_catalog(
        db,
        merchant_id=body.merchant_id,
        query=body.query,
        category=body.category,
        max_price=body.max_price,
        limit=body.limit,
    )
    return SearchResponse(
        merchant_id=body.merchant_id,
        products=[p.to_dict() for p in results],
    )


@router.post("/build-cart", response_model=PurchaseIntentResponse)
def build_cart_endpoint(body: BuildCartRequest, db: Session = Depends(get_db)) -> PurchaseIntentResponse:
    """
    Skip intent parsing / selection; caller supplies items directly. The cart
    still gets persisted and evaluated by Warden with a full audit trail.
    """
    # Resolve mandate.
    if body.mandate_id:
        mandate = check_mandate(db, body.mandate_id)
    else:
        mandate = find_active_mandate_for_customer(db, customer_id=body.customer_id)
    if mandate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No usable mandate for customer {body.customer_id}",
        )

    # Quote using current catalog prices.
    selections = [{"catalog_item_id": i.catalog_item_id, "quantity": i.quantity} for i in body.items]
    quote = quote_cart(db, selections=selections)

    # Persist Cart.
    from datetime import datetime, timezone

    from app.models import Cart

    now = datetime.now(tz=timezone.utc)
    cart_id = _new_cart_id()
    db.add(
        Cart(
            id=cart_id,
            mandate_id=mandate.id,
            merchant_id=mandate.merchant_id,
            items=[line.to_dict() for line in quote.items],
            total_amount=quote.total,
            currency=quote.currency or mandate.currency,
            period=now.strftime("%Y-%m"),
            created_at=now,
        )
    )
    db.flush()

    # Category surfaced to Warden — if the cart mixes categories, we pick the
    # first line's category and let Warden judge (allowed_categories is a set).
    category = quote.items[0].category if quote.items else "unknown"

    # For explicit build-cart we assume quoted == current unless the caller
    # supplied per-item quoted prices.
    quoted_total = quote.total
    if body.quoted_prices:
        quoted_total = Decimal("0")
        for line in quote.items:
            unit = body.quoted_prices.get(line.catalog_item_id, line.unit_price)
            quoted_total += Decimal(str(unit)) * line.quantity

    proposal = Proposal(
        mandate_id=mandate.id,
        customer_id=mandate.customer_id,
        merchant_id=mandate.merchant_id,
        cart_id=cart_id,
        amount=quote.total,
        currency=quote.currency or mandate.currency,
        category=category,
        quoted_price=quoted_total,
        current_price=quote.total,
        idempotency_key=body.idempotency_key,
    )
    outcome = evaluate_proposal(db, proposal, now=now)

    # Explainer for the response envelope.
    explainer = Explainer()
    natural = explainer.explain_decision(
        result=outcome.decision,
        reason_code=outcome.reason_code,
        warden_explanation=outcome.explanation,
        action_id=outcome.action_id,
    ).natural_language

    db.commit()

    return PurchaseIntentResponse(
        intent_text="(explicit build-cart)",
        parsed_intent=None,
        mandate=mandate.to_dict(),
        candidates=[],
        selected=[
            {
                "catalog_item_id": line.catalog_item_id,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price),
            }
            for line in quote.items
        ],
        quote=quote.to_dict(),
        cart_id=cart_id,
        warden={
            "action_id": outcome.action_id,
            "decision": outcome.decision.value,
            "reason_code": outcome.reason_code.value,
            "explanation": outcome.explanation,
            "duplicate": outcome.duplicate,
            "checks_performed": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "verdict": c.verdict,
                    "reason_code": c.reason_code.value if c.reason_code else None,
                    "detail": c.detail,
                }
                for c in outcome.checks
            ],
        },
        agent_confidence=1.0,  # explicit path — no LLM confidence involved
        agent_verdict=outcome.decision,
        explanation=natural,
    )


@router.post("/explain", response_model=ExplainResponse)
def explain_endpoint(body: ExplainRequest, db: Session = Depends(get_db)) -> ExplainResponse:
    explainer = Explainer()

    if body.action_id:
        result = explainer.explain_action(db, body.action_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Action {body.action_id} has no decision to explain.",
            )
        return ExplainResponse(**result.to_dict())

    # Explain from inline fields.
    if body.result is None or body.reason_code is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either action_id, or (result + reason_code).",
        )
    result = explainer.explain_decision(
        result=body.result,
        reason_code=body.reason_code,
        warden_explanation=body.warden_explanation or "",
    )
    return ExplainResponse(**result.to_dict())
