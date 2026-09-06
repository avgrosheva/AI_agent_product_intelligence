"""Import every model module once so Base.metadata is fully populated
(needed for Alembic autogenerate and for relationship() string resolution).
"""

from backend.app.models.base import Base
from backend.app.models.core import Experiment, Product, User
from backend.app.models.outcomes import Evaluation, FailureLabel, ProductEvent, Recommendation
from backend.app.models.sessions import AgentAction, Message, Session, ToolCall

__all__ = [
    "Base",
    "User",
    "Product",
    "Experiment",
    "Session",
    "Message",
    "AgentAction",
    "ToolCall",
    "Recommendation",
    "ProductEvent",
    "Evaluation",
    "FailureLabel",
]
