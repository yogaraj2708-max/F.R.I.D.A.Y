"""
F.R.I.D.A.Y. 3.0 — Document Concurrency & Isolation Test Suite
Tests concurrent document operations across threads, separate session contexts,
and isolation between parallel document analyses.
"""

import os
import time
import concurrent.futures
import pytest

from friday_core.document.reader import UnifiedDocumentReader, clear_document_cache


@pytest.fixture(autouse=True)
def clean_cache():
    clear_document_cache()


def test_concurrent_document_reads(tmp_path):
    """Assert reading multiple different documents concurrently in thread pool executes cleanly with zero crosstalk."""
    doc_paths = []
    for i in range(5):
        p = str(tmp_path / f"doc_{i}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"Unique payload for document index {i}: SecretKey_{i*111}")
        doc_paths.append((i, p))

    results = {}

    def worker_read(item):
        idx, path = item
        res = UnifiedDocumentReader.read_document(path)
        return idx, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_read, item) for item in doc_paths]
        for f in concurrent.futures.as_completed(futures):
            idx, res = f.result()
            results[idx] = res

    assert len(results) == 5
    for idx, res in results.items():
        assert res["status"] == "SUCCESS"
        assert f"SecretKey_{idx*111}" in res["raw_text"]
        # Ensure no crosstalk from other documents
        for other_idx in range(5):
            if other_idx != idx:
                assert f"SecretKey_{other_idx*111}" not in res["raw_text"]


def test_concurrent_same_document_deduplication(tmp_path):
    """Assert concurrent reads on the same document are safe and return identical content."""
    doc_path = str(tmp_path / "shared.txt")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("Shared immutable specification content.")

    def read_shared():
        return UnifiedDocumentReader.read_document(doc_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(read_shared) for _ in range(4)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 4
    first_sha = results[0]["sha256"]
    for r in results:
        assert r["status"] == "SUCCESS"
        assert r["sha256"] == first_sha
        assert "Shared immutable specification" in r["raw_text"]
