"""
F.R.I.D.A.Y. 3.0 — Deep Research 2.0 Engine
Orchestrates query decomposition, multi-angle search, cross-checking,
contradiction detection, and briefing synthesis.
Integrates with Emergency Stop.
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.research.models import (
    ResearchSource,
    KeyFinding,
    Contradiction,
    ResearchBriefing
)
from friday_core.research.decomposer import QueryDecomposer
from friday_core.research.cross_checker import SourceCrossChecker
from friday_core.research.synthesizer import DeepResearchSynthesizer

logger = logging.getLogger("FRIDAY.DeepResearch2")


class DeepResearchEngine:
    """
    Coordinates end-to-end multi-source research tasks with citation provenance,
    verifiable HTTP retrieval, deep page reading, and contradiction detection.
    """
    def __init__(
        self,
        search_fetcher: Optional[Callable[[str], List[Dict[str, str]]]] = None,
        page_fetcher: Optional[Callable[[str, int], Dict[str, Any]]] = None
    ):
        self.search_fetcher = search_fetcher
        self.page_fetcher = page_fetcher

    def _get_search_fetcher(self) -> Callable[[str], List[Dict[str, str]]]:
        if self.search_fetcher is not None:
            return self.search_fetcher
        from friday_ui.core.engine import fetch_web_results
        return fetch_web_results

    def _get_page_fetcher(self) -> Callable[[str, int], Dict[str, Any]]:
        if self.page_fetcher is not None:
            return self.page_fetcher
        from friday_ui.core.engine import fetch_page_content_detailed
        return fetch_page_content_detailed

    def conduct_research(
        self,
        topic: str,
        sources_override: Optional[List[ResearchSource]] = None,
        max_subqueries: int = 4
    ) -> ResearchBriefing:
        """
        Executes complete Deep Research pipeline:
        1. Query decomposition
        2. Multi-angle search collection with deduplication
        3. Real web page content extraction & content hashing
        4. Cross-checking & contradiction detection on verified sources
        5. Briefing synthesis
        """
        if emergency_stop.is_stopped():
            logger.warning("Deep research rejected: Emergency Stop is active.")
            return ResearchBriefing(
                topic=topic,
                executive_summary="Research aborted: Emergency Stop was activated.",
                is_verified=False
            )

        cleaned_topic = QueryDecomposer.clean_topic(topic)
        subqueries = QueryDecomposer.decompose(cleaned_topic, max_subqueries=max_subqueries)

        all_sources: List[ResearchSource] = []
        if sources_override is not None:
            for s in sources_override:
                if s.verification_status == "UNVERIFIED" and len(s.snippet) >= 20:
                    s.verification_status = "VERIFIED"
                all_sources.append(s)
        else:
            search_fn = self._get_search_fetcher()
            page_fn = self._get_page_fetcher()
            seen_urls = set()

            for sq in subqueries:
                if emergency_stop.is_stopped():
                    logger.warning("Deep research stopped during subquery execution.")
                    break
                try:
                    raw_results = search_fn(sq)
                    if raw_results:
                        for r in raw_results:
                            url = r.get("href") or r.get("url") or ""
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_sources.append(ResearchSource(
                                    url=url,
                                    title=r.get("title", "Untitled Source"),
                                    snippet=r.get("body", "") or r.get("snippet", ""),
                                    credibility_score=1.0,
                                    original_url=url,
                                    verification_status="UNVERIFIED"
                                ))
                except Exception as e:
                    logger.error(f"Error fetching search results for subquery '{sq}': {e}")

            # Also deep-read content for candidate sources (top 6 max)
            for s in all_sources[:6]:
                if emergency_stop.is_stopped():
                    break
                try:
                    page_res = page_fn(s.url, 1800)
                    if isinstance(page_res, dict):
                        s.http_status = page_res.get("http_status", 200)
                        s.final_url = page_res.get("final_url", s.url)
                        s.content_type = page_res.get("content_type", "text/html")
                        s.content_length = page_res.get("content_length", 0)
                        s.retrieved_at = page_res.get("retrieved_at", s.retrieved_at)
                        s.parser_status = page_res.get("parser_status", "SUCCESS")
                        s.content_hash = page_res.get("content_hash")

                        text = page_res.get("extracted_text")
                        if text and len(text.strip()) >= 50:
                            s.raw_content = text
                            s.snippet += f"\nDetailed Content:\n{text}"
                            s.verification_status = "VERIFIED"
                        else:
                            s.verification_status = "UNVERIFIED"
                except Exception as p_err:
                    logger.debug("Failed deep page reading for %s: %s", s.url, p_err)
                    s.verification_status = "UNVERIFIED"
                    s.parser_status = "FAILED"

        # Separate verified sources
        verified_sources = [s for s in all_sources if s.verification_status == "VERIFIED"]

        # If zero verified sources exist: fail closed honestly
        if not verified_sources and not sources_override:
            return ResearchBriefing(
                topic=cleaned_topic,
                executive_summary=(
                    f"⚠️ Research Inconclusive: Zero verifiable source endpoints could be retrieved "
                    f"for '{cleaned_topic}'. In accordance with zero-trust intelligence standards, "
                    f"F.R.I.D.A.Y. refuses to synthesize ungrounded claims or fabricate sources. "
                    f"No verifiable multi-source intelligence could be extracted for this topic."
                ),
                findings=[],
                contradictions=[],
                sources=all_sources,
                is_verified=False,
                total_sources_discovered=len(all_sources),
                total_sources_verified=0,
                subqueries=subqueries
            )

        sources_for_claims = verified_sources if verified_sources else all_sources

        # 3. Cross-Checking & Contradiction Detection
        findings = SourceCrossChecker.extract_claims(sources_for_claims)
        contradictions = SourceCrossChecker.detect_contradictions(sources_for_claims)

        # 4. Synthesize Briefing
        briefing = DeepResearchSynthesizer.synthesize(
            topic=cleaned_topic,
            findings=findings,
            contradictions=contradictions,
            sources=sources_for_claims
        )
        briefing.total_sources_discovered = len(all_sources)
        briefing.total_sources_verified = len(verified_sources)
        briefing.subqueries = subqueries

        return briefing


# Global Singleton Deep Research Engine
deep_research_engine = DeepResearchEngine()
