"""
LLM abstraction — real Anthropic client, deterministic mock, and a factory
that chooses between them so the app runs offline for hackathon demos.

Never called from Warden — this whole package is one directory over.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Protocol

from app.config import get_settings


# ---- Contract ---------------------------------------------------------------


class LLMClient(Protocol):
    """The minimum surface the agent needs from an LLM."""

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        purpose: str,  # tag ("parse_intent" | "select_products" | "explain") used by mock
        context: dict[str, Any] | None = None,  # supplied to the mock for deterministic branching
    ) -> dict[str, Any]:
        """Ask the LLM for a JSON object. Returns a parsed dict."""


# ---- Real Anthropic client --------------------------------------------------


class AnthropicLLMClient:
    """Wraps `anthropic.Anthropic` and forces a JSON reply via prompting."""

    def __init__(self, *, api_key: str, model: str) -> None:
        # Import lazily so the SDK is only required in live mode.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        purpose: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        forced_system = (
            system
            + "\n\nRespond with a single JSON object matching the requested schema. "
            "Return JSON only, with no prose, no markdown fences, no commentary."
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=forced_system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return _parse_json_blob(text)


def _parse_json_blob(text: str) -> dict[str, Any]:
    """Extract a JSON object from an LLM reply that may contain stray text."""
    text = text.strip()
    if not text:
        raise ValueError("Empty LLM response")
    # First try straight parse.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m is None:
        raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")
    return json.loads(m.group(0))


# ---- Deterministic mock -----------------------------------------------------


class MockLLMClient:
    """
    Deterministic mock. Same inputs -> same JSON. Used for tests and offline demos.

    Branching lives in one place per `purpose`.
    """

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        purpose: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        if purpose == "parse_intent":
            return self._parse_intent(user, ctx)
        if purpose == "select_products":
            return self._select_products(user, ctx)
        if purpose == "explain":
            return self._explain(user, ctx)
        raise ValueError(f"MockLLMClient: unknown purpose {purpose!r}")

    # -- parse_intent --------------------------------------------------------

    _CATEGORY_KEYWORDS: dict[str, list[str]] = {
        "coffee": ["coffee", "espresso", "brew", "latte"],
        "beans": ["beans", "grinder"],
        "appliance": ["machine", "appliance", "grinder"],
    }

    def _parse_intent(self, user: str, ctx: dict[str, Any]) -> dict[str, Any]:
        text = user.lower()

        # Category detection.
        allowed = ctx.get("allowed_categories") or []
        picked: str | None = None
        for cat in allowed or self._CATEGORY_KEYWORDS.keys():
            keywords = self._CATEGORY_KEYWORDS.get(cat, [cat])
            if any(kw in text for kw in keywords):
                picked = cat
                break
        if picked is None and allowed:
            picked = allowed[0]  # fall back to the first allowed category
        elif picked is None:
            picked = "coffee"

        # Spend hint. Match "₹2000", "Rs 2000", "2,000 rupees", "no more than 2000".
        spend_match = re.search(
            r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]{1,7})(?:\s*(?:rupees|inr))?",
            text,
        )
        max_spend: Decimal | None = None
        if spend_match:
            raw = spend_match.group(1).replace(",", "")
            try:
                max_spend = Decimal(raw)
            except Exception:
                max_spend = None

        # Quantity hint.
        qty_match = re.search(r"\b(\d+)\s*(?:units?|bags?|packs?|boxes?)\b", text)
        quantity_hint = int(qty_match.group(1)) if qty_match else None

        # Confidence: high unless the user says something we normally flag.
        confidence = 0.9
        if "uncertain" in text or "not sure" in text or "help me decide" in text:
            confidence = 0.4

        return {
            "desired_category": picked,
            "max_spend": str(max_spend) if max_spend is not None else None,
            "quantity_hint": quantity_hint,
            "urgency": "high" if "asap" in text or "urgent" in text else "normal",
            "confidence": confidence,
            "rationale": f"Detected category {picked!r} from intent text.",
        }

    # -- select_products -----------------------------------------------------

    def _select_products(self, user: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """
        Greedy: sort candidates by price ascending, add until we would exceed
        the budget. Never picks zero items if any candidate fits.
        """
        candidates: list[dict[str, Any]] = ctx.get("candidates") or []
        budget = Decimal(str(ctx.get("budget") or "0"))
        quantity_hint: int | None = ctx.get("quantity_hint")

        # Deterministic order: cheapest first, then by name so ties break stably.
        sorted_candidates = sorted(
            candidates, key=lambda c: (Decimal(str(c["price"])), c["name"])
        )

        selected: list[dict[str, Any]] = []
        running = Decimal("0")
        for c in sorted_candidates:
            price = Decimal(str(c["price"]))
            qty = 1
            if quantity_hint and len(selected) == 0:
                qty = max(1, quantity_hint)
            line_total = price * qty
            if budget > 0 and running + line_total > budget:
                # try qty 1 if we started with a hint
                if qty > 1:
                    line_total = price
                    qty = 1
                    if budget > 0 and running + line_total > budget:
                        continue
                else:
                    continue
            selected.append({
                "catalog_item_id": c["id"],
                "quantity": qty,
                "unit_price": str(price),
            })
            running += line_total

        confidence = 0.9 if selected else 0.2
        return {
            "selected_items": selected,
            "confidence": confidence,
            "rationale": (
                f"Greedy selection under budget ₹{budget}: picked "
                f"{len(selected)} item(s), total ₹{running}."
            ),
        }

    # -- explain -------------------------------------------------------------

    _TEMPLATES: dict[str, str] = {
        "OK": "This purchase was approved because it satisfies every rule on the customer's mandate.",
        "CAP_EXCEEDED": "This purchase was blocked because the cart exceeds the customer's remaining spending limit.",
        "WINDOW_EXHAUSTED": "This purchase was blocked because the customer has already used all transactions allowed for the current period.",
        "OUT_OF_SCOPE_CATEGORY": "This purchase was blocked because the requested category is not covered by the mandate.",
        "PRICE_DRIFT": "This purchase was blocked because the current merchant price has drifted from the price the AI quoted.",
        "DUPLICATE_ACTION": "This is a duplicate of a previous request; Warden returned the original decision instead of authorizing again.",
        "MANDATE_EXPIRED": "This purchase was blocked because the mandate has expired.",
        "MANDATE_REVOKED": "This purchase was blocked because the mandate has been revoked.",
        "INVALID_MANDATE": "This purchase was blocked because the mandate could not be validated for this proposal.",
        "APPROVAL_REQUIRED": "This purchase requires human approval because the amount exceeds the mandate's auto-approve threshold.",
        "SYSTEM_ERROR": "This purchase was blocked due to an internal system error.",
    }

    def _explain(self, user: str, ctx: dict[str, Any]) -> dict[str, Any]:
        reason = str(ctx.get("reason_code") or "SYSTEM_ERROR")
        result = str(ctx.get("result") or "BLOCK")
        template = self._TEMPLATES.get(reason, self._TEMPLATES["SYSTEM_ERROR"])
        return {
            "natural_language": template,
            "result": result,
            "reason_code": reason,
        }


# ---- Factory ----------------------------------------------------------------


def get_llm_client() -> LLMClient:
    """Choose an LLM client based on settings. Never raises in mock/auto modes."""
    settings = get_settings()
    mode = (settings.llm_mode or "auto").lower()

    if mode == "mock":
        return MockLLMClient()

    if mode == "live":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "WARDEN_LLM_MODE=live but ANTHROPIC_API_KEY is empty."
            )
        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key, model=settings.llm_model
        )

    # auto
    if settings.anthropic_api_key:
        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key, model=settings.llm_model
        )
    return MockLLMClient()
