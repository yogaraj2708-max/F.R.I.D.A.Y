"""
F.R.I.D.A.Y. 3.0 — Multi-Format Document Extractors
Extracts text and structured sections from .pdf, .docx, .xlsx, .md, .txt, .csv, and source code.
Preserves page and section metadata for provenance citations.
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger("FRIDAY.RAG.Extractors")

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


class DocumentExtractor:
    """
    Multi-format text and section extractor with strict metadata preservation.
    """

    @classmethod
    def extract(cls, file_path: str) -> List[Tuple[str, str]]:
        """
        Extracts content from a file as a list of (section_or_page, text) tuples.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Target document not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext in [".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml", ".ini", ".cfg"]:
            return cls._extract_plaintext(file_path)
        elif ext == ".pdf":
            return cls._extract_pdf(file_path)
        elif ext == ".docx":
            return cls._extract_docx(file_path)
        elif ext == ".xlsx":
            return cls._extract_xlsx(file_path)
        else:
            # Fallback to UTF-8 plaintext extraction
            return cls._extract_plaintext(file_path)

    @staticmethod
    def _extract_plaintext(file_path: str) -> List[Tuple[str, str]]:
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                return [("full_document", content)]
            except UnicodeDecodeError:
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [("full_document", content)]

    @staticmethod
    def _extract_pdf(file_path: str) -> List[Tuple[str, str]]:
        if not PYPDF_AVAILABLE:
            raise RuntimeError("pypdf is required for PDF extraction.")

        results = []
        try:
            reader = pypdf.PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    results.append((f"p.{idx + 1}", text.strip()))
        except Exception as e:
            logger.error(f"Error parsing PDF '{file_path}': {e}")
            raise
        return results if results else [("p.1", "")]

    @staticmethod
    def _extract_docx(file_path: str) -> List[Tuple[str, str]]:
        """
        Extracts paragraphs from DOCX via standard library zipfile and XML parsing.
        Zero external dependency required.
        """
        results = []
        try:
            with zipfile.ZipFile(file_path, "r") as docx_zip:
                if "word/document.xml" not in docx_zip.namelist():
                    raise ValueError("Invalid DOCX format: word/document.xml missing.")
                xml_content = docx_zip.read("word/document.xml")
                root = ET.fromstring(xml_content)

                # Word XML namespaces
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = []
                for p in root.findall(".//w:p", ns):
                    texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
                    if texts:
                        paragraphs.append("".join(texts))

                full_text = "\n\n".join(paragraphs)
                results.append(("document_body", full_text))
        except Exception as e:
            logger.error(f"Error extracting DOCX '{file_path}': {e}")
            raise
        return results

    @staticmethod
    def _extract_xlsx(file_path: str) -> List[Tuple[str, str]]:
        """
        Extracts tabular string tokens from XLSX via zipfile and sharedStrings.xml.
        """
        results = []
        try:
            with zipfile.ZipFile(file_path, "r") as xlsx_zip:
                shared_strings = []
                if "xl/sharedStrings.xml" in xlsx_zip.namelist():
                    ss_xml = xlsx_zip.read("xl/sharedStrings.xml")
                    root = ET.fromstring(ss_xml)
                    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    for si in root.findall(".//s:si", ns):
                        t_elems = si.findall(".//s:t", ns)
                        shared_strings.append("".join([t.text or "" for t in t_elems]))
                full_text = " | ".join([s for s in shared_strings if s.strip()])
                results.append(("spreadsheet_cells", full_text))
        except Exception as e:
            logger.error(f"Error extracting XLSX '{file_path}': {e}")
            raise
        return results
