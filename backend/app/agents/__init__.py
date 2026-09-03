"""
AI Buyer Agent + Explainer.

ARCHITECTURAL RULE: nothing in this package may authorize a payment. The agent
gathers context, proposes a cart, and hands the typed proposal to Warden. The
Explainer only reads decisions. Neither one may bypass or mutate a Warden
decision.
"""

from app.agents.buyer import (
    AgentError,
    AgentRun,
    BuyerAgent,
    NoUsableMandateError,
    ParsedIntent,
    SelectedItem,
)
from app.agents.explainer import DecisionExplanation, Explainer
from app.agents.llm_client import (
    AnthropicLLMClient,
    LLMClient,
    MockLLMClient,
    get_llm_client,
)
from app.agents.tools import (
    CartLine,
    MandateView,
    ProductView,
    Quote,
    check_mandate,
    find_active_mandate_for_customer,
    get_product,
    quote_cart,
    search_catalog,
)

__all__ = [
    "AgentError",
    "AgentRun",
    "AnthropicLLMClient",
    "BuyerAgent",
    "CartLine",
    "DecisionExplanation",
    "Explainer",
    "LLMClient",
    "MandateView",
    "MockLLMClient",
    "NoUsableMandateError",
    "ParsedIntent",
    "ProductView",
    "Quote",
    "SelectedItem",
    "check_mandate",
    "find_active_mandate_for_customer",
    "get_llm_client",
    "get_product",
    "quote_cart",
    "search_catalog",
]
