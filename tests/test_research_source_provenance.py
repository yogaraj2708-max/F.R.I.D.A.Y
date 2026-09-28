"""
Tests for F.R.I.D.A.Y. 3.0 — Section 4, 6, 7, 8, 21, 22: Source Provenance & Corroboration
Validates:
1. Proof of actual extraction: url, timestamp, excerpt, and content hash (SHA-256).
2. Provenance chain: claim -> exact excerpt -> source URL -> retrieved_at timestamp.
3. Multi-source distinctness: Sources A, B, and C remain individually identifiable.
4. Contradiction preservation: Opposing factual claims are preserved and attributed without artificial consensus.
5. Grounded citation mapping: Citations map strictly to retrieved and verified URLs.
"""

import unittest
import hashlib
from datetime import datetime, timezone

from friday_core.research.models import ResearchSource, KeyFinding, Contradiction, ResearchBriefing
from friday_core.research.cross_checker import SourceCrossChecker
from friday_core.research.synthesizer import DeepResearchSynthesizer


class TestResearchSourceProvenance(unittest.TestCase):

    def setUp(self):
        text_a = "Semiconductor manufacturing reached 2nm gate-all-around mass production in Q1 2026."
        text_b = "Semiconductor manufacturing reached 2nm gate-all-around mass production according to foundry reports."
        text_c = "Semiconductor manufacturing has not achieved viable commercial yields for 2nm gate-all-around nodes."

        hash_a = hashlib.sha256(text_a.encode('utf-8')).hexdigest()
        hash_b = hashlib.sha256(text_b.encode('utf-8')).hexdigest()
        hash_c = hashlib.sha256(text_c.encode('utf-8')).hexdigest()

        self.src_a = ResearchSource(
            url="https://semireview.com/2nm-progress",
            title="SemiReview 2nm Progress",
            snippet=text_a,
            raw_content=text_a,
            content_hash=hash_a,
            verification_status="VERIFIED",
            retrieved_at="2026-09-27T10:00:00Z"
        )
        self.src_b = ResearchSource(
            url="https://hardwaretech.io/foundry-2026",
            title="HardwareTech Foundry Report",
            snippet=text_b,
            raw_content=text_b,
            content_hash=hash_b,
            verification_status="VERIFIED",
            retrieved_at="2026-09-27T10:05:00Z"
        )
        self.src_c = ResearchSource(
            url="https://chipanalysis.org/yield-challenges",
            title="ChipAnalysis Yield Challenges",
            snippet=text_c,
            raw_content=text_c,
            content_hash=hash_c,
            verification_status="VERIFIED",
            retrieved_at="2026-09-27T10:10:00Z"
        )

    def test_01_provenance_chain_records_hashes_and_timestamps(self):
        """Verify extract_claims constructs an immutable provenance chain for each claim."""
        findings = SourceCrossChecker.extract_claims([self.src_a, self.src_b])
        self.assertGreater(len(findings), 0)

        top_f = findings[0]
        # Should be corroborated by both A and B
        self.assertEqual(len(top_f.supporting_sources), 2)
        self.assertIn(self.src_a.url, top_f.supporting_sources)
        self.assertIn(self.src_b.url, top_f.supporting_sources)

        # Check provenance chain records
        self.assertEqual(len(top_f.provenance_chain), 2)
        record_a = top_f.provenance_chain[0]
        self.assertEqual(record_a["source_url"], self.src_a.url)
        self.assertEqual(record_a["content_hash"], self.src_a.content_hash)
        self.assertEqual(record_a["retrieved_at"], self.src_a.retrieved_at)
        self.assertEqual(record_a["verification_status"], "VERIFIED")

    def test_02_multi_source_distinctness_preserved_in_synthesis(self):
        """Verify sources remain individually identifiable in executive summary and markdown dossier."""
        findings = SourceCrossChecker.extract_claims([self.src_a, self.src_b])
        contradictions = SourceCrossChecker.detect_contradictions([self.src_a, self.src_b, self.src_c])

        briefing = DeepResearchSynthesizer.synthesize(
            topic="2nm Semiconductor Scaling",
            findings=findings,
            contradictions=contradictions,
            sources=[self.src_a, self.src_b, self.src_c]
        )

        md = DeepResearchSynthesizer.format_markdown(briefing)

        # Assert all 3 distinct URLs are preserved in consulted sources
        self.assertIn(self.src_a.url, md)
        self.assertIn(self.src_b.url, md)
        self.assertIn(self.src_c.url, md)

        # Assert title links exist
        self.assertIn(f"[{self.src_a.title}]({self.src_a.url})", md)
        self.assertIn(f"[{self.src_b.title}]({self.src_b.url})", md)
        self.assertIn(f"[{self.src_c.title}]({self.src_c.url})", md)

    def test_03_conflicting_factual_claims_detected_and_attributed(self):
        """Verify opposing claims are flagged as contradictions with proper attribution to sources A and C."""
        contradictions = SourceCrossChecker.detect_contradictions([self.src_a, self.src_c])
        self.assertEqual(len(contradictions), 1)

        c = contradictions[0]
        self.assertEqual(c.source_a, self.src_a.url)
        self.assertEqual(c.source_b, self.src_c.url)
        self.assertIn("Semiconductor manufacturing", c.claim_a)
        self.assertIn("not achieved viable", c.claim_b)

    def test_04_no_orphan_citations_in_dossier(self):
        """Verify that every citation in markdown maps to an actually retrieved source URL."""
        findings = SourceCrossChecker.extract_claims([self.src_a])
        briefing = DeepResearchSynthesizer.synthesize(
            topic="Test Topic",
            findings=findings,
            contradictions=[],
            sources=[self.src_a]
        )
        md = DeepResearchSynthesizer.format_markdown(briefing)

        import re
        urls_in_md = re.findall(r"https?://[^\s)\]]+", md)
        known_urls = {self.src_a.url}

        for u in urls_in_md:
            self.assertIn(u, known_urls, f"Orphan or unretrieved citation detected: {u}")


if __name__ == "__main__":
    unittest.main()
