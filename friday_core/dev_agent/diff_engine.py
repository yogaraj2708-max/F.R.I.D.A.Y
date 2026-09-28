"""
F.R.I.D.A.Y. 3.0 — Diff Engine & Syntax Validator
Computes unified diffs, checks Python AST syntax, and applies atomic patches with rollback.
"""

import os
import ast
import difflib
import logging
from typing import List, Tuple, Optional
from friday_core.dev_agent.models import CodeFileChange

logger = logging.getLogger("FRIDAY.DiffEngine")


class DiffEngine:
    """
    Computes diffs, validates syntax, and writes verified code edits.
    """

    @classmethod
    def compute_diff(cls, file_path: str, original: str, proposed: str) -> str:
        orig_lines = original.splitlines(keepends=True)
        prop_lines = proposed.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines,
            prop_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=""
        ))
        return "".join(diff_lines)

    @classmethod
    def validate_python_syntax(cls, code: str, filename: str = "<string>") -> Tuple[bool, Optional[str]]:
        """Parses code into Python AST to ensure syntax validity."""
        try:
            ast.parse(code, filename=filename)
            return True, None
        except SyntaxError as se:
            err = f"SyntaxError in {filename} at line {se.lineno}: {se.msg}"
            logger.warning(err)
            return False, err
        except Exception as ex:
            return False, str(ex)

    @classmethod
    def create_change_proposal(cls, file_path: str, proposed_content: str) -> CodeFileChange:
        orig_content = ""
        is_new = not os.path.exists(file_path)
        if not is_new:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    orig_content = f.read()
            except Exception:
                pass

        diff = cls.compute_diff(file_path, orig_content, proposed_content)
        return CodeFileChange(
            file_path=file_path,
            original_content=orig_content,
            proposed_content=proposed_content,
            diff=diff,
            is_new=is_new
        )

    @classmethod
    def apply_change(cls, change: CodeFileChange) -> bool:
        """Writes proposed content to file with directory creation and syntax validation."""
        if change.file_path.endswith(".py"):
            valid, err = cls.validate_python_syntax(change.proposed_content, change.file_path)
            if not valid:
                logger.error(f"Refusing to write {change.file_path}: invalid syntax ({err})")
                return False

        try:
            dest_dir = os.path.dirname(os.path.abspath(change.file_path))
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            with open(change.file_path, "w", encoding="utf-8") as f:
                f.write(change.proposed_content)
            return True
        except Exception as e:
            logger.error(f"Failed to apply change to {change.file_path}: {e}")
            return False

    @classmethod
    def rollback_change(cls, change: CodeFileChange) -> bool:
        """Restores original content or deletes newly created file."""
        try:
            if change.is_new:
                if os.path.exists(change.file_path):
                    os.remove(change.file_path)
            else:
                with open(change.file_path, "w", encoding="utf-8") as f:
                    f.write(change.original_content)
            return True
        except Exception as e:
            logger.error(f"Rollback failed for {change.file_path}: {e}")
            return False
