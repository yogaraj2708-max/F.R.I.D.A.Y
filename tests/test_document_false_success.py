"""
F.R.I.D.A.Y. 3.0 — Document False Success & Honesty Test Suite
Enforces the zero-trust False-Success Rule across document operations:
1. Never claim 'read the document' unless actual document bytes were parsed and extracted.
2. Never claim 'edited the file' unless the modified artifact was saved atomically, reopened, and verified.
3. Never guess or hallucinate extraction from filename alone.
4. When information is missing, answer honestly that it was not found.
"""

import os
import pytest

from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache
from friday_core.document.unified_editor import UnifiedDocumentEditor


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_missing_file_never_reports_success():
    """Assert non-existent file path fails closed and never reports success."""
    res = UnifiedDocumentReader.read_document("C:/NonExistentPath/phantom_file.pdf")
    assert res["status"] == "FAILED"
    assert res["verified"] is False
    assert "not found" in res["error"].lower()


def test_empty_file_never_reports_success(tmp_path):
    """Assert empty 0-byte file fails closed and never reports success."""
    empty_path = str(tmp_path / "zero_bytes.docx")
    with open(empty_path, "wb") as f:
        pass

    res = UnifiedDocumentReader.read_document(empty_path)
    assert res["status"] == "FAILED"
    assert res["verified"] is False
    assert "empty (0 bytes)" in res["error"].lower()


def test_unsupported_binary_never_reports_success(tmp_path):
    """Assert arbitrary binary file is rejected with clear honest failure."""
    bin_path = str(tmp_path / "binary.docx")
    with open(bin_path, "wb") as f:
        f.write(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09")

    res = UnifiedDocumentReader.read_document(bin_path)
    assert res["status"] == "FAILED"
    assert res["verified"] is False


def test_missing_focus_item_never_hallucinates(tmp_path):
    """Assert querying a topic that does not exist in the document returns NOT_FOUND honestly."""
    doc_path = str(tmp_path / "notes.txt")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("Chapter 1: Newtonian Mechanics\nForce equals mass times acceleration.")

    res = UnifiedDocumentReader.read_document(doc_path, focus="Quantum Chromodynamics")
    assert res["status"] == "NOT_FOUND"
    assert res["target_found"] is False
    assert "not found" in res["raw_text"].lower()


def test_edit_verification_failure_never_reports_success(tmp_path):
    """Assert edit on non-existent target fails with verified=False."""
    txt_file = str(tmp_path / "log.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("Log line 1: Service started.\n")

    res = UnifiedDocumentEditor.edit_document(
        file_path=txt_file,
        target="NonExistentTargetToReplace",
        operation="replace",
        content="Injected text"
    )

    assert res.success is False
    assert res.verification.get("verified") is False
    assert "not found" in res.message.lower()
