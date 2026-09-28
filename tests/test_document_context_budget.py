"""
F.R.I.D.A.Y. 3.0 — Document Context Budget & Deduplication Test Suite
Tests context budget limits, truncation, CSV row limits, JSON structural bounding,
and attachment deduplication via SHA-256 content hashing.
"""

import os
import json
import csv
import pytest

from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache
from friday_core.document.file_detector import MAX_EXTRACTED_CHARS, MAX_CSV_ROWS


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_text_file_bounded_to_max_chars(tmp_path):
    """Assert a giant text file is strictly bounded to max_chars."""
    huge_text = str(tmp_path / "huge.txt")
    with open(huge_text, "w", encoding="utf-8") as f:
        # Write 50,000 characters
        for i in range(1000):
            f.write(f"Line {i:04d}: This is detailed telemetry data that should not flood the context window.\n")

    res = UnifiedDocumentReader.read_document(huge_text, max_chars=2000)
    assert res["status"] == "SUCCESS"
    assert len(res["raw_text"]) <= 2200
    assert "Truncated" in res["raw_text"] or len(res["raw_text"]) <= 2000


def test_csv_bounded_to_row_limit(tmp_path):
    """Assert a CSV with 500 rows is bounded to MAX_CSV_ROWS (100)."""
    csv_path = str(tmp_path / "big_table.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Timestamp", "Value", "Status"])
        for i in range(500):
            writer.writerow([i, f"2026-09-27T12:{i%60:02d}:00", i * 1.5, "ACTIVE"])

    res = UnifiedDocumentReader.read_document(csv_path)
    assert res["status"] == "SUCCESS"
    # Default preview is 10 rows
    assert "Rows 2-11 of 501" in res["evidence_location"]
    # With condition focus matching 500 rows, should cap at MAX_CSV_ROWS
    res_focused = UnifiedDocumentReader.read_document(csv_path, focus="active")
    assert res_focused["status"] == "SUCCESS"
    row_count = res_focused["raw_text"].count("Row ")
    assert row_count <= MAX_CSV_ROWS


def test_json_structural_bounding_never_raw_dumps(tmp_path):
    """Assert a giant JSON dictionary does not dump raw megabytes."""
    json_path = str(tmp_path / "giant.json")
    giant_dict = {f"parameter_{i}": {"value": i, "details": "config " * 10} for i in range(500)}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(giant_dict, f)

    res = UnifiedDocumentReader.read_document(json_path)
    assert res["status"] == "SUCCESS"
    assert "500 top-level keys" in res["raw_text"]
    assert "Sample (first 5 keys)" in res["raw_text"]
    assert len(res["raw_text"]) < 2500  # Strict context budget


def test_attachment_deduplication(tmp_path):
    """Assert reading the same document twice leverages deduplication cache with matching SHA-256."""
    doc_path = str(tmp_path / "memo.txt")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("Important system directive: Always verify writes.")

    res1 = UnifiedDocumentReader.read_document(doc_path)
    assert res1.get("cached") is not True

    res2 = UnifiedDocumentReader.read_document(doc_path)
    assert res2.get("cached") is True
    assert res1["sha256"] == res2["sha256"]
