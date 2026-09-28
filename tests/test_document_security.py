"""
F.R.I.D.A.Y. 3.0 — Document Security & Boundary Protection Test Suite
Tests path traversal, UNC shares, sensitive system paths, unauthorized folders,
and security gate enforcement across document reading and editing.
"""

import os
import pytest

from friday_core.document.file_detector import validate_file_path, is_sensitive_path
from friday_core.document.reader import UnifiedDocumentReader
from friday_core.document.unified_editor import UnifiedDocumentEditor
from friday_core.skills.agent_bridge import agent_tool_bridge


def test_path_traversal_blocked_in_validator():
    """Assert directory traversal strings are rejected."""
    traversal_paths = [
        "../../secret.env",
        "..\\..\\passwords.txt",
        "docs/../../windows/system32",
        "folder/../.../traversal"
    ]
    for p in traversal_paths:
        is_safe, _, err = validate_file_path(p, must_exist=False)
        assert is_safe is False
        assert "traversal" in err.lower()


def test_unc_network_paths_blocked():
    """Assert UNC network shares are blocked fail-closed."""
    unc_paths = [
        "\\\\evil-server\\payload\\doc.pdf",
        "//attacker.com/share/data.docx"
    ]
    for p in unc_paths:
        is_safe, _, err = validate_file_path(p, must_exist=False)
        assert is_safe is False
        assert "unc" in err.lower()


def test_sensitive_system_files_blocked():
    """Assert attempts to target SAM, System32, shadow, and keys are blocked."""
    sensitive_targets = [
        "C:\\Windows\\System32\\config\\SAM",
        "/etc/shadow",
        "/etc/passwd",
        "C:/Users/Admin/.env",
        "C:/Users/Admin/.ssh/id_rsa",
        "C:/Windows/System32/winevt/Logs/Security.evtx"
    ]
    for p in sensitive_targets:
        assert is_sensitive_path(p) is True
        is_safe, _, err = validate_file_path(p, must_exist=False)
        assert is_safe is False
        assert "protected system" in err.lower()


def test_reader_rejects_traversal():
    """Assert UnifiedDocumentReader returns FAILED on path traversal."""
    res = UnifiedDocumentReader.read_document("../../etc/passwd")
    assert res["status"] == "FAILED"
    assert "traversal" in res["error"].lower()
    assert res["verified"] is False


def test_editor_rejects_traversal_and_system_files():
    """Assert UnifiedDocumentEditor rejects traversal and system targets."""
    res = UnifiedDocumentEditor.edit_document(
        file_path="../../config.json",
        target="setting",
        operation="replace",
        content="new_setting"
    )
    assert res.success is False
    assert "security gate" in res.message.lower() or "traversal" in res.message.lower()


def test_agent_tool_bridge_risk_gate_blocks_document_tools():
    """Assert AgentToolBridge.risk_gate blocks prohibited paths."""
    allowed, reason = agent_tool_bridge.risk_gate("read_document", {"file_path": "\\\\remote\\payload.pdf"})
    assert allowed is False
    assert "blocked" in reason.lower()

    allowed2, reason2 = agent_tool_bridge.risk_gate("edit_document", {"file_path": "C:\\Windows\\System32\\calc.exe"})
    assert allowed2 is False
    assert "blocked" in reason2.lower()
