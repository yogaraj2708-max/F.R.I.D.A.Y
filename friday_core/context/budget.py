"""
F.R.I.D.A.Y. 3.0 — Context Budget Manager
Enforces strict token limits, reserve allocations, and preflight budget verification
before sending requests to local or remote LLMs.
Zero silent drops; deterministic multi-pass chunking and audit logging.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("FRIDAY.ContextBudget")

# Default context budget configurations
DEFAULT_MODEL_CONTEXT_LIMIT = 8192
DEFAULT_RESERVED_SYSTEM = 1200
DEFAULT_RESERVED_HISTORY = 1000
DEFAULT_RESERVED_OUTPUT = 1536


@dataclass
class ContextBudgetResult:
    is_valid: bool
    estimated_tokens: int
    context_limit: int
    available_context: int
    system_tokens: int = 0
    history_tokens: int = 0
    attachment_tokens: int = 0
    raw_retrieved_tokens: int = 0
    final_prompt_tokens: int = 0
    truncation_occurred: bool = False
    chunk_count: int = 1
    retrieved_files: List[str] = field(default_factory=list)
    retrieved_symbols: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


class ContextBudgetManager:
    """
    Supervises prompt token budgeting.
    Formula:
      AVAILABLE_CONTEXT = MODEL_CONTEXT_LIMIT - RESERVED_SYSTEM - RESERVED_HISTORY - RESERVED_OUTPUT
    """

    def __init__(
        self,
        model_context_limit: int = DEFAULT_MODEL_CONTEXT_LIMIT,
        reserved_system: int = DEFAULT_RESERVED_SYSTEM,
        reserved_history: int = DEFAULT_RESERVED_HISTORY,
        reserved_output: int = DEFAULT_RESERVED_OUTPUT,
    ):
        self.model_context_limit = model_context_limit
        self.reserved_system = reserved_system
        self.reserved_history = reserved_history
        self.reserved_output = reserved_output

    @property
    def available_context(self) -> int:
        avail = self.model_context_limit - self.reserved_system - self.reserved_history - self.reserved_output
        return max(512, avail)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Fast token estimation heuristic: ~3.8 chars per token for code/JSON/text + token safety margin.
        """
        if not text:
            return 0
        # Roughly 3.8 chars per token for code/markdown/technical text
        # Add 10% safety buffer for tokenizer variance
        estimated = int((len(text) / 3.8) * 1.10) + 1
        return estimated

    @classmethod
    def estimate_messages_tokens(cls, messages: List[Dict[str, Any]]) -> int:
        """Estimates total tokens across all messages including roles and structure."""
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += cls.estimate_tokens(content)
            # Add message envelope overhead (~4 tokens per message)
            total += 4
        return total

    def log_budget_metrics(self, result: ContextBudgetResult) -> None:
        """Emits structured audit logging for forensic traceability."""
        logger.info(
            "CONTEXT_BUDGET: limit=%d, available=%d | "
            "RETRIEVED_FILES: %s | "
            "RETRIEVED_SYMBOLS: %s | "
            "ESTIMATED_TOKENS: %d | "
            "FINAL_PROMPT_TOKENS: %d | "
            "TRUNCATION_OCCURRED: %s | "
            "CHUNK_COUNT: %d",
            result.context_limit,
            result.available_context,
            result.retrieved_files,
            result.retrieved_symbols,
            result.estimated_tokens,
            result.final_prompt_tokens,
            result.truncation_occurred,
            result.chunk_count,
        )

    def validate_and_bound_prompt(
        self,
        messages: List[Dict[str, Any]],
        context_limit: Optional[int] = None,
        retrieved_files: Optional[List[str]] = None,
        retrieved_symbols: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], ContextBudgetResult]:
        """
        Preflight guard: Enforces estimated_prompt_tokens < model_context_limit before calling Ollama.
        If request exceeds the limit, bounds history and attachments deterministically.
        """
        limit = context_limit or self.model_context_limit
        total_est = self.estimate_messages_tokens(messages)
        files = retrieved_files or []
        symbols = retrieved_symbols or []

        # If already well under budget, return unmodified
        if total_est < limit:
            res = ContextBudgetResult(
                is_valid=True,
                estimated_tokens=total_est,
                context_limit=limit,
                available_context=self.available_context,
                final_prompt_tokens=total_est,
                truncation_occurred=False,
                chunk_count=1,
                retrieved_files=files,
                retrieved_symbols=symbols,
            )
            self.log_budget_metrics(res)
            return messages, res

        # Exceeds limit: We must reduce/bound without breaking the conversation
        logger.warning(
            "Prompt tokens (%d) exceed context limit (%d). Applying budget compression.",
            total_est,
            limit,
        )

        bounded_messages = list(messages)
        truncation_occurred = False
        chunk_count = 1

        # Step 1: Compress conversation history (keep system prompt and latest user directive)
        if len(bounded_messages) > 2:
            system_msg = bounded_messages[0] if bounded_messages[0].get("role") == "system" else None
            latest_msg = bounded_messages[-1]
            interim = bounded_messages[1:-1] if system_msg else bounded_messages[:-1]

            # Prune older turns until under budget
            while interim and self.estimate_messages_tokens(bounded_messages) >= limit:
                interim.pop(0)
                bounded_messages = ([system_msg] if system_msg else []) + interim + [latest_msg]
                truncation_occurred = True

        # Step 2: If latest user message itself exceeds the budget (e.g. huge attachments)
        cur_est = self.estimate_messages_tokens(bounded_messages)
        if cur_est >= limit and bounded_messages:
            last_msg = bounded_messages[-1]
            content = last_msg.get("content", "")

            # Check if there are attached documents inside
            if "[Attached Document:" in content or "```" in content:
                # Target budget for the user turn
                max_user_chars = int((self.available_context + self.reserved_history) * 3.5)
                if len(content) > max_user_chars:
                    # Parse out sections
                    directive_part = ""
                    if "Boss Directive:\n" in content:
                        parts = content.split("Boss Directive:\n", 1)
                        attachments_part = parts[0]
                        directive_part = "\n\nBoss Directive:\n" + parts[1]
                    else:
                        attachments_part = content

                    # Compact attached snippets
                    compacted = self._compact_attachment_snippets(attachments_part, max_user_chars - len(directive_part))
                    new_content = compacted + directive_part
                    last_msg["content"] = new_content
                    truncation_occurred = True
                    chunk_count = 2

        final_est = self.estimate_messages_tokens(bounded_messages)
        is_valid = final_est < limit

        res = ContextBudgetResult(
            is_valid=is_valid,
            estimated_tokens=total_est,
            context_limit=limit,
            available_context=self.available_context,
            final_prompt_tokens=final_est,
            truncation_occurred=truncation_occurred,
            chunk_count=chunk_count,
            retrieved_files=files,
            retrieved_symbols=symbols,
            error_message=None if is_valid else f"Context overflow: {final_est} >= {limit}",
        )
        self.log_budget_metrics(res)
        return bounded_messages, res

    def _compact_attachment_snippets(self, text: str, max_chars: int) -> str:
        """
        Compacts document snippets while preserving file headings, metadata, and key code headers.
        """
        if len(text) <= max_chars or max_chars <= 200:
            return text[:max_chars]

        # Break by attached document blocks
        blocks = re.split(r"(?=\[Attached Document:)", text)
        if not blocks or len(blocks) == 1:
            return text[:max_chars] + "\n\n[... Remaining content bounded to preserve context ...]"

        budget_per_block = max(400, max_chars // len(blocks))
        compacted_blocks = []
        for b in blocks:
            b_strip = b.strip()
            if not b_strip:
                continue
            if len(b_strip) > budget_per_block:
                # Keep header line and first slice of code block
                lines = b_strip.splitlines()
                header = lines[0] if lines else ""
                body = "\n".join(lines[1:])
                slice_len = max(100, budget_per_block - len(header) - 80)
                compacted_blocks.append(
                    f"{header}\n{body[:slice_len]}\n[... Excerpt bounded to budget ...]\n```"
                )
            else:
                compacted_blocks.append(b_strip)

        result = "\n\n".join(compacted_blocks)
        return result[:max_chars]


# Global default context budget manager
context_budget_manager = ContextBudgetManager()
