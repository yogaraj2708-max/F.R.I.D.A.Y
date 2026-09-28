"""
F.R.I.D.A.Y. 3.0 — Source Cross-Checker & Contradiction Detector
Cross-examines information from multiple search results and sources.
Identifies corroborating claims and flags conflicting or contradictory statements.
"""

import re
from typing import List, Dict, Any, Tuple
from friday_core.research.models import ResearchSource, KeyFinding, Contradiction


class SourceCrossChecker:
    """
    Evaluates agreement and flags contradictions across multiple research sources.
    """

    @classmethod
    def extract_claims(cls, sources: List[ResearchSource]) -> List[KeyFinding]:
        """
        Extracts salient statements from sources and determines corroboration.
        If multiple sources support the same claim/topic, confidence increases.
        """
        findings: List[KeyFinding] = []
        if not sources:
            return findings

        # Group snippet sentences by thematic keywords
        seen_sentences = set()
        for src in sources:
            sentences = re.split(r"(?<=[.!?])\s+", src.snippet)
            for sent in sentences:
                cleaned = sent.strip()
                if len(cleaned) < 25 or cleaned in seen_sentences:
                    continue
                seen_sentences.add(cleaned)

                # Check if this sentence corroborates existing findings
                matched = False
                for f in findings:
                    # Token overlap similarity check
                    toks_f = set(re.findall(r"\w+", f.claim.lower()))
                    toks_s = set(re.findall(r"\w+", cleaned.lower()))
                    overlap = len(toks_f.intersection(toks_s))
                    if overlap >= 5 and src.url not in f.supporting_sources:
                        f.supporting_sources.append(src.url)
                        f.evidence_snippets[src.url] = cleaned[:250]
                        f.provenance_chain.append({
                            "source_url": src.url,
                            "excerpt": cleaned[:250],
                            "retrieved_at": src.retrieved_at,
                            "content_hash": src.content_hash,
                            "verification_status": src.verification_status
                        })
                        f.confidence = min(1.0, f.confidence + 0.2)
                        matched = True
                        break

                if not matched:
                    findings.append(KeyFinding(
                        claim=cleaned,
                        supporting_sources=[src.url],
                        confidence=0.6 * src.credibility_score,
                        evidence_snippets={src.url: cleaned[:250]},
                        provenance_chain=[{
                            "source_url": src.url,
                            "excerpt": cleaned[:250],
                            "retrieved_at": src.retrieved_at,
                            "content_hash": src.content_hash,
                            "verification_status": src.verification_status
                        }]
                    ))

        # Sort findings by corroboration confidence
        findings.sort(key=lambda x: (len(x.supporting_sources), x.confidence), reverse=True)
        return findings

    @classmethod
    def detect_contradictions(cls, sources: List[ResearchSource]) -> List[Contradiction]:
        """
        Identifies opposing statements (e.g. contrasting numbers, affirmative vs negative)
        across distinct sources.
        """
        contradictions: List[Contradiction] = []
        if len(sources) < 2:
            return contradictions

        # Contrast indicators
        negation_markers = ["not", "never", "no longer", "failed", "untrue", "false", "disputed"]

        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                src_a = sources[i]
                src_b = sources[j]

                # Check for contrasting statements
                toks_a = set(re.findall(r"\w+", src_a.snippet.lower()))
                toks_b = set(re.findall(r"\w+", src_b.snippet.lower()))

                shared_terms = toks_a.intersection(toks_b)
                # If they share significant nouns/entities but one contains negation markers
                if len(shared_terms) >= 3:
                    has_neg_a = any(m in toks_a for m in negation_markers)
                    has_neg_b = any(m in toks_b for m in negation_markers)

                    if has_neg_a != has_neg_b:
                        # Potential contradiction found
                        contradictions.append(Contradiction(
                            topic=f"Contrasting claims regarding '{' '.join(list(shared_terms)[:4])}'",
                            claim_a=src_a.snippet[:120] + "...",
                            source_a=src_a.url,
                            claim_b=src_b.snippet[:120] + "...",
                            source_b=src_b.url
                        ))

        return contradictions
