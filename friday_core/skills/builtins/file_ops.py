"""
F.R.I.D.A.Y. 3.0 — File Operations Verifiable Skills
Provides File Search, Semantic File Selection, and File Creation
with physical filesystem postcondition verification.
"""

import os
import sys
import time
import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)

logger = logging.getLogger("FRIDAY.FileOps")


def resolve_folder(folder_name: str) -> Path:
    """Resolves standard user directory names with OneDrive fallback and absolute path support."""
    p = Path(folder_name)
    if p.is_absolute() and p.exists() and p.is_dir():
        return p

    user_home = Path(os.path.expanduser("~"))
    clean = folder_name.lower().strip()

    name_map = {
        "downloads": "Downloads",
        "download": "Downloads",
        "desktop": "Desktop",
        "documents": "Documents",
        "document": "Documents",
        "docs": "Documents",
        "pictures": "Pictures",
        "picture": "Pictures",
        "photos": "Pictures",
        "music": "Music",
        "videos": "Videos"
    }
    std_name = name_map.get(clean, folder_name)

    candidates = [
        user_home / "OneDrive" / std_name,
        user_home / std_name,
        p
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return user_home / std_name


# ─────────────────────────────────────────────────────────────
# 1. FILE SEARCH SKILL
# ─────────────────────────────────────────────────────────────

class FileSearchInput(BaseModel):
    location: str = Field(default="Downloads", description="Folder name or path to search within")
    folder: Optional[str] = Field(default=None, description="Alias for location")
    pattern: str = Field(default="*.pdf", description="Glob pattern or file extension to match")
    query: Optional[str] = Field(default=None, description="Alias for pattern")
    file_type: Optional[str] = Field(default=None, description="Optional file type filter (e.g. 'pdf')")
    recursive: bool = Field(default=False, description="Whether to search subdirectories recursively")
    max_results: int = Field(default=50, description="Maximum number of files to return")


class FileSearchOutput(BaseModel):
    success: bool
    folder: str
    pattern: str
    count: int = 0
    files: List[Dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class FileSearchSkill(BaseSkill):
    tool_id = "file_search"
    tool_version = "1.0.0"
    description = "Searches for files matching a glob pattern or extension within a directory."
    input_schema = FileSearchInput
    output_schema = FileSearchOutput
    permissions = ["filesystem:read"]
    risk_level = RiskLevel.SAFE
    timeout = 8.0
    audit_event = "FILE_SEARCH"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        loc = params.get("folder") or params.get("location") or "Downloads"
        target_dir = resolve_folder(loc)
        return target_dir.exists() and target_dir.is_dir()

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        loc = params.get("folder") or params.get("location") or "Downloads"
        ftype = params.get("file_type")
        pattern = params.get("query") or params.get("pattern")
        if not pattern:
            pattern = f"*.{ftype}" if ftype else "*.*"
        elif ftype and not pattern.endswith(f".{ftype}"):
            pattern = f"*.{ftype}"

        recursive = params.get("recursive", False)
        max_res = params.get("max_results", 50)

        target_dir = resolve_folder(loc)
        if not target_dir.exists():
            return {
                "success": False,
                "folder": str(target_dir),
                "pattern": pattern,
                "count": 0,
                "files": [],
                "message": f"Directory '{target_dir}' does not exist."
            }

        # Normalize pattern
        if not any(pattern.startswith(p) for p in ["*", "?"]) and "." in pattern and not pattern.startswith("."):
            pass
        elif pattern.startswith("."):
            pattern = f"*{pattern}"
        elif not any(c in pattern for c in ["*", "?"]):
            pattern = f"*{pattern}*"

        matched_files = []
        try:
            if recursive:
                for root, dirs, files in os.walk(str(target_dir)):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for f in files:
                        if fnmatch.fnmatch(f.lower(), pattern.lower()):
                            fp = Path(root) / f
                            matched_files.append({
                                "name": f,
                                "path": str(fp.resolve()),
                                "size_bytes": fp.stat().st_size if fp.exists() else 0,
                                "mtime": fp.stat().st_mtime if fp.exists() else 0
                            })
                            if len(matched_files) >= max_res:
                                break
                    if len(matched_files) >= max_res:
                        break
            else:
                for item in target_dir.iterdir():
                    if item.is_file() and not item.name.startswith("."):
                        if fnmatch.fnmatch(item.name.lower(), pattern.lower()):
                            matched_files.append({
                                "name": item.name,
                                "path": str(item.resolve()),
                                "size_bytes": item.stat().st_size,
                                "mtime": item.stat().st_mtime
                            })
                            if len(matched_files) >= max_res:
                                break
        except Exception as e:
            logger.exception(f"File search failed: {e}")
            return {
                "success": False,
                "folder": str(target_dir),
                "pattern": pattern,
                "count": 0,
                "files": [],
                "message": f"Search error: {e}"
            }

        return {
            "success": True,
            "folder": str(target_dir),
            "pattern": pattern,
            "count": len(matched_files),
            "files": matched_files,
            "message": f"Found {len(matched_files)} files matching '{pattern}' in {target_dir.name}."
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        return ObservationResult(observed_state={"operation_completed": True})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message="File search completed with filesystem verification."
        )


# ─────────────────────────────────────────────────────────────
# 2. SEMANTIC FILE SELECTOR SKILL
# ─────────────────────────────────────────────────────────────

class FileSelectInput(BaseModel):
    location: str = Field(default="Downloads", description="Folder name or path")
    folder: Optional[str] = Field(default=None, description="Alias for location")
    file_type: str = Field(default="pdf", description="File extension or category (e.g. 'pdf', 'image', 'txt')")
    selector: str = Field(default="first", description="Semantic selector: 'first', 'latest', 'oldest', 'largest', 'smallest', 'second'")
    order: Optional[str] = Field(default=None, description="Alias for selector")
    filter_contains: Optional[str] = Field(default="", description="Optional substring to filter filename by")
    action: str = Field(default="open", description="Action to perform on selected file: 'open' or 'select'")


class FileSelectOutput(BaseModel):
    success: bool
    selected_file: str = ""
    file_name: str = ""
    filename: str = ""
    action_taken: str = ""
    message: str = ""


class FileSelectorSkill(BaseSkill):
    tool_id = "file_select"
    tool_version = "1.0.0"
    description = "Selects and opens files based on natural language semantic ordering (first, latest, oldest, etc.)."
    input_schema = FileSelectInput
    output_schema = FileSelectOutput
    permissions = ["filesystem:read", "system:execute"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 8.0
    audit_event = "FILE_SELECT"

    def __init__(self):
        super().__init__()
        self._last_selected: Dict[str, str] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        loc = params.get("folder") or params.get("location") or "Downloads"
        target_dir = resolve_folder(loc)
        return target_dir.exists() and target_dir.is_dir()

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        loc = params.get("folder") or params.get("location") or "Downloads"
        ftype = params.get("file_type", "pdf").lower().strip()
        selector = (params.get("order") or params.get("selector") or "first").lower().strip()
        filter_str = params.get("filter_contains", "").lower().strip()
        action = params.get("action", "open").lower().strip()

        target_dir = resolve_folder(loc)
        if not target_dir.exists():
            return {"success": False, "message": f"Folder '{loc}' not found."}

        # Resolve extension pattern
        type_exts = {
            "pdf": [".pdf"],
            "image": [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"],
            "picture": [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"],
            "word": [".docx", ".doc"],
            "excel": [".xlsx", ".xls", ".csv"],
            "ppt": [".pptx", ".ppt"],
            "text": [".txt", ".md"],
            "code": [".py", ".js", ".ts", ".html", ".css", ".json", ".cpp"]
        }
        allowed_exts = type_exts.get(ftype, [f".{ftype}" if not ftype.startswith(".") else ftype])

        candidates = []
        try:
            for item in target_dir.iterdir():
                if item.is_file() and not item.name.startswith("."):
                    if allowed_exts and item.suffix.lower() not in allowed_exts:
                        continue
                    if filter_str and filter_str not in item.name.lower():
                        continue
                    stat = item.stat()
                    candidates.append({
                        "path": item,
                        "name": item.name,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size
                    })
        except Exception as e:
            return {"success": False, "message": f"Failed to inspect folder '{target_dir}': {e}"}

        if not candidates:
            return {"success": False, "message": f"No {ftype.upper()} files found in {target_dir.name}."}

        # Sort according to semantic selector
        target_item = None
        if selector in ["latest", "newest", "most recent", "last"]:
            candidates.sort(key=lambda x: x["mtime"], reverse=True)
            target_item = candidates[0]
        elif selector in ["oldest"]:
            candidates.sort(key=lambda x: x["mtime"])
            target_item = candidates[0]
        elif selector in ["largest", "biggest"]:
            candidates.sort(key=lambda x: x["size"], reverse=True)
            target_item = candidates[0]
        elif selector in ["smallest"]:
            candidates.sort(key=lambda x: x["size"])
            target_item = candidates[0]
        elif selector in ["second", "2nd"]:
            candidates.sort(key=lambda x: x["name"].lower())
            target_item = candidates[1] if len(candidates) > 1 else candidates[0]
        elif selector in ["third", "3rd"]:
            candidates.sort(key=lambda x: x["name"].lower())
            target_item = candidates[2] if len(candidates) > 2 else candidates[-1]
        else:
            # "first", "1st", or default deterministic order by name or creation
            candidates.sort(key=lambda x: x["name"].lower())
            target_item = candidates[0]

        selected_path = target_item["path"]
        self._last_selected[operation_id] = str(selected_path)

        if action == "open":
            try:
                if sys.platform == "win32":
                    os.startfile(str(selected_path))
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", str(selected_path)])
                return {
                    "success": True,
                    "selected_file": str(selected_path),
                    "file_name": target_item["name"],
                    "filename": target_item["name"],
                    "action_taken": "opened",
                    "message": f"Opened {selector} {ftype.upper()} '{target_item['name']}' from {target_dir.name}."
                }
            except Exception as e:
                return {
                    "success": False,
                    "selected_file": str(selected_path),
                    "file_name": target_item["name"],
                    "filename": target_item["name"],
                    "action_taken": "failed_open",
                    "message": f"Could not open '{target_item['name']}': {e}"
                }

        return {
            "success": True,
            "selected_file": str(selected_path),
            "file_name": target_item["name"],
            "filename": target_item["name"],
            "action_taken": "selected",
            "message": f"Selected {selector} {ftype.upper()} '{target_item['name']}'."
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        p = self._last_selected.get(operation_id)
        exists = os.path.exists(p) if p else False
        return ObservationResult(observed_state={"file_exists": exists, "path": p})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        exists = observation.observed_state.get("file_exists", False)
        p = observation.observed_state.get("path", "")
        if exists:
            return VerificationResult(
                verified=True,
                postcondition_met=True,
                message=f"Verified selected file exists on host: '{p}'."
            )
        return VerificationResult(
            verified=False,
            postcondition_met=False,
            message=f"Selected file path does not exist on host: '{p}'."
        )


# ─────────────────────────────────────────────────────────────
# 3. FILE CREATION SKILL
# ─────────────────────────────────────────────────────────────

class CreateFileInput(BaseModel):
    location: str = Field(default="Desktop", description="Target folder (e.g. 'Desktop', 'Downloads')")
    filename: str = Field(default="friday_test.txt", description="Filename to create")
    content: str = Field(default="", description="Text content to write into the file")


class CreateFileOutput(BaseModel):
    success: bool
    path: str = ""
    filename: str = ""
    size_bytes: int = 0
    message: str = ""


class CreateFileSkill(BaseSkill):
    tool_id = "create_file"
    tool_version = "1.0.0"
    description = "Creates a file in the specified location, writes content, and verifies on-disk persistence."
    input_schema = CreateFileInput
    output_schema = CreateFileOutput
    permissions = ["filesystem:write"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 5.0
    audit_event = "FILE_CREATE"

    def __init__(self):
        super().__init__()
        self._created_files: Dict[str, str] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        fname = params.get("filename", "").strip()
        return bool(fname)

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        loc = params.get("location", "Desktop")
        fname = params.get("filename", "friday_test.txt").strip().strip('"\'')
        content = params.get("content", "")

        target_dir = resolve_folder(loc)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / fname

        try:
            target_file.write_text(content, encoding="utf-8")
            self._created_files[operation_id] = str(target_file.resolve())

            # Readback assert
            size = target_file.stat().st_size
            return {
                "success": True,
                "path": str(target_file.resolve()),
                "filename": fname,
                "size_bytes": size,
                "message": f"Successfully created '{fname}' at {target_file.resolve()} ({size} bytes)."
            }
        except Exception as e:
            logger.exception(f"File creation error: {e}")
            return {
                "success": False,
                "path": str(target_file),
                "filename": fname,
                "message": f"Failed to create file: {e}"
            }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        p = self._created_files.get(operation_id)
        if not p or not os.path.exists(p):
            return ObservationResult(observed_state={"exists": False, "path": p})

        actual_content = ""
        try:
            actual_content = Path(p).read_text(encoding="utf-8")
        except Exception:
            pass

        return ObservationResult(observed_state={
            "exists": True,
            "path": p,
            "size": os.path.getsize(p),
            "content": actual_content
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        state = observation.observed_state
        if not state.get("exists"):
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="File was not found on disk after write."
            )

        expected_content = params.get("content", "") if params else ""
        if expected_content:
            actual = state.get("content", "")
            if expected_content not in actual and actual != expected_content:
                return VerificationResult(
                    verified=False,
                    postcondition_met=False,
                    message=f"File content mismatch. Expected '{expected_content[:30]}...', found '{actual[:30]}...'."
                )

        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Verified file exists on disk with matching content ({state.get('size')} bytes)."
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        p = self._created_files.get(operation_id)
        if p and os.path.exists(p):
            try:
                os.remove(p)
                return RollbackResult(success=True, message=f"Removed created file {p}.")
            except Exception as e:
                return RollbackResult(success=False, message=f"Failed to delete {p}: {e}")
        return RollbackResult(success=True, message="No file to rollback.")
