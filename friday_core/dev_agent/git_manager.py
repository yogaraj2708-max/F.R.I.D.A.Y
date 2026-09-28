"""
F.R.I.D.A.Y. 3.0 — Developer Agent Git Version Control Manager
Performs git status inspection, file staging, and commit execution with human confirmation gating.
"""

import subprocess
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("FRIDAY.GitManager")


class GitManager:
    """
    Manages git operations with safety confirmation gates.
    """
    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root or "."

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True
        )

    def get_status(self) -> List[str]:
        """Returns list of modified, untracked, or staged files."""
        proc = self._run_git(["status", "--porcelain"])
        if proc.returncode != 0:
            return []
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return lines

    def stage_files(self, file_paths: List[str]) -> bool:
        """Runs git add for specified files."""
        if not file_paths:
            return True
        proc = self._run_git(["add"] + file_paths)
        return proc.returncode == 0

    def commit(self, message: str, approved_by_user: bool = False) -> Dict[str, Any]:
        """
        Creates a git commit.
        Enforces that approved_by_user must be True for human-in-the-loop safety.
        """
        if not approved_by_user:
            return {
                "success": False,
                "error": "Git commit rejected: Explicit human approval is required.",
                "commit_hash": None
            }

        if not message.strip():
            return {
                "success": False,
                "error": "Commit message cannot be empty.",
                "commit_hash": None
            }

        proc = self._run_git(["commit", "-m", message])
        if proc.returncode != 0:
            return {
                "success": False,
                "error": proc.stderr.strip() or proc.stdout.strip(),
                "commit_hash": None
            }

        # Retrieve commit hash
        hash_proc = self._run_git(["rev-parse", "--short", "HEAD"])
        commit_hash = hash_proc.stdout.strip() if hash_proc.returncode == 0 else "unknown"

        return {
            "success": True,
            "commit_hash": commit_hash,
            "message": message
        }
