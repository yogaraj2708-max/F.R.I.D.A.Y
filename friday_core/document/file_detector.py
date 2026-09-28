"""
F.R.I.D.A.Y. 3.0 — Zero-Trust Document File Detector & Security Guard
Enforces strict path security, magic byte validation, file size bounds, and extension verification.
Never trusts file extension alone. Rejects malformed, binary, empty, or traversed files fail-closed.
"""

import os
import re
import zipfile
import hashlib
import json
import csv
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    JSON = "json"
    CSV = "csv"
    SOURCE_CODE = "source_code"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


# Bounded limits (Section 4)
MAX_PDF_DOCX_BYTES = 25 * 1024 * 1024       # 25 MB
MAX_JSON_CSV_BYTES = 10 * 1024 * 1024       # 10 MB
MAX_TEXT_BYTES = 5 * 1024 * 1024           # 5 MB
MAX_EXTRACTED_CHARS = 3500                  # ~875 tokens
MAX_CSV_ROWS = 100
MAX_CSV_COLS = 50
MAX_JSON_DEPTH = 10
MAX_PDF_PAGES = 100
MAX_ATTACHMENT_COUNT = 5

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".ps1", ".bat", ".cmd", ".sql", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".xml"
}


@dataclass
class FileDetectionResult:
    doc_type: DocumentType
    canonical_path: str
    file_size: int
    sha256: str
    is_valid: bool
    mime_type: str = "application/octet-stream"
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentSecurityError(Exception):
    """Raised when a document path or access violates security boundaries."""
    pass


class DocumentFormatError(Exception):
    """Raised when a file fails magic byte or format validation."""
    pass


def is_sensitive_path(path_str: str) -> bool:
    """Checks if a path targets sensitive system or credential files."""
    norm = path_str.replace("\\", "/").lower()
    base = os.path.basename(norm)
    # Protected system directories
    if "/windows/system32" in norm or "\\windows\\system32" in path_str.lower() or "/system32/config" in norm:
        return True
    if "/etc/shadow" in norm or "/etc/passwd" in norm:
        return True
    # Protected sensitive filenames
    if base in ("sam", "security", "system", ".env", "id_rsa", "id_ed25519", "id_dsa"):
        return True
    if base.startswith("sam.") or base.endswith((".evtx", ".key")):
        return True
    if base.startswith(".env.") or base == ".env":
        return True
    return False


