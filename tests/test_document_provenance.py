"""
F.R.I.D.A.Y. 3.0 — Document Provenance & Evidence Isolation Test Suite
Tests provenance tracking for read_document and edit_document, distinct evidence isolation
between multiple documents, and segregation of document evidence from web evidence.
"""

import os
import pytest

from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_read_document_provenance_bundle():
    """Assert verify_tool_result for read_document generates correct structure."""
    bundle = agent_tool_bridge.verify_tool_result(
        tool_name="read_document",
        arguments={"file_path": "C:/docs/blueprint.pdf", "focus": "reactor"},
        raw_output="Extracted blueprint data from Page 4",
        trace_id="trace-doc-1",
        tool_call_id="call-doc-1"
    )

    assert bundle["tool_name"] == "read_document"
    assert bundle["source_file"] == "C:/docs/blueprint.pdf"
    assert bundle["status"] == "SUCCESS"
    assert bundle["verification_status"] == "VERIFIED"
    assert "[VERIFIED TOOL PROVENANCE | tool: read_document" in bundle["formatted_result"]


def test_edit_document_provenance_bundle():
    """Assert verify_tool_result for edit_document includes target, operation, and verification."""
    bundle = agent_tool_bridge.verify_tool_result(
        tool_name="edit_document",
        arguments={"file_path": "C:/docs/report.docx", "target": "Item 12", "operation": "replace"},
        raw_output="Document Edit Succeeded & Verified:\nVERIFIED: Surgical edit succeeded.\nFile: C:/docs/report.docx\nOperation: replace",
        trace_id="trace-edit-1",
        tool_call_id="call-edit-1"
    )

    assert bundle["tool_name"] == "edit_document"
    assert bundle["source_file"] == "C:/docs/report.docx"
    assert bundle["target"] == "Item 12"
    assert bundle["operation"] == "replace"
    assert bundle["status"] == "SUCCESS"
    assert bundle["verification_status"] == "VERIFIED"


def test_document_and_web_evidence_isolation():
    """Assert document evidence and web evidence maintain separate provenance and fields."""
    doc_bundle = agent_tool_bridge.verify_tool_result(
        tool_name="read_document",
        arguments={"file_path": "C:/docs/manual.pdf"},
        raw_output="Manual content",
        trace_id="trace-doc-2",
        tool_call_id="call-doc-2"
    )

    web_bundle = agent_tool_bridge.verify_tool_result(
        tool_name="web_search",
        arguments={"query": "quantum computing"},
        raw_output="Results from https://example.com/quantum",
        trace_id="trace-web-2",
        tool_call_id="call-web-2"
    )

    # Document has source_file, NO source_urls
    assert "source_file" in doc_bundle
    assert "source_urls" not in doc_bundle

    # Web has source_urls, NO source_file
    assert "source_urls" in web_bundle
    assert "source_file" not in web_bundle


def test_multi_document_evidence_isolation(tmp_path):
    """Assert Document A and Document B maintain independent hashes, contents, and locations."""
    file_a = str(tmp_path / "doc_a.txt")
    file_b = str(tmp_path / "doc_b.txt")

    with open(file_a, "w", encoding="utf-8") as f:
        f.write("Document A discusses Project Alpha with high priority.")

    with open(file_b, "w", encoding="utf-8") as f:
        f.write("Document B discusses Project Beta with low priority.")

    res_a = UnifiedDocumentReader.read_document(file_a)
    res_b = UnifiedDocumentReader.read_document(file_b)

    assert res_a["sha256"] != res_b["sha256"]
    assert "Project Alpha" in res_a["raw_text"]
    assert "Project Beta" not in res_a["raw_text"]

    assert "Project Beta" in res_b["raw_text"]
    assert "Project Alpha" not in res_b["raw_text"]
