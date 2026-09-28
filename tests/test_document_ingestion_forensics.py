"""
F.R.I.D.A.Y. 3.0 — Document Ingestion Forensics Test Suite
Tests file type detection, magic byte verification, MIME handling, encoding detection,
and safe rejection of renamed, malformed, empty, or binary files.
"""

import os
import zipfile
import json
import pytest

from friday_core.document.file_detector import (
    detect_and_validate_file,
    DocumentType,
    MAX_TEXT_BYTES,
    MAX_PDF_DOCX_BYTES
)


def create_minimal_pdf(path: str, text: str = "Test PDF Content"):
    """Generates a syntactically valid minimal PDF."""
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <<>> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(len(text) + 20).encode("ascii") + b" >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (" + text.encode("ascii") + b") Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000216 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n310\n%%EOF\n"
    )
    with open(path, "wb") as f:
        f.write(content)


def create_minimal_docx(path: str):
    """Generates a minimal valid DOCX file using python-docx."""
    import docx
    doc = docx.Document()
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("This is a verified test document paragraph.")
    doc.save(path)


def test_valid_pdf_detected(tmp_path):
    """Assert valid PDF is recognized by %PDF- magic bytes."""
    pdf_file = str(tmp_path / "sample.pdf")
    create_minimal_pdf(pdf_file, "Hello F.R.I.D.A.Y.")

    res = detect_and_validate_file(pdf_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.PDF
    assert res.mime_type == "application/pdf"
    assert res.file_size > 0
    assert len(res.sha256) == 64


def test_renamed_pdf_detected(tmp_path):
    """Assert PDF renamed to .txt is detected as PDF via magic bytes."""
    renamed_file = str(tmp_path / "disguised.txt")
    create_minimal_pdf(renamed_file, "Disguised PDF")

    res = detect_and_validate_file(renamed_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.PDF
    assert res.mime_type == "application/pdf"


def test_fake_pdf_rejected(tmp_path):
    """Assert text file renamed to .pdf is rejected fail-closed."""
    fake_pdf = str(tmp_path / "fake.pdf")
    with open(fake_pdf, "w", encoding="utf-8") as f:
        f.write("I am just plain text pretending to be a PDF.")

    res = detect_and_validate_file(fake_pdf)
    assert res.is_valid is False
    assert "lacks '%PDF-'" in res.error


def test_valid_docx_detected(tmp_path):
    """Assert valid DOCX is recognized by ZIP header and Word structure."""
    docx_file = str(tmp_path / "sample.docx")
    create_minimal_docx(docx_file)

    res = detect_and_validate_file(docx_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.DOCX
    assert "wordprocessingml" in res.mime_type


def test_fake_docx_rejected(tmp_path):
    """Assert text file renamed to .docx is rejected."""
    fake_docx = str(tmp_path / "fake.docx")
    with open(fake_docx, "w", encoding="utf-8") as f:
        f.write("This is not a zip file.")

    res = detect_and_validate_file(fake_docx)
    assert res.is_valid is False
    assert "ZIP" in res.error or "PK" in res.error


def test_arbitrary_zip_not_docx_rejected(tmp_path):
    """Assert ZIP file lacking Word document structure is rejected."""
    zip_path = str(tmp_path / "archive.docx")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("test.txt", "Some random data inside zip.")

    res = detect_and_validate_file(zip_path)
    assert res.is_valid is False
    assert "not a valid DOCX" in res.error or res.doc_type == DocumentType.UNSUPPORTED


def test_empty_file_rejected(tmp_path):
    """Assert 0-byte file is rejected fail-closed."""
    empty_file = str(tmp_path / "empty.txt")
    empty_file_path = str(empty_file)
    with open(empty_file_path, "wb") as f:
        pass

    res = detect_and_validate_file(empty_file_path)
    assert res.is_valid is False
    assert "empty (0 bytes)" in res.error


def test_binary_file_rejected(tmp_path):
    """Assert binary file containing null bytes is safely rejected."""
    bin_file = str(tmp_path / "payload.txt")
    with open(bin_file, "wb") as f:
        f.write(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00")

    res = detect_and_validate_file(bin_file)
    assert res.is_valid is False
    assert "Binary file rejected" in res.error


def test_valid_json_detected(tmp_path):
    """Assert valid JSON is detected and parsed."""
    json_file = str(tmp_path / "data.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({"version": "3.0", "status": "active"}, f)

    res = detect_and_validate_file(json_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.JSON
    assert res.metadata.get("element_count") == 2


def test_malformed_json_rejected(tmp_path):
    """Assert malformed JSON is rejected fail-closed."""
    bad_json = str(tmp_path / "broken.json")
    with open(bad_json, "w", encoding="utf-8") as f:
        f.write("{'bad_json': True, missing_quote}")

    res = detect_and_validate_file(bad_json)
    assert res.is_valid is False
    assert "Malformed JSON" in res.error


def test_valid_csv_detected(tmp_path):
    """Assert CSV with delimiter is detected."""
    csv_file = str(tmp_path / "table.csv")
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("id,name,role\n1,Tony,Admin\n2,Pepper,CEO\n")

    res = detect_and_validate_file(csv_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.CSV


def test_source_code_detected(tmp_path):
    """Assert source code file is recognized."""
    py_file = str(tmp_path / "script.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write("def calculate_total(a, b):\n    return a + b\n")

    res = detect_and_validate_file(py_file)
    assert res.is_valid is True
    assert res.doc_type == DocumentType.SOURCE_CODE
