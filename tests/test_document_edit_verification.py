"""
F.R.I.D.A.Y. 3.0 — Document Edit Verification Test Suite
Tests atomic save, independent reopen verification, SHA-256 hash tracking,
surgical replacement, ambiguous target clarification, and zero false success.
"""

import os
import pytest
import docx

from friday_core.document.unified_editor import UnifiedDocumentEditor
from friday_core.document.file_detector import compute_sha256


def test_text_surgical_edit_and_verification(tmp_path):
    """Assert surgical edit on plain text modifies target, updates hash, and reopens verified."""
    txt_file = str(tmp_path / "config.txt")
    initial_content = (
        "ServerConfig:\n"
        "  port = 8080\n"
        "  max_connections = 100\n"
        "  mode = development\n"
        "EndConfig\n"
    )
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(initial_content)

    before_hash = compute_sha256(txt_file)

    res = UnifiedDocumentEditor.edit_document(
        file_path=txt_file,
        target="mode = development",
        operation="replace",
        content="mode = production"
    )

    assert res.success is True
    assert "VERIFIED" in res.message
    assert res.verification.get("verified") is True
    assert res.verification.get("before_hash") == before_hash
    after_hash = compute_sha256(txt_file)
    assert res.verification.get("after_hash") == after_hash
    assert before_hash != after_hash

    # Independent reopen verification
    with open(txt_file, "r", encoding="utf-8") as f:
        reopened = f.read()

    assert "mode = production" in reopened
    assert "port = 8080" in reopened
    assert "max_connections = 100" in reopened


def test_source_code_surgical_edit(tmp_path):
    """Assert surgical edit on Python source code file."""
    py_file = str(tmp_path / "worker.py")
    code = (
        "def compute_hash(data):\n"
        "    return hash(data)\n\n"
        "def execute_task():\n"
        "    return 'old_task'\n"
    )
    with open(py_file, "w", encoding="utf-8") as f:
        f.write(code)

    res = UnifiedDocumentEditor.edit_document(
        file_path=py_file,
        target="return 'old_task'",
        operation="replace",
        content="return 'new_hardened_task'"
    )

    assert res.success is True
    assert res.verification.get("verified") is True

    with open(py_file, "r", encoding="utf-8") as f:
        updated = f.read()

    assert "return 'new_hardened_task'" in updated
    assert "def compute_hash(data):" in updated  # Unrelated code preserved


def test_ambiguous_target_fails_safely(tmp_path):
    """Assert ambiguous target occurring multiple times requests clarification."""
    txt_file = str(tmp_path / "ambiguous.txt")
    content = "status = pending\nother line\nstatus = pending\n"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(content)

    res = UnifiedDocumentEditor.edit_document(
        file_path=txt_file,
        target="status = pending",
        operation="replace",
        content="status = active"
    )

    assert res.success is False
    assert "ambiguous" in res.message.lower() or "clarification" in res.message.lower()
    assert res.verification.get("verified") is False


def test_missing_target_fails_honestly(tmp_path):
    """Assert non-existent target fails with honest error."""
    txt_file = str(tmp_path / "single.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("System status: healthy.\n")

    res = UnifiedDocumentEditor.edit_document(
        file_path=txt_file,
        target="NonExistentTargetString",
        operation="replace",
        content="Replacement"
    )

    assert res.success is False
    assert "not found" in res.message.lower()
    assert res.verification.get("verified") is False
