import os
import re
import pytest
import pypdf
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from friday_core.router.semantic_router import SemanticIntentRouter, SkillIntent
from friday_ui.core.engine import FridayBrain


def generate_test_pdf(filepath: str, title: str = "", sentences: list = None) -> str:
    """Generates a strictly valid minimal PDF-1.4 file with correct xref offsets and optional metadata."""
    sentences = sentences or ["This is a test document."]
    stream_content = "BT\n/F1 12 Tf\n50 720 Td\n16 TL\n"
    for s in sentences:
        safe_s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({safe_s}) '\n"
    stream_content += "ET\n"
    stream_bytes = stream_content.encode("latin-1")
    stream_len = len(stream_bytes)

    body = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        f"4 0 obj << /Length {stream_len} >>\nstream\n"
    ).encode("latin-1") + stream_bytes + b"endstream\nendobj\n" + (
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
    ).encode("latin-1")

    obj6 = ""
    if title:
        safe_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        obj6 = f"6 0 obj << /Title ({safe_title}) >> endobj\n"
        body += obj6.encode("latin-1")

    # Compute xref offsets
    lines = body.split(b"\n")
    offsets = []
    curr = 0
    num_objs = 6 if title else 5
    for obj_idx in range(1, num_objs + 1):
        target_token = f"{obj_idx} 0 obj".encode("ascii")
        pos = body.find(target_token)
        offsets.append(pos)

    xref_pos = len(body)
    xref_table = f"xref\n0 {num_objs + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref_table += f"{off:010d} 00000 n \n"

    trailer_info = " /Info 6 0 R" if title else ""
    trailer = f"trailer << /Size {num_objs + 1} /Root 1 0 R{trailer_info} >>\nstartxref\n{xref_pos}\n%%EOF\n"
    full_data = body + xref_table.encode("latin-1") + trailer.encode("latin-1")

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(full_data)

    return os.path.abspath(filepath)


@pytest.mark.asyncio
async def test_pdf_intent_routing_zero_telemetry_collision():
    """BUG-011: Assert PDF queries resolve to SkillIntent.DOCUMENT_QA and NEVER collapse into SYSTEM_TELEMETRY."""
    router = SemanticIntentRouter()
    
    test_queries = [
        "what is the first sentence of this PDF?",
        "what's the first sentence in this PDF?",
        "what is the title of this PDF?",
        "summarize this PDF",
        "give me a 3-point summary of this PDF",
        "read this PDF file"
    ]
    
    for q in test_queries:
        res = await router.route(q, client=None, confidence_threshold=0.70)
        assert res.intent == SkillIntent.DOCUMENT_QA, (
            f"Query '{q}' routed to '{res.intent.name}' instead of DOCUMENT_QA. Collision occurred!"
        )
        assert res.intent != SkillIntent.SYSTEM_TELEMETRY, (
            f"Query '{q}' collided into SYSTEM_TELEMETRY!"
        )


@pytest.mark.asyncio
async def test_pdf_title_extraction_and_zero_hallucination(tmp_path):
    """BUG-009: Verified metadata title extraction, and truthful fallback when title is missing (zero hallucination)."""
    # 1. PDF with explicit verified title
    pdf_with_title = str(tmp_path / "titled_doc.pdf")
    generate_test_pdf(
        pdf_with_title,
        title="F.R.I.D.A.Y. Operational Architecture",
        sentences=["System specification document.", "Subsystems are nominal."]
    )

    # 2. PDF without metadata title
    pdf_without_title = str(tmp_path / "untitled_doc.pdf")
    generate_test_pdf(
        pdf_without_title,
        title="",
        sentences=["Standard operational text without a metadata title."]
    )

    # Mock FridayBrain
    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()

    # Test 1: Title exists
    res1 = await engine._handle_document_qa(f"what is the title of {pdf_with_title}?", "what is the title of this pdf")
    assert "F.R.I.D.A.Y. Operational Architecture" in res1
    assert "verified title" in res1.lower()

    # Test 2: Title does not exist -> must NOT hallucinate
    res2 = await engine._handle_document_qa(f"what is the title of {pdf_without_title}?", "what is the title of this pdf")
    assert "couldn't verify the title from the pdf" in res2.lower(), (
        f"Expected truthful non-hallucinated refusal, got: '{res2}'"
    )


@pytest.mark.asyncio
async def test_pdf_first_sentence_extraction_exact_grounding(tmp_path):
    """BUG-011: First sentence extraction matches exact text from page 1."""
    pdf_path = str(tmp_path / "grounded_doc.pdf")
    first_sent = "The first sentence of this PDF confirms zero-trust verification across all subsystems."
    second_sent = "Telemetry and document intelligence are strictly decoupled."
    generate_test_pdf(
        pdf_path,
        title="Verification Guide",
        sentences=[first_sent, second_sent]
    )

    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()

    res = await engine._handle_document_qa(f"what is the first sentence of {pdf_path}?", "what is the first sentence of this pdf")
    assert first_sent in res, f"Expected '{first_sent}' in response, got: '{res}'"


@pytest.mark.asyncio
async def test_pdf_token_budgeting_on_large_document(tmp_path):
    """BUG-010: Context budgeting strictly caps document context <= 7500 chars (<= 2500 tokens)."""
    pdf_path = str(tmp_path / "large_doc.pdf")
    
    # Generate 100 sentences (~15,000 characters)
    large_sentences = [f"Section {i}: Verifying subsystem resilience under heavy workload conditions." for i in range(150)]
    generate_test_pdf(
        pdf_path,
        title="Large Scale System Specification",
        sentences=large_sentences
    )

    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()
    captured_prompts = []

    async def mock_query_llm(prompt, stream_to_ui=False, stream_to_speech=False):
        captured_prompts.append(prompt)
        return "• Point 1\n• Point 2\n• Point 3"

    engine.query_llm = mock_query_llm

    # Execute summarization
    res = await engine._handle_document_qa(f"give me a 3-point summary of {pdf_path}", "summarize this pdf")
    assert res == "__STREAMED__"
    assert len(captured_prompts) == 1
    
    prompt = captured_prompts[0]
    # Check that prompt contains 3-point instruction
    assert "3-point summary" in prompt or "three bullet points" in prompt
    
    # Extract the document text excerpt from the prompt
    excerpt_match = re.search(r'"""\n(.*?)\n"""', prompt, re.DOTALL)
    assert excerpt_match is not None, "Document excerpt not properly enclosed in prompt"
    excerpt = excerpt_match.group(1)
    
    # Strict context budget check: <= 7500 characters
    assert len(excerpt) <= 7500, f"Token budget exceeded! Excerpt length: {len(excerpt)} chars (limit 7500)"