def validate_file_path(file_path: str, must_exist: bool = True, for_write: bool = False) -> Tuple[bool, str, str]:
    """
    Validates a file path against traversal, UNC shares, sensitive system locations, and symlink escapes.
    Returns: (is_safe: bool, canonical_path: str, error_message: str)
    """
    if not file_path or not str(file_path).strip():
        return False, "", "Empty file path provided."

    clean_path = str(file_path).strip()
    norm = clean_path.replace("\\", "/").lower()

    # 1. Path traversal checks
    if ".." in norm:
        return False, clean_path, "Access blocked: Directory traversal ('..') is prohibited."

    # 2. UNC network shares
    if clean_path.startswith("\\\\") or clean_path.startswith("//"):
        return False, clean_path, "Access blocked: UNC network paths are prohibited."

    # 3. Sensitive system files
    if is_sensitive_path(clean_path):
        return False, clean_path, "Access blocked: Path targets protected system files."

    # 4. Canonical path resolution
    try:
        abs_path = os.path.abspath(clean_path)
        real_path = os.path.realpath(abs_path)
    except Exception as e:
        return False, clean_path, f"Path resolution failed: {e}"

    # Verify real path does not target sensitive system paths after symlink resolution
    if is_sensitive_path(real_path):
        return False, real_path, "Access blocked: Symlink resolves to protected system files."

    # 5. Existence check
    if must_exist and not os.path.exists(real_path):
        return False, real_path, f"File not found: '{real_path}'"

    # 6. For write check (directory must exist or be creatable)
    if for_write:
        parent_dir = os.path.dirname(real_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                return False, real_path, f"Cannot create output directory: {e}"

    return True, real_path, ""


def compute_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file safely."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_and_validate_file(file_path: str) -> FileDetectionResult:
    """
    Performs zero-trust forensic validation of a file.
    Does not trust file extension alone. Validates magic bytes, file size,
    encoding, and structure.
    """
    is_safe, canonical_path, err = validate_file_path(file_path, must_exist=True)
    if not is_safe:
        return FileDetectionResult(
            doc_type=DocumentType.UNKNOWN,
            canonical_path=canonical_path or file_path,
            file_size=0,
            sha256="",
            is_valid=False,
            error=err
        )

    # 1. Size check
    try:
        file_size = os.path.getsize(canonical_path)
    except Exception as e:
        return FileDetectionResult(
            doc_type=DocumentType.UNKNOWN,
            canonical_path=canonical_path,
            file_size=0,
            sha256="",
            is_valid=False,
            error=f"Cannot inspect file size: {e}"
        )

    if file_size == 0:
        return FileDetectionResult(
            doc_type=DocumentType.UNKNOWN,
            canonical_path=canonical_path,
            file_size=0,
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            is_valid=False,
            error=f"File is empty (0 bytes): '{os.path.basename(canonical_path)}'"
        )

    file_hash = compute_sha256(canonical_path)
    ext = os.path.splitext(canonical_path)[1].lower()

    # Read leading bytes for magic signature checks
    try:
        with open(canonical_path, "rb") as f:
            header = f.read(1024)
    except Exception as e:
        return FileDetectionResult(
            doc_type=DocumentType.UNKNOWN,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=False,
            error=f"Unreadable file: {e}"
        )

    # 2. PDF Magic Bytes Check (%PDF-)
    if header.startswith(b"%PDF-") or b"%PDF-" in header[:1024]:
        if file_size > MAX_PDF_DOCX_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.PDF,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="application/pdf",
                error=f"PDF exceeds maximum bounded size of {MAX_PDF_DOCX_BYTES // (1024*1024)}MB ({file_size} bytes)."
            )
        # Verify parser can actually read the PDF trailer/pages
        try:
            import pypdf
            reader = pypdf.PdfReader(canonical_path)
            if reader.is_encrypted:
                return FileDetectionResult(
                    doc_type=DocumentType.PDF,
                    canonical_path=canonical_path,
                    file_size=file_size,
                    sha256=file_hash,
                    is_valid=False,
                    mime_type="application/pdf",
                    error="PDF is encrypted or password-protected. Decryption key required."
                )
            num_pages = len(reader.pages)
            return FileDetectionResult(
                doc_type=DocumentType.PDF,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=True,
                mime_type="application/pdf",
                metadata={"total_pages": num_pages, "is_encrypted": False}
            )
        except Exception as pe:
            err_str = str(pe)
            if "decrypt" in err_str.lower() or "password" in err_str.lower():
                err_msg = "PDF is encrypted or password-protected. Decryption key required."
            else:
                err_msg = f"Malformed or corrupted PDF: {pe}"
            return FileDetectionResult(
                doc_type=DocumentType.PDF,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="application/pdf",
                error=err_msg
            )

    # 3. DOCX Magic Bytes Check (PK\x03\x04 + zip entry word/document.xml or [Content_Types].xml)
    if header.startswith(b"PK\x03\x04"):
        if file_size > MAX_PDF_DOCX_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.DOCX,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                error=f"DOCX exceeds maximum bounded size of {MAX_PDF_DOCX_BYTES // (1024*1024)}MB ({file_size} bytes)."
            )
        try:
            with zipfile.ZipFile(canonical_path, "r") as zf:
                namelist = zf.namelist()
                if "[Content_Types].xml" in namelist or any(n.startswith("word/") for n in namelist):
                    return FileDetectionResult(
                        doc_type=DocumentType.DOCX,
                        canonical_path=canonical_path,
                        file_size=file_size,
                        sha256=file_hash,
                        is_valid=True,
                        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        metadata={"zip_entries": len(namelist)}
                    )
                else:
                    return FileDetectionResult(
                        doc_type=DocumentType.UNSUPPORTED,
                        canonical_path=canonical_path,
                        file_size=file_size,
                        sha256=file_hash,
                        is_valid=False,
                        error=f"ZIP archive does not contain Word document structure (not a valid DOCX)."
                    )
        except zipfile.BadZipFile:
            return FileDetectionResult(
                doc_type=DocumentType.DOCX,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                error="Corrupted DOCX: Bad ZIP archive."
            )

    # If extension claimed to be PDF or DOCX but magic bytes failed
    if ext == ".pdf":
        return FileDetectionResult(
            doc_type=DocumentType.PDF,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=False,
            error="File has .pdf extension but lacks '%PDF-' magic header signature."
        )
    if ext == ".docx":
        return FileDetectionResult(
            doc_type=DocumentType.DOCX,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=False,
            error="File has .docx extension but lacks 'PK\x03\x04' ZIP magic header signature."
        )

    # 4. Binary check: files containing null bytes \x00 in first 1024 bytes (excluding UTF-16 BOMs)
    has_utf16le_bom = header.startswith(b"\xff\xfe")
    has_utf16be_bom = header.startswith(b"\xfe\xff")
    if not (has_utf16le_bom or has_utf16be_bom) and b"\x00" in header:
        return FileDetectionResult(
            doc_type=DocumentType.UNSUPPORTED,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=False,
            error="Binary file rejected: Non-text binary content detected."
        )

    # 5. Read sample text decoding
    text_content = ""
    for encoding in ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"]:
        try:
            with open(canonical_path, "r", encoding=encoding) as tf:
                text_content = tf.read(65536)
                break
        except (UnicodeDecodeError, LookupError):
            continue

    if not text_content and file_size > 0:
        return FileDetectionResult(
            doc_type=DocumentType.UNKNOWN,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=False,
            error="Encoding detection failed: Unable to decode text content with UTF-8/UTF-16/CP1252."
        )

    stripped_sample = text_content.strip()

    # 6. JSON Detection
    if ext == ".json" or (stripped_sample.startswith(("{", "[")) and stripped_sample.endswith(("}", "]"))):
        if file_size > MAX_JSON_CSV_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.JSON,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="application/json",
                error=f"JSON file exceeds maximum size of {MAX_JSON_CSV_BYTES // (1024*1024)}MB."
            )
        try:
            with open(canonical_path, "r", encoding="utf-8", errors="replace") as jf:
                parsed_json = json.load(jf)
            return FileDetectionResult(
                doc_type=DocumentType.JSON,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=True,
                mime_type="application/json",
                metadata={"is_dict": isinstance(parsed_json, dict), "element_count": len(parsed_json)}
            )
        except json.JSONDecodeError as je:
            return FileDetectionResult(
                doc_type=DocumentType.JSON,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="application/json",
                error=f"Malformed JSON: {je}"
            )

    # 7. CSV Detection
    if ext == ".csv":
        if file_size > MAX_JSON_CSV_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.CSV,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                mime_type="text/csv",
                error=f"CSV file exceeds maximum size of {MAX_JSON_CSV_BYTES // (1024*1024)}MB."
            )
        try:
            with open(canonical_path, "r", encoding="utf-8", errors="replace") as cf:
                sample_lines = [cf.readline() for _ in range(5)]
                sample_text = "".join(sample_lines)
                delimiter = ","
                try:
                    dialect = csv.Sniffer().sniff(sample_text)
                    delimiter = dialect.delimiter
                except Exception:
                    # fallback check
                    if "\t" in sample_text:
                        delimiter = "\t"
                    elif ";" in sample_text:
                        delimiter = ";"

            return FileDetectionResult(
                doc_type=DocumentType.CSV,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=True,
                mime_type="text/csv",
                metadata={"delimiter": delimiter}
            )
        except Exception as ce:
            return FileDetectionResult(
                doc_type=DocumentType.CSV,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                error=f"Malformed CSV: {ce}"
            )

    # 8. Source Code Detection
    if ext in SOURCE_EXTENSIONS:
        if file_size > MAX_TEXT_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.SOURCE_CODE,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                error=f"Source code file exceeds maximum size of {MAX_TEXT_BYTES // (1024*1024)}MB."
            )
        return FileDetectionResult(
            doc_type=DocumentType.SOURCE_CODE,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=True,
            mime_type="text/plain",
            metadata={"extension": ext}
        )

    # 9. Markdown Detection
    if ext in [".md", ".markdown"]:
        if file_size > MAX_TEXT_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.MARKDOWN,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                error=f"Markdown file exceeds maximum size of {MAX_TEXT_BYTES // (1024*1024)}MB."
            )
        return FileDetectionResult(
            doc_type=DocumentType.MARKDOWN,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=True,
            mime_type="text/markdown"
        )

    # 10. Plain Text Detection (.txt or fallback)
    if ext in [".txt", ".log", ".text"] or not ext:
        if file_size > MAX_TEXT_BYTES:
            return FileDetectionResult(
                doc_type=DocumentType.TXT,
                canonical_path=canonical_path,
                file_size=file_size,
                sha256=file_hash,
                is_valid=False,
                error=f"Text file exceeds maximum size of {MAX_TEXT_BYTES // (1024*1024)}MB."
            )
        return FileDetectionResult(
            doc_type=DocumentType.TXT,
            canonical_path=canonical_path,
            file_size=file_size,
            sha256=file_hash,
            is_valid=True,
            mime_type="text/plain"
        )

    # Default unsupported format
    return FileDetectionResult(
        doc_type=DocumentType.UNSUPPORTED,
        canonical_path=canonical_path,
        file_size=file_size,
        sha256=file_hash,
        is_valid=False,
        error=f"Unsupported file format '{ext}' for document intelligence."
    )
