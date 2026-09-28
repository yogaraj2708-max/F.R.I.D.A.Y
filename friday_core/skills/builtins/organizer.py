"""
F.R.I.D.A.Y. 3.0 — Autonomous File Organizer Verifiable Skill
Organizes files with transactional journaling, postcondition verification, and atomic rollback.
"""

from typing import Any, Dict, List, Optional, Tuple
import os
import shutil
from pathlib import Path
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)

EXTENSION_MAP = {
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".csv", ".pptx", ".odt"],
    "Images": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Media": [".mp3", ".wav", ".mp4", ".mkv", ".flv", ".mov"],
    "Code": [".py", ".js", ".html", ".css", ".json", ".cpp", ".java", ".ts"],
    "Installers": [".exe", ".msi", ".dmg"]
}


class FileOrganizerInput(BaseModel):
    directory_path: str = Field(..., min_length=1, description="Absolute path to the directory to organize")
    dry_run: bool = Field(default=False, description="Preview actions without moving files")


class FileOrganizerOutput(BaseModel):
    directory_path: str
    files_moved: int
    categories_created: List[str]
    dry_run: bool


class FileOrganizerSkill(BaseSkill):
    tool_id = "file_organizer"
    tool_version = "1.0.0"
    description = "Organizes files by type into categorized folders with rollback and postcondition verification."
    input_schema = FileOrganizerInput
    output_schema = FileOrganizerOutput
    permissions = ["filesystem:read", "filesystem:write"]
    risk_level = RiskLevel.CAUTION
    timeout = 15.0
    audit_event = "FILE_ORGANIZATION"

    def __init__(self):
        super().__init__()
        # Transaction journal: operation_id -> list of (dest_path, source_path) for rollback
        self._journal: Dict[str, List[Tuple[str, str]]] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        dir_path = params.get("directory_path", "")
        p = Path(dir_path)
        if not p.exists() or not p.is_dir():
            return False
        # Must be writable
        return os.access(dir_path, os.W_OK)

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        dir_path = Path(params["directory_path"])
        dry_run = params.get("dry_run", False)
        moves: List[Tuple[str, str]] = []
        categories_used = set()

        files = [f for f in dir_path.iterdir() if f.is_file()]

        for f in files:
            ext = f.suffix.lower()
            category = "Others"
            for cat, extensions in EXTENSION_MAP.items():
                if ext in extensions:
                    category = cat
                    break

            cat_dir = dir_path / category
            dest_file = cat_dir / f.name

            # Collision avoidance
            if dest_file.exists():
                counter = 1
                while dest_file.exists():
                    dest_file = cat_dir / f"{f.stem}_{counter}{f.suffix}"
                    counter += 1

            if not dry_run:
                cat_dir.mkdir(exist_ok=True)
                shutil.move(str(f), str(dest_file))
                moves.append((str(dest_file), str(f)))  # (current, original)

            categories_used.add(category)

        if not dry_run:
            self._journal[operation_id] = moves

        return {
            "directory_path": str(dir_path),
            "files_moved": len(moves) if not dry_run else len(files),
            "categories_created": sorted(list(categories_used)),
            "dry_run": dry_run
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        if params and params.get("dry_run"):
            return ObservationResult(observed_state={"dry_run": True, "files_verified": True})

        moves = self._journal.get(operation_id, [])
        all_exist = True
        missing = []

        for dest, _ in moves:
            if not os.path.exists(dest):
                all_exist = False
                missing.append(dest)

        return ObservationResult(observed_state={
            "files_verified": all_exist,
            "total_moved": len(moves),
            "missing_files": missing
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        if params and params.get("dry_run"):
            return VerificationResult(
                verified=True,
                postcondition_met=True,
                message="Dry-run file organization preview complete."
            )

        verified = observation.observed_state.get("files_verified", False)
        total = observation.observed_state.get("total_moved", 0)

        if not verified:
            missing = observation.observed_state.get("missing_files", [])
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Postcondition failed: {len(missing)} files missing after organization.",
                details={"missing": missing}
            )

        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Successfully organized and verified {total} files.",
            details={"total_moved": total}
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        moves = self._journal.get(operation_id, [])
        if not moves:
            return RollbackResult(success=True, message="No moves recorded for rollback.")

        reverted = []
        errors = []

        for dest, src in reversed(moves):
            try:
                if os.path.exists(dest):
                    shutil.move(dest, src)
                    reverted.append(src)
            except Exception as ex:
                errors.append(f"Failed to revert {dest} -> {src}: {ex}")

        # Clean empty category folders if possible
        if params:
            dir_path = Path(params["directory_path"])
            for cat in EXTENSION_MAP.keys():
                cat_dir = dir_path / cat
                try:
                    if cat_dir.exists() and not any(cat_dir.iterdir()):
                        cat_dir.rmdir()
                except Exception:
                    pass

        if errors:
            return RollbackResult(
                success=False,
                message=f"Rollback partially failed: {'; '.join(errors)}",
                reverted_changes=reverted
            )

        return RollbackResult(
            success=True,
            message=f"Rolled back {len(reverted)} files to original locations.",
            reverted_changes=reverted
        )
