"""
F.R.I.D.A.Y. 3.0 — Structured Document Agent Package
Provides structural parsing, document mapping, targeted region extraction,
bounded context editing, independent write-back verification, and anti-overflow guards for DOCX documents.
"""

from friday_core.document.models import (
    DocumentMap,
    DocumentHeading,
    DocumentParagraph,
    DocumentTable,
    DocumentCell,
    DocumentSection,
    DocEditOperation,
    DocEditRequest,
    DocEditResult,
    RelevantRegion
)
from friday_core.document.parser import DocxStructuralParser
from friday_core.document.editor import DocxStructuredEditor
from friday_core.document.verifier import DocxIndependentVerifier
from friday_core.document.agent import StructuredDocumentAgent
from friday_core.document.pdf_worker import (
    PDFAnalysisWorker,
    PDFAnalysisTask,
    PDFAnalysisResult
)
from friday_core.document.file_detector import (
    DocumentType,
    FileDetectionResult,
    detect_and_validate_file,
    validate_file_path
)
from friday_core.document.reader import UnifiedDocumentReader
from friday_core.document.unified_editor import UnifiedDocumentEditor

__all__ = [
    "DocumentMap",
    "DocumentHeading",
    "DocumentParagraph",
    "DocumentTable",
    "DocumentCell",
    "DocumentSection",
    "DocEditOperation",
    "DocEditRequest",
    "DocEditResult",
    "RelevantRegion",
    "DocxStructuralParser",
    "DocxStructuredEditor",
    "DocxIndependentVerifier",
    "StructuredDocumentAgent",
    "PDFAnalysisWorker",
    "PDFAnalysisTask",
    "PDFAnalysisResult",
    "DocumentType",
    "FileDetectionResult",
    "detect_and_validate_file",
    "validate_file_path",
    "UnifiedDocumentReader",
    "UnifiedDocumentEditor",
]

