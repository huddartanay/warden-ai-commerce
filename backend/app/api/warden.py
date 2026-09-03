"""Warden HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.warden import (
    ActionDetail,
    ActionOut,
    CheckResultOut,
    DecisionOut,
    DecisionResponse,
    EvaluateRequest,
    MandateOut,
)
from app.warden.coordinator import (
    ActionNotFoundError,
    InvalidActionStateError,
    MandateNotFoundError,
    approve_step_up,
    evaluate_proposal,
    revoke_mandate,
)
from app.warden.policies import Proposal

router = APIRouter(prefix="/warden", tags=["warden"])


def _to_proposal(body: EvaluateRequest) -> Proposal:
    return Proposal(
        mandate_id=body.mandate_id,
        customer_id=body.customer_id,
        merchant_id=body.merchant_id,
        cart_id=body.cart_id,
        amount=body.amount,
        currency=body.currency,
        category=body.category,
        quoted_price=body.quoted_price,
        current_price=body.current_price,
        idempotency_key=body.idempotency_key,
        action_id=body.action_id,
    )


@router.post("/evaluate", response_model=DecisionResponse)
def evaluate_endpoint(body: EvaluateRequest, db: Session = Depends(get_db)) -> DecisionResponse:
    proposal = _to_proposal(body)
    outcome = evaluate_proposal(db, proposal)
    db.commit()

    return DecisionResponse(
        action_id=outcome.action_id,
        decision=outcome.decision,
        reason_code=outcome.reason_code,
        explanation=outcome.explanation,
        checks_performed=[
            CheckResultOut(
                name=c.name,
                ok=c.ok,
                verdict=c.verdict,
                reason_code=c.reason_code,
                detail=c.detail,
            )
            for c in outcome.checks
        ],
        duplicate=outcome.duplicate,
    )


@router.post("/approve/{action_id}", response_model=ActionOut)
def approve_endpoint(action_id: str, db: Session = Depends(get_db)) -> ActionOut:
    try:
        action = approve_step_up(db, action_id)
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MandateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidActionStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    db.commit()
    db.refresh(action)
    return ActionOut.model_validate(action)


@router.post("/revoke-mandate/{mandate_id}", response_model=MandateOut)
def revoke_endpoint(mandate_id: str, db: Session = Depends(get_db)) -> MandateOut:
    try:
        mandate = revoke_mandate(db, mandate_id)
    except MandateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    db.commit()
    db.refresh(mandate)
    return MandateOut.model_validate(mandate)


@router.get("/mandate/{mandate_id}", response_model=MandateOut)
def get_mandate_endpoint(mandate_id: str, db: Session = Depends(get_db)) -> MandateOut:
    from app.models import Mandate  # local to avoid cycles at import time

    mandate = db.get(Mandate, mandate_id)
    if mandate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mandate {mandate_id} not found.",
        )
    return MandateOut.model_validate(mandate)


@router.get("/action/{action_id}", response_model=ActionDetail)
def get_action_endpoint(action_id: str, db: Session = Depends(get_db)) -> ActionDetail:
    from sqlalchemy import select

    from app.models import Action, Decision

    action = db.get(Action, action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found.",
        )
    decision = db.execute(
        select(Decision).where(Decision.action_id == action_id)
    ).scalar_one_or_none()

    return ActionDetail(
        action=ActionOut.model_validate(action),
        decision=DecisionOut.model_validate(decision) if decision else None,
    )
