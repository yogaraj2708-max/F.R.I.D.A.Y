"""
F.R.I.D.A.Y. 3.0 — Context Subsystem Package
Provides gated desktop context inspection (active window, process, clipboard, screen)
under strict user permissions.
"""

from friday_core.context.models import (
    ContextPermission,
    ContextPermissionError,
    DesktopContext
)
from friday_core.context.manager import (
    ContextManager,
    context_manager
)

from friday_core.context.budget import (
    ContextBudgetManager,
    ContextBudgetResult,
    context_budget_manager,
    DEFAULT_MODEL_CONTEXT_LIMIT
)
from friday_core.context.graphify_retriever import (
    GraphifyIndexRetriever,
    graphify_retriever,
    is_graphify_artifact,
    GRAPHIFY_ARTIFACT_NAMES
)

__all__ = [
    "ContextPermission",
    "ContextPermissionError",
    "DesktopContext",
    "ContextManager",
    "context_manager",
    "ContextBudgetManager",
    "ContextBudgetResult",
    "context_budget_manager",
    "DEFAULT_MODEL_CONTEXT_LIMIT",
    "GraphifyIndexRetriever",
    "graphify_retriever",
    "is_graphify_artifact",
    "GRAPHIFY_ARTIFACT_NAMES"
]
