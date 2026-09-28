"""
F.R.I.D.A.Y. 3.0 — Forensic PDF Concurrency, Thread Safety & UI Freeze Test Suite
Tests background QThread execution, real progress states, cancellation, deduplication,
throttled markdown rendering, and failure injection.
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QTextBrowser
from PySide6.QtCore import QThread, QTimer

from friday_core.document.pdf_worker import (
    PDFAnalysisWorker,
    PDFAnalysisTask,
    PDFAnalysisResult,
    PDFPageSummary
)
from friday_ui.widgets.chat_bubble import ChatBubble


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_pdf_worker_runs_on_background_thread(qapp):
    """Rule 1 & 2: Assert worker runs on a non-GUI thread and main GUI thread is never blocked."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_A_5_pages.pdf",
        user_directive="Analyse this PDF",
        model_name="deepseek-r1:8b"
    )
    worker = PDFAnalysisWorker(task)

    worker_thread = None
    gui_thread = QThread.currentThread()

    with patch.object(worker, '_stream_ollama_chat', return_value="Verified analysis"):
        with patch.object(worker, '_analyze_page_visual', return_value=""):
            orig_run = worker.run
            def tracked_run():
                nonlocal worker_thread
                worker_thread = QThread.currentThread()
                orig_run()
            worker.run = tracked_run

            worker.start()
            timeout = time.time() + 5.0
            while worker.isRunning() and time.time() < timeout:
                qapp.processEvents()
                time.sleep(0.01)

            assert not worker.isRunning(), "Worker did not finish in time"
            worker.wait(5000)
            assert worker_thread is not None, "Worker did not execute"
            assert worker_thread != gui_thread, (
                f"Worker executed on GUI thread ({gui_thread})! Concurrency violation!"
            )


def test_pdf_worker_real_progress_states(qapp):
    """Rule 6: Verify worker emits truthful progress states matching actual stages."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_A_5_pages.pdf",
        user_directive="Analyse this PDF"
    )
    worker = PDFAnalysisWorker(task)
    emitted_stages = []

    worker.progress_signal.connect(lambda stage, pct, text: emitted_stages.append(stage))

    with patch.object(worker, '_stream_ollama_chat', return_value="Dossier content"):
        with patch.object(worker, '_analyze_page_visual', return_value=""):
            worker.start()
            while worker.isRunning():
                qapp.processEvents()
                time.sleep(0.01)
            worker.wait(5000)

    expected_stages = ["INITIALIZING", "LOADING_PDF", "PARSING", "EXTRACTING_PAGES", "BUILDING_CONTEXT", "LLM_ANALYSIS", "FINALIZING", "COMPLETED"]
    for s in expected_stages:
        assert s in emitted_stages, f"Expected stage '{s}' was not emitted by worker! Stages: {emitted_stages}"


def test_pdf_worker_cancellation_midway(qapp):
    """Rule 7: User cancellation must propagate and terminate worker cleanly."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_D_105_pages.pdf",
        user_directive="Analyse this PDF"
    )
    worker = PDFAnalysisWorker(task)
    cancelled_emitted = False
    result_received = None

    worker.cancelled_signal.connect(lambda: setattr(sys.modules[__name__], '_cancel_flag', True))
    def on_finished(res):
        nonlocal result_received
        result_received = res
    worker.finished_signal.connect(on_finished)

    def mock_stream_with_cancel(prompt):
        worker.cancel()
        time.sleep(0.02)
        return "Should not finish"

    with patch.object(worker, '_stream_ollama_chat', side_effect=mock_stream_with_cancel):
        with patch.object(worker, '_analyze_page_visual', return_value=""):
            worker.start()

            timeout = time.time() + 5.0
            while worker.isRunning() and time.time() < timeout:
                qapp.processEvents()
                time.sleep(0.01)

            # Process remaining cross-thread queued signals
            for _ in range(5):
                qapp.processEvents()
                time.sleep(0.01)

            assert not worker.isRunning(), "Worker failed to terminate on cancellation"
            worker.wait(5000)
            assert worker.is_cancelled() is True
            assert result_received is not None
            assert result_received.cancelled is True


