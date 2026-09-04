"""
SQLAlchemy ORM models for Warden.

Importing this package registers every model class on the shared
`app.db.Base.metadata`, so downstream code can rely on
`Base.metadata.create_all(engine)` and Alembic autogenerate diffing the full
schema.
"""

from app.models.action import Action
from app.models.agent_credential import AgentCredential
from app.models.audit import AuditLog
from app.models.cart import Cart
from app.models.catalog_item import CatalogItem
from app.models.decision import Decision
from app.models.enums import (
    ActionStatus,
    ActionType,
    DecisionResult,
    MandateStatus,
    ReasonCode,
    ResolutionStatus,
)
from app.models.mandate import Mandate
from app.models.merchant import Merchant
from app.models.razorpay_ref import RazorpayRef
from app.models.resolution import Resolution

__all__ = [
    "Action",
    "ActionStatus",
    "ActionType",
    "AgentCredential",
    "AuditLog",
    "Cart",
    "CatalogItem",
    "Decision",
    "DecisionResult",
    "Mandate",
    "MandateStatus",
    "Merchant",
    "RazorpayRef",
    "ReasonCode",
    "Resolution",
    "ResolutionStatus",
]
