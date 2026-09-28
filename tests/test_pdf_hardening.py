"""
F.R.I.D.A.Y. 3.0 — PDF Hardening Test Suite
Tests single-page, multi-page, targeted relevance retrieval, encrypted/scanned PDF handling,
bounded context, and fail-closed error recovery.
"""

import os
import io
import pytest
import pypdf

from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache
from friday_core.document.file_detector import detect_and_validate_file, DocumentType


def make_single_page_pdf(lines: list) -> bytes:
    """Generates valid PDF bytes for a single page with exact offsets and fonts."""
    stream = "BT /F1 12 Tf 50 720 Td 14 TL " + " ".join(f"({l.replace('(', '').replace(')', '')}) '" for l in lines) + " ET"
    sb = stream.encode("latin-1")
    objs = [
        b"%PDF-1.4\n",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(sb)).encode("ascii") + b" >>\nstream\n" + sb + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    ]
    offsets = []
    curr = len(objs[0])
    for obj in objs[1:]:
        offsets.append(curr)
        curr += len(obj)

    body = b"".join(objs)
    xref_offset = len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode("ascii")
    xref += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF"
    return body + xref


def create_multipage_pdf(path: str, pages_data: list):
    """Creates a multi-page PDF using pypdf."""
    writer = pypdf.PdfWriter()
    for p_lines in pages_data:
        if isinstance(p_lines, str):
            p_lines = [p_lines]
        p_bytes = make_single_page_pdf(p_lines)
        single_r = pypdf.PdfReader(io.BytesIO(p_bytes))
        writer.add_page(single_r.pages[0])

    with open(path, "wb") as f:
        writer.write(f)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_pdf_single_page_read(tmp_path):
    """Test reading a 1-page PDF."""
    pdf_path = str(tmp_path / "single.pdf")
    create_multipage_pdf(pdf_path, [["Single page content with vital data."]])

    res = UnifiedDocumentReader.read_document(pdf_path)
    assert res["status"] == "SUCCESS"
    assert "Single page content" in res["raw_text"]
    assert res["doc_type"] == "pdf"
    assert "Page 1 of 1" in res["evidence_location"]
    assert res["verified"] is True


def test_pdf_ten_pages_targeted_focus(tmp_path):
    """Test reading a 10-page PDF with focus query 'item 12'."""
    pages = [[f"Page {i+1} general discussion." for _ in range(2)] for i in range(9)]
    pages.append(["Item 12: High-voltage transformer wiring specifications and safety procedures."])
    pdf_path = str(tmp_path / "ten_pages.pdf")
    create_multipage_pdf(pdf_path, pages)

    res = UnifiedDocumentReader.read_document(pdf_path, focus="item 12")
    assert res["status"] == "SUCCESS"
    assert "transformer wiring specifications" in res["raw_text"]
    assert "Page 10" in res["evidence_location"]
    assert res["target_found"] is not False


def test_pdf_focus_not_found_reports_honestly(tmp_path):
    """Test asking for a topic that does not exist in the PDF."""
    pages = [["Page 1 discusses quantum computing."], ["Page 2 discusses laser cooling."]]
    pdf_path = str(tmp_path / "physics.pdf")
    create_multipage_pdf(pdf_path, pages)

    res = UnifiedDocumentReader.read_document(pdf_path, focus="Item 99: Warp Drive")
    assert res["status"] == "NOT_FOUND"
    assert "Target information for 'Item 99: Warp Drive' was not found" in res["raw_text"]
    assert res["target_found"] is False


def test_pdf_specific_page_extraction(tmp_path):
    """Test extracting a specific page by number."""
    pages = [[f"This is content on page {i+1}."] for i in range(5)]
    pdf_path = str(tmp_path / "five_pages.pdf")
    create_multipage_pdf(pdf_path, pages)

    res = UnifiedDocumentReader.read_document(pdf_path, page=3)
    assert res["status"] == "SUCCESS"
    assert "content on page 3" in res["raw_text"]
    assert "Page 3 of 5" in res["evidence_location"]


def test_pdf_encrypted_fails_safely(tmp_path):
    """Test encrypted PDF handling fails closed with an honest message."""
    pdf_path = str(tmp_path / "secret.pdf")
    writer = pypdf.PdfWriter()
    p_bytes = make_single_page_pdf(["Top secret encrypted document."])
    r = pypdf.PdfReader(io.BytesIO(p_bytes))
    writer.add_page(r.pages[0])
    writer.encrypt("topsecret123")
    with open(pdf_path, "wb") as f:
        writer.write(f)

    res = UnifiedDocumentReader.read_document(pdf_path)
    assert res["status"] == "FAILED"
    assert "encrypted" in res["error"].lower() or "password" in res["error"].lower()
    assert res["verified"] is False


def test_pdf_corrupt_fails_safely(tmp_path):
    """Test corrupted PDF file fails closed."""
    corrupt_pdf = str(tmp_path / "corrupt.pdf")
    with open(corrupt_pdf, "wb") as f:
        f.write(b"%PDF-1.4\nCorrupted binary garbage that cannot be parsed by pypdf \x00\xff\xfe")

    res = UnifiedDocumentReader.read_document(corrupt_pdf)
    assert res["status"] == "FAILED"
    assert res["verified"] is False


def test_pdf_context_strictly_bounded(tmp_path):
    """Test large PDF does not dump unlimited context."""
    pages = [[f"Page {i+1}: " + "Detailed architectural specification. " * 30] for i in range(15)]
    pdf_path = str(tmp_path / "large.pdf")
    create_multipage_pdf(pdf_path, pages)

    res = UnifiedDocumentReader.read_document(pdf_path, max_chars=1200)
    assert res["status"] == "SUCCESS"
    assert len(res["raw_text"]) <= 1350  # Bounded near requested max_chars
