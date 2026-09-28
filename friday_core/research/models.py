"""
F.R.I.D.A.Y. 3.0 — Deep Research 2.0 Data Models
Provides structured schemas for query decomposition, source cross-checking,
contradiction detection, and verifiable briefings with URL provenance.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    url: str
    title: str
    snippet: str
    credibility_score: float = 1.0
    original_url: Optional[str] = None
    final_url: Optional[str] = None
    http_status: int = 200
    content_type: str = "text/html"
    content_length: int = 0
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    published_at: Optional[str] = None
    raw_content: Optional[str] = None
    content_hash: Optional[str] = None
    verification_status: str = "UNVERIFIED"  # "VERIFIED" only when actual page body >= 50 chars read
    parser_status: str = "PENDING"           # "SUCCESS", "FAILED", "TIMEOUT", "EMPTY", "BLOCKED"


class KeyFinding(BaseModel):
    claim: str
    supporting_sources: List[str] = Field(default_factory=list)  # URLs
    confidence: float = 1.0
    evidence_snippets: Dict[str, str] = Field(default_factory=dict)  # {url: exact_excerpt}
    provenance_chain: List[Dict[str, Any]] = Field(default_factory=list)  # [{source_url, excerpt, retrieved_at, content_hash}]


class Contradiction(BaseModel):
    topic: str
    claim_a: str
    source_a: str
    claim_b: str
    source_b: str


class ResearchBriefing(BaseModel):
    topic: str
    executive_summary: str
    findings: List[KeyFinding] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(default_factory=list)
    sources: List[ResearchSource] = Field(default_factory=list)
    is_verified: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_sources_discovered: int = 0
    total_sources_verified: int = 0
    subqueries: List[str] = Field(default_factory=list)
    task_id: Optional[str] = None
