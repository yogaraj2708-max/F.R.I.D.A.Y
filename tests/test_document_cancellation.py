"""
F.R.I.D.A.Y. 3.0 — Document Cancellation Test Suite
Tests cancellation of long PDF processing, thread-safe abort, and terminal CANCELLED states.
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread

from friday_core.document.pdf_worker import (
    PDFAnalysisWorker,
    PDFAnalysisTask,
    PDFAnalysisResult
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_pdf_worker_cancellation(qapp, tmp_path):
    """Assert cancelling PDFAnalysisWorker aborts execution and reaches terminal CANCELLED state."""
    pdf_file = str(tmp_path / "dummy.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4\n%dummy\n")

    task = PDFAnalysisTask(
        pdf_path=pdf_file,
        user_directive="Analyse full document"
    )
    worker = PDFAnalysisWorker(task)


    cancelled_emitted = False
    result_received = None

    def on_cancelled():
        nonlocal cancelled_emitted
        cancelled_emitted = True

    def on_result(res):
        nonlocal result_received
        result_received = res

    worker.cancelled_signal.connect(on_cancelled)
    worker.finished_signal.connect(on_result)


    # Immediately request cancellation
    worker.cancel()
    assert worker.is_cancelled() is True

    # Run the worker
    worker.start()
    timeout = time.time() + 3.0
    while worker.isRunning() and time.time() < timeout:
        qapp.processEvents()
        time.sleep(0.01)

    assert not worker.isRunning(), "Worker should have terminated promptly after cancellation"
    assert cancelled_emitted is True, "Worker should emit cancelled_signal on cancellation"
    if result_received:
        assert result_received.cancelled is True
        assert result_received.success is False
