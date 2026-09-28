"""
F.R.I.D.A.Y. 3.0 — Deep Research 2.0 Query Decomposer
Decomposes complex research topics into orthogonal, targeted search queries.
"""

import re
from typing import List


class QueryDecomposer:
    """
    Deconstructs high-level research queries into orthogonal sub-queries.
    """

    @classmethod
    def clean_topic(cls, raw_query: str) -> str:
        """Strips conversational noise and prefixes from research prompts."""
        pattern = r"^(?:(?:do\s+(?:a\s+)?)?deep\s+(?:web\s+)?research\s+(?:web\s+and\s+tell\s+about|web\s+about|on|about)?|research\s+(?:web\s+and\s+tell\s+about|on|about)?|tell\s+(?:me\s+)?about\s+(?:company\s+named\s+)?|deep\s+search\s+(?:on|about)?)\s*"
        cleaned = re.sub(pattern, "", raw_query, flags=re.IGNORECASE).strip()
        return cleaned or raw_query.strip()

    @classmethod
    def decompose(cls, topic: str, max_subqueries: int = 4) -> List[str]:
        """
        Generates orthogonal search angles covering overview, recent advances,
        architectural/implementation details, and limitations/challenges.
        """
        cleaned = cls.clean_topic(topic)
        if not cleaned:
            return []

        subqueries = [
            f"{cleaned} overview architecture key concepts",
            f"{cleaned} latest developments 2026 updates",
            f"{cleaned} specifications benchmarks performance",
            f"{cleaned} limitations challenges criticism"
        ]
        return subqueries[:max_subqueries]
