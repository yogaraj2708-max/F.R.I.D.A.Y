"""
F.R.I.D.A.Y. 3.0 — DOCX Hardening Test Suite
Tests paragraphs, headings, tables, lists, targeted region retrieval,
surgical edits, unrelated content preservation, and reopen verification.
"""

import os
import pytest
import docx

from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache
from friday_core.document.unified_editor import UnifiedDocumentEditor
from friday_core.document.parser import DocxStructuralParser
from friday_core.document.verifier import DocxIndependentVerifier


def create_sample_docx(path: str) -> str:
    """Creates a rich DOCX with headings, paragraphs, and a table."""
    doc = docx.Document()
    doc.add_heading("Section 1: Mission Parameters", level=1)
    doc.add_paragraph("F.R.I.D.A.Y. zero-trust architecture enforces forensic validation.")

    doc.add_heading("Section 2: Engineering Specs", level=1)
    doc.add_paragraph("All subsystems must be isolated, bounded, and recoverable.")
    doc.add_paragraph("Item 12: Primary reactor core cooling sequence requires active telemetry monitoring.")

    doc.add_heading("Section 3: Summary of Metrics", level=1)
    table = doc.add_table(rows=3, cols=3)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Threshold"
    table.cell(0, 2).text = "Status"

    table.cell(1, 0).text = "Latency"
    table.cell(1, 1).text = "100ms"
    table.cell(1, 2).text = "Nominal"

    table.cell(2, 0).text = "Memory"
    table.cell(2, 1).text = "512MB"
    table.cell(2, 2).text = "Optimal"

    doc.save(path)
    return path


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_docx_structural_parsing(tmp_path):
    """Test DOCX structural map extracts headings, paragraphs, and tables."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    doc_map = DocxStructuralParser.parse(doc_path)
    assert doc_map.total_paragraphs >= 4
    assert doc_map.total_tables == 1
    assert any("Section 1" in h.text for h in doc_map.headings)
    assert any("Section 2" in h.text for h in doc_map.headings)


def test_docx_read_default_bounded(tmp_path):
    """Test reading DOCX without focus returns structural summary and excerpts."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    res = UnifiedDocumentReader.read_document(doc_path)
    assert res["status"] == "SUCCESS"
    assert "DOCX Structure" in res["raw_text"]
    assert res["doc_type"] == "docx"
    assert res["verified"] is True


def test_docx_targeted_focus_retrieval(tmp_path):
    """Test reading DOCX with focus='item 12' retrieves exact item paragraph."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    res = UnifiedDocumentReader.read_document(doc_path, focus="item 12")
    assert res["status"] == "SUCCESS"
    assert "reactor core cooling sequence" in res["raw_text"]
    assert res["target_found"] is True


def test_docx_focus_not_found(tmp_path):
    """Test asking for non-existent item in DOCX reports NOT_FOUND honestly."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    res = UnifiedDocumentReader.read_document(doc_path, focus="Item 99: Anti-Gravity Engine")
    assert res["status"] == "NOT_FOUND"
    assert "Target information for 'Item 99: Anti-Gravity Engine' was not found" in res["raw_text"]
    assert res["target_found"] is False


def test_docx_surgical_edit_and_reopen_verification(tmp_path):
    """Test surgical edit of a specific item, atomic write, reopen, and verification."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    new_content = "Item 12: Reactor core cooling sequence has been upgraded to cryogenic liquid nitrogen."
    edit_res = UnifiedDocumentEditor.edit_document(
        file_path=doc_path,
        target="Item 12",
        operation="replace",
        content=new_content
    )

    assert edit_res.success is True
    assert "VERIFIED" in edit_res.message
    assert edit_res.verification.get("verified") is True
    assert edit_res.verification.get("before_hash") != edit_res.verification.get("after_hash")

    # Independent reopen verification: fresh handle
    fresh_doc = docx.Document(doc_path)
    texts = [p.text for p in fresh_doc.paragraphs]
    assert any("cryogenic liquid nitrogen" in t for t in texts)
    # Ensure Section 1 paragraph was NOT modified
    assert any("F.R.I.D.A.Y. zero-trust architecture enforces forensic validation." in t for t in texts)


def test_docx_edit_missing_target_fails_safely(tmp_path):
    """Test surgical edit on a missing target fails closed without modifying file."""
    doc_path = str(tmp_path / "spec.docx")
    create_sample_docx(doc_path)

    edit_res = UnifiedDocumentEditor.edit_document(
        file_path=doc_path,
        target="NonExistentTargetXYZ",
        operation="replace",
        content="New content"
    )

    assert edit_res.success is False
    assert ("not found" in edit_res.message.lower()) or ("could not identify" in edit_res.message.lower()) or ("clarification" in edit_res.message.lower())
    assert edit_res.verification.get("verified") is False