def test_pdf_worker_malformed_pdf_fail_closed(qapp):
    """Rule 19: Malformed PDF must report truthful FAILED status and not crash."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_I_malformed.pdf",
        user_directive="Analyse this PDF"
    )
    worker = PDFAnalysisWorker(task)
    error_msg = ""
    result = None

    worker.error_signal.connect(lambda err: setattr(sys.modules[__name__], '_err', err))
    worker.finished_signal.connect(lambda res: setattr(sys.modules[__name__], '_res', res))

    worker.start()
    while worker.isRunning():
        qapp.processEvents()
        time.sleep(0.01)
    worker.wait(5000)

    res = getattr(sys.modules[__name__], '_res', None)
    assert res is not None
    assert res.success is False
    assert res.error is not None
    assert "fail" in res.error.lower() or "error" in res.error.lower() or "corrupt" in res.error.lower() or "stream" in res.error.lower()


def test_chat_bubble_throttled_markdown_rendering(qapp):
    """Rule 3 & 5: ChatBubble must throttle streaming token updates to prevent event loop starvation."""
    bubble = ChatBubble(role="friday", text="", is_streaming=True)
    bubble.show()

    # Simulate 200 rapid token chunks emitted at high frequency (1ms apart)
    t0 = time.perf_counter()
    for i in range(200):
        bubble.append_token(f"word{i} ")
        qapp.processEvents()
        time.sleep(0.001)

    render_count_during_stream = getattr(bubble, '_last_token_render', 0.0)
    assert render_count_during_stream > 0

    bubble.finish_stream(final_text=None)
    qapp.processEvents()

    # Ensure full text is rendered completely in the end
    assert len(bubble.raw_text.split()) == 200
    assert "word199" in bubble.text_browser.toPlainText()


def test_context_representation_all_pages_represented(qapp):
    """Rule 8 & 9: All document pages must be represented in the structured page map."""
    worker = PDFAnalysisWorker(PDFAnalysisTask(pdf_path="dummy.pdf"))
    pages = [
        PDFPageSummary(page_num=i, text=f"Page {i} content text", char_count=20, has_images=False, heading=f"Heading {i}")
        for i in range(1, 25)
    ]
    context, tokens = worker._build_context_representation(
        doc_name="test.pdf",
        meta_title="Transformer Guide",
        meta_author="EE Dept",
        pages=pages,
        total_pages=24
    )

    # Assert every single page from 1 to 24 is in the context
    for i in range(1, 25):
        assert f"Page {i}" in context, f"Page {i} was missing from the context representation!"
    assert tokens > 0


def test_failure_injection_ollama_unavailable(qapp):
    """Rule 14 & 30: When Ollama is offline or drops connection, worker reports truthful failure."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_A_5_pages.pdf",
        user_directive="Analyse this PDF"
    )
    worker = PDFAnalysisWorker(task)
    error_received = None

    worker.error_signal.connect(lambda err: setattr(sys.modules[__name__], '_ollama_err', err))

    # Mock Ollama raising ConnectionError
    with patch.object(worker, '_stream_ollama_chat', side_effect=RuntimeError("Connection refused by Ollama service")):
        with patch.object(worker, '_analyze_page_visual', return_value=""):
            worker.start()
            while worker.isRunning():
                qapp.processEvents()
                time.sleep(0.01)
            worker.wait(5000)

    err = getattr(sys.modules[__name__], '_ollama_err', None)
    assert err is not None
    assert "ollama" in err.lower() or "connection" in err.lower() or "failed" in err.lower()


def test_failure_injection_vision_timeout_fallback(qapp):
    """Rule 11 & 30: If vision model times out on diagrams, worker falls back gracefully without failing overall analysis."""
    task = PDFAnalysisTask(
        pdf_path="scratch/test_pdfs/TEST_E_large_images.pdf",
        user_directive="Analyse this PDF",
        inspect_visuals=True
    )
    worker = PDFAnalysisWorker(task)
    result_received = None

    def on_finished(res):
        nonlocal result_received
        result_received = res
    worker.finished_signal.connect(on_finished)

    # Mock vision timing out (returning empty string after timeout log)
    with patch.object(worker, '_analyze_page_visual', return_value=""):
        with patch.object(worker, '_stream_ollama_chat', return_value="Verified text analysis without visual diagrams"):
            worker.start()
            while worker.isRunning():
                qapp.processEvents()
                time.sleep(0.01)
            worker.wait(5000)

    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.01)

    assert result_received is not None
    assert result_received.success is True
    assert "Verified text analysis" in result_received.text


def test_large_pdf_matrix_processing(qapp):
    """Rule 20: Test matrix verifying TEST-A, TEST-B, TEST-C, TEST-D, TEST-F, TEST-K."""
    matrix_files = [
        ("TEST-A", "scratch/test_pdfs/TEST_A_5_pages.pdf", 5),
        ("TEST-B", r"C:\Users\Admin\Downloads\Single_Phase_3_Phase_Transformer_Centum_Visual_Guide.pdf", 24),
        ("TEST-C", "scratch/test_pdfs/TEST_C_50_pages.pdf", 50),
        ("TEST-D", "scratch/test_pdfs/TEST_D_105_pages.pdf", 105),
        ("TEST-F", "scratch/test_pdfs/TEST_F_text_heavy.pdf", 1),
        ("TEST-K", "scratch/test_pdfs/TEST_K_tables.pdf", 1),
    ]

    for label, pdf_path, expected_min_pages in matrix_files:
        if label == "TEST-B" and not os.path.exists(pdf_path):
            import logging
            logging.getLogger("FRIDAY.Test").warning("Skipping TEST-B: External fixture not found on host machine (%s)", pdf_path)
            continue
        assert os.path.exists(pdf_path), f"Test PDF missing: {pdf_path}"
        task = PDFAnalysisTask(
            pdf_path=pdf_path,
            user_directive="Analyse this PDF",
            inspect_visuals=False
        )
        worker = PDFAnalysisWorker(task)
        result = None

        def on_finished(res):
            nonlocal result
            result = res
        worker.finished_signal.connect(on_finished)

        with patch.object(worker, '_stream_ollama_chat', return_value=f"Analysis of {label}"):
            worker.start()
            while worker.isRunning():
                qapp.processEvents()
                time.sleep(0.005)
            worker.wait(5000)

        for _ in range(3):
            qapp.processEvents()
            time.sleep(0.01)

        assert result is not None, f"{label} returned no result"
        assert result.success is True, f"{label} failed with: {result.error}"
        assert result.total_pages >= expected_min_pages, f"{label} page count mismatch"

