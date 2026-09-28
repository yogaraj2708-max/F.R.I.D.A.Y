"""
F.R.I.D.A.Y. 3.0 — Deep Research 2.0 Subsystem Exports
"""

from friday_core.research.models import (
    ResearchSource,
    KeyFinding,
    Contradiction,
    ResearchBriefing
)
from friday_core.research.decomposer import QueryDecomposer
from friday_core.research.cross_checker import SourceCrossChecker
from friday_core.research.synthesizer import DeepResearchSynthesizer
from friday_core.research.engine import DeepResearchEngine, deep_research_engine
from friday_core.research.worker import DeepResearchWorker

__all__ = [
    "ResearchSource",
    "KeyFinding",
    "Contradiction",
    "ResearchBriefing",
    "QueryDecomposer",
    "SourceCrossChecker",
    "DeepResearchSynthesizer",
    "DeepResearchEngine",
    "deep_research_engine",
    "DeepResearchWorker"
]
