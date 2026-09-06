"""Python enums backing the Postgres ENUM types used across DATA_MODEL.md.

Kept as plain str-Enums (not SQLAlchemy's native Enum-of-Enum niceties) so
the same classes can be imported by the generator (datagen/) without any
SQLAlchemy/DB dependency.
"""

from enum import Enum


class Platform(str, Enum):
    web = "web"
    ios = "ios"
    android = "android"


class DeviceTier(str, Enum):
    low = "low"
    mid = "mid"
    high = "high"


class Locale(str, Enum):
    ru_ru = "ru-RU"
    en_us = "en-US"


class Persona(str, Enum):
    budget = "budget"
    mainstream = "mainstream"
    power_user = "power_user"
    gift_buyer = "gift_buyer"


class ProductCategory(str, Enum):
    laptop = "laptop"
    monitor = "monitor"
    accessory = "accessory"


class CpuTier(str, Enum):
    entry = "entry"
    mid = "mid"
    high = "high"


class GpuTier(str, Enum):
    integrated = "integrated"
    entry_discrete = "entry_discrete"
    high_discrete = "high_discrete"


class ExperimentStatus(str, Enum):
    running = "running"
    completed = "completed"


class AgentVersion(str, Enum):
    v1 = "v1"
    v2 = "v2"


class SessionOutcome(str, Enum):
    purchase = "purchase"
    add_to_cart_only = "add_to_cart_only"
    abandoned = "abandoned"
    no_action = "no_action"


class MessageSender(str, Enum):
    user = "user"
    agent = "agent"


class ActionType(str, Enum):
    understand_query = "understand_query"
    search = "search"
    filter = "filter"
    clarify = "clarify"
    recommend = "recommend"
    answer = "answer"
    abandon_flow = "abandon_flow"


class ToolName(str, Enum):
    search_products = "search_products"
    filter_products = "filter_products"
    get_product_details = "get_product_details"
    compare_products = "compare_products"


class ToolErrorType(str, Enum):
    none = "none"
    timeout = "timeout"
    empty_result = "empty_result"
    invalid_args = "invalid_args"


class ProductEventType(str, Enum):
    impression = "impression"
    click = "click"
    add_to_cart = "add_to_cart"
    purchase = "purchase"
    remove_from_cart = "remove_from_cart"


class EvalType(str, Enum):
    offline_task_success = "offline_task_success"
    constraint_satisfaction = "constraint_satisfaction"
    answer_faithfulness = "answer_faithfulness"


class Evaluator(str, Enum):
    rule_based = "rule_based"
    llm = "llm"


class FailureMode(str, Enum):
    unnecessary_clarification = "unnecessary_clarification"
    wrong_constraint_interpretation = "wrong_constraint_interpretation"
    poor_ranking = "poor_ranking"
    wrong_tool_selection = "wrong_tool_selection"
    unsupported_product_claim = "unsupported_product_claim"
    retrieval_failure = "retrieval_failure"
    other = "other"
    none = "none"


class FailureLabelSource(str, Enum):
    """Single fixed value in the application database (DATA_MODEL.md SS3.11).

    Ground-truth failure labels never populate the app's failure_labels
    table; they exist only in validation_ground_truth.parquet.
    """

    llm_classifier = "llm_classifier"
