"""
F.R.I.D.A.Y. 3.0 — RAG 2.0 Document Intelligence & Citations Data Models
Provides strict chunk provenance, source citations, knowledge domains,
and citation validation models.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class KnowledgeDomain(str, Enum):
    PROJECT = "PROJECT"
    PERSONAL = "PERSONAL"
    TECHNICAL = "TECHNICAL"
    RESEARCH = "RESEARCH"


class DocumentChunk(BaseModel):
    """
    Granular, verifiable document chunk with full provenance tracking.
    """
    chunk_id: str
    doc_id: str
    title: str
    source_path: str
    source_filename: str
    page_or_section: str = "general"
    chunk_index: int
    content: str
    char_offset: int = 0
    token_count: int = 0
    domain: str = KnowledgeDomain.PROJECT.value
    version: int = 1
    content_hash: str = ""
    doc_hash: str = ""
    embedding_model: str = "fast_blake2b_384"
    embedding_dim: int = 384
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def citation_tag(self) -> str:
        """Standardized, verifiable citation tag for LLM reference."""
        return f"[Doc: {self.source_filename}, Sec: {self.page_or_section}, Chunk: {self.chunk_index}]"


class QueryResult(BaseModel):
    """
    Scored search result combining dense vector and lexical BM25 matching.
    """
    chunk: DocumentChunk
    vector_score: float = 0.0
    bm25_score: float = 0.0
    hybrid_score: float = 0.0

    @property
    def citation_tag(self) -> str:
        return self.chunk.citation_tag

    def format_as_untrusted_data(self) -> str:
        """Formats the retrieved chunk as explicitly marked UNTRUSTED DATA."""
        return (
            f"<untrusted_document_evidence citation=\"{self.citation_tag}\" "
            f"doc_id=\"{self.chunk.doc_id}\" domain=\"{self.chunk.domain}\" "
            f"version=\"{self.chunk.version}\" score=\"{self.hybrid_score}\">\n"
            f"{self.chunk.content}\n"
            f"</untrusted_document_evidence>"
        )


class CitationVerificationResult(BaseModel):
    """
    Strict provenance audit result checking LLM answer citations against retrieved context.
    Detects and flags hallucinated citations.
    """
    is_valid: bool
    cited_tags: List[str] = Field(default_factory=list)
    supported_tags: List[str] = Field(default_factory=list)
    hallucinated_tags: List[str] = Field(default_factory=list)
