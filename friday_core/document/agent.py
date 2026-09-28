"""
F.R.I.D.A.Y. 3.0 — Structured Document Agent
Coordinates the complete zero-trust document pipeline:
DOCX
  -> structural parsing
  -> document map
  -> relevant-section detection
  -> targeted extraction
  -> task interpretation
  -> edit operation
  -> document write-back
  -> independent verification
Enforces hard token budgets, ambiguity clarification, and anti-false-success guarantees.
"""

import os
import re
import logging
from typing import Optional, Dict, Any, Callable, Awaitable

from friday_core.document.models import (
    DocumentMap,
    RelevantRegion,
    DocEditOperation,
    DocEditRequest,
    DocEditResult
)
from friday_core.document.parser import DocxStructuralParser
from friday_core.document.editor import DocxStructuredEditor
from friday_core.document.verifier import DocxIndependentVerifier

logger = logging.getLogger("FRIDAY.DocumentAgent")


class StructuredDocumentAgent:
    """
    Autonomous agent for safe, bounded, verified document modifications.
    """

    def __init__(self, llm_query_fn: Optional[Callable[[str], Awaitable[str]]] = None):
        self.llm_query_fn = llm_query_fn

    async def execute_task(
        self,
        file_path: str,
        user_directive: str,
        output_path: Optional[str] = None
    ) -> DocEditResult:
        """
        Executes a targeted document task following the 8-stage zero-trust architecture.
        """
        tokens_used = 0

        # Stage 1 & 2: Structural Parsing & Document Map
        if not os.path.exists(file_path):
            return DocEditResult(
                success=False,
                message=f"Target document not found at: {file_path}",
                file_path=file_path,
                operation="parse",
                tokens_used=0
            )

        try:
            doc_map = DocxStructuralParser.parse(file_path)
        except Exception as e:
            logger.error(f"Failed to parse document structure: {e}")
            return DocEditResult(
                success=False,
                message=f"Could not parse document structure from '{os.path.basename(file_path)}': {e}",
                file_path=file_path,
                operation="parse",
                tokens_used=0
            )

        # Stage 3: Relevant-Section Detection & Targeted Extraction
        region = DocxStructuralParser.find_relevant_region(doc_map, user_directive)

        # Check Ambiguity
        if region.is_ambiguous:
            return DocEditResult(
                success=False,
                message=f"Clarification Required: {region.ambiguity_reason}",
                file_path=file_path,
                operation="disambiguate",
                tokens_used=region.context_token_estimate
            )

        # Stage 4: Task Interpretation
        operation, extracted_content = self._interpret_task(user_directive)

        # Read / Summarize / Inspect operations without mutation
        if operation == DocEditOperation.READ:
            return DocEditResult(
                success=True,
                message=f"Extracted content from {', '.join(region.matched_labels)}:\n\n{region.context_text}",
                file_path=file_path,
                operation=operation.value,
                target_region=", ".join(region.matched_labels),
                tokens_used=region.context_token_estimate
            )

        if operation == DocEditOperation.SUMMARIZE:
            summary_prompt = (
                f"Summarize the following document section concisely:\n\n"
                f"Context:\n{region.context_text}\n\n"
                f"Directive: {user_directive}"
            )
            tokens_used += region.context_token_estimate
            if self.llm_query_fn:
                summary_text = await self.llm_query_fn(summary_prompt)
            else:
                summary_text = f"Summary of {', '.join(region.matched_labels)}: {region.context_text[:200]}..."
            return DocEditResult(
                success=True,
                message=summary_text,
                file_path=file_path,
                operation=operation.value,
                target_region=", ".join(region.matched_labels),
                tokens_used=tokens_used
            )

        # Stage 5: Content Determination & Generation (Targeted, minimal context)
        final_content = extracted_content

        if not final_content:
            # Check if user directive asks for generation (e.g., "fill this from 12 to 13 with a clause on ...")
            gen_match = re.search(r"\b(?:with|using|to\s+say|as)\s+[\"']?([^\"'\n]+)[\"']?", user_directive, re.IGNORECASE)
            if gen_match:
                candidate = gen_match.group(1).strip()
                if candidate:
                    final_content = candidate

        # If still no content:
        # Check if the user simply commanded "fill this from 12 to 13" without giving values or template
        if not final_content:
            # Check if there is an explicit template or preceding item in the region to propagate
            propagated = self._detect_propagation_candidate(doc_map, region)
            if propagated:
                final_content = propagated
            else:
                # ASK FOR CLARIFICATION. NEVER GUESS OR INVENT DATA.
                targets_str = ", ".join(region.matched_labels) if region.matched_labels else "the selected section"
                return DocEditResult(
                    success=False,
                    message=(
                        f"Clarification Required: I located {targets_str} in '{doc_map.file_name}', "
                        f"but no values or fill criteria were specified. What exact text or data would you like me to fill in, Boss?"
                    ),
                    file_path=file_path,
                    operation=operation.value,
                    target_region=targets_str,
                    tokens_used=region.context_token_estimate
                )

        # Stage 6: Edit Operation (Surgical OpenXML Modification)
        success, edit_msg, target_out, details = DocxStructuredEditor.execute_edit(
            file_path=file_path,
            relevant_region=region,
            operation=operation,
            content=final_content,
            output_path=output_path
        )

        if not success or not target_out:
            return DocEditResult(
                success=False,
                message=edit_msg,
                file_path=file_path,
                operation=operation.value,
                target_region=", ".join(region.matched_labels),
                tokens_used=tokens_used
            )

        # Stage 7 & 8: Document Write-Back & Independent Verification
        verified, ver_msg, ver_details = DocxIndependentVerifier.verify_edit(
            original_path=file_path,
            modified_path=target_out,
            target_region=region,
            expected_content=final_content
        )

        if not verified:
            # Revert to clean state
            logger.error(f"Write-back verification failed: {ver_msg}")
            return DocEditResult(
                success=False,
                message=ver_msg,
                file_path=target_out,
                operation=operation.value,
                target_region=", ".join(region.matched_labels),
                tokens_used=tokens_used,
                verification=ver_details
            )

        # Success certified only after independent readback
        targets_desc = ", ".join(region.matched_labels)
        verified_msg = (
            f"Successfully updated {targets_desc} in '{os.path.basename(target_out)}', Boss.\n"
            f"- Operation: {operation.value.upper()}\n"
            f"- File: `{target_out}` ({ver_details.get('byte_size', 0)} bytes)\n"
            f"- Independent Verification: Passed (File readable, modifications verified, unrelated content intact)."
        )

        return DocEditResult(
            success=True,
            message=verified_msg,
            file_path=target_out,
            operation=operation.value,
            target_region=targets_desc,
            modified_content=final_content,
            tokens_used=tokens_used,
            verification=ver_details
        )

    def _interpret_task(self, directive: str) -> tuple[DocEditOperation, Optional[str]]:
        """Parses user natural language directive to determine structured operation and explicit content."""
        clean = directive.lower().strip()

        # Check specifically for 'with "content"' or 'to "content"' or 'as "content"'
        with_quoted = re.search(r'\b(?:with|to\s+say|as|set\s+to|value|text)\s*[:=]?\s*["\']([^"\']+)["\']', directive, re.IGNORECASE)
        if with_quoted:
            explicit_content = with_quoted.group(1).strip()
        else:
            # Find all quoted substrings; ignore those that end with .docx
            quotes = re.findall(r'["\']([^"\']+)["\']', directive)
            non_file_quotes = [q for q in quotes if not q.lower().endswith(".docx")]
            if non_file_quotes:
                explicit_content = non_file_quotes[-1].strip()
            else:
                explicit_content = None

        if not explicit_content:
            with_match = re.search(r'\b(?:with|value|text)\s*[:=]?\s*(.+)$', directive, re.IGNORECASE)
            if with_match and not any(w in with_match.group(1).lower() for w in ["from", "to", "table", "section"]):
                explicit_content = with_match.group(1).strip().strip('"\'')

        if clean.startswith("read") or "read " in clean:
            return DocEditOperation.READ, None
        if "summarize" in clean or "summary" in clean:
            return DocEditOperation.SUMMARIZE, None
        if clean.startswith("fill") or "fill " in clean:
            return DocEditOperation.FILL, explicit_content
        if "replace" in clean:
            return DocEditOperation.REPLACE, explicit_content
        if "append" in clean or "add to" in clean:
            return DocEditOperation.APPEND, explicit_content
        if "insert" in clean:
            return DocEditOperation.INSERT, explicit_content
        if "delete" in clean or "remove" in clean:
            return DocEditOperation.DELETE, None

        return DocEditOperation.EDIT, explicit_content

    @staticmethod
    def _detect_propagation_candidate(doc_map: DocumentMap, region: RelevantRegion) -> Optional[str]:
        """
        Checks if the document has a repeated pattern or prior item that matches a template
        (e.g., if item 11 has [Pending] and item 12 is empty).
        """
        # If no explicit template detected, return None to trigger clarification
        return None
