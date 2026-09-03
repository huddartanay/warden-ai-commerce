"""
Explainer.

Takes a Warden decision (result + reason_code + short explanation) and
returns a natural-language sentence. Read-only — the decision itself is not
modified in the DB or in the returned payload.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm_client import LLMClient, get_llm_client
from app.models import Action, Decision
from app.models.enums import DecisionResult, ReasonCode


@dataclass
class DecisionExplanation:
    action_id: str | None
    result: DecisionResult
    reason_code: ReasonCode
    natural_language: str
    warden_explanation: str

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "result": self.result.value,
            "reason_code": self.reason_code.value,
            "natural_language": self.natural_language,
            "warden_explanation": self.warden_explanation,
        }


class Explainer:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or get_llm_client()

    def explain_decision(
        self,
        *,
        result: DecisionResult,
        reason_code: ReasonCode,
        warden_explanation: str,
        action_id: str | None = None,
    ) -> DecisionExplanation:
        system = (
            "You explain a Warden decision to a merchant in ONE plain sentence. "
            "Do not invent facts. Do not change the decision. If it was blocked, "
            "clearly state why."
        )
        user = (
            f"Warden result: {result.value}\n"
            f"Reason code: {reason_code.value}\n"
            f"Short explanation: {warden_explanation}"
        )
        raw = self._llm.complete_json(
            system=system,
            user=user,
            purpose="explain",
            context={
                "result": result.value,
                "reason_code": reason_code.value,
                "explanation": warden_explanation,
            },
        )
        nl = str(raw.get("natural_language") or warden_explanation)
        return DecisionExplanation(
            action_id=action_id,
            result=result,
            reason_code=reason_code,
            natural_language=nl,
            warden_explanation=warden_explanation,
        )

    def explain_action(self, session: Session, action_id: str) -> DecisionExplanation | None:
        action = session.get(Action, action_id)
        if action is None:
            return None
        decision = session.execute(
            select(Decision).where(Decision.action_id == action_id)
        ).scalar_one_or_none()
        if decision is None:
            return None
        return self.explain_decision(
            result=decision.result,
            reason_code=decision.reason_code,
            warden_explanation=decision.explanation,
            action_id=action.id,
        )
