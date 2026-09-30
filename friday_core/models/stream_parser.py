"""
F.R.I.D.A.Y. 3.0 — Robust Reasoning & Streaming Response Parser
Strict Output-Isolation Architecture: Separates internal reasoning, tool calls, and final content.

Hard Safety Invariant:
Internal reasoning, chain-of-thought, and provider thinking payloads MUST NEVER enter:
- visible chat bubbles
- TTS speech synthesis
- clipboard copies
- user notifications
- user-facing logs
- saved assistant final-answer storage
"""

import re
from enum import Enum
from typing import Tuple, List, Optional, Any


class AssistantStreamState(str, Enum):
    """Internal assistant state representation."""
    REASONING = "REASONING"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    FINAL_CONTENT = "FINAL_CONTENT"


class ReasoningStreamParser:
    """
    Streaming token and chunk processor that strictly isolates internal reasoning from final user-facing content.

    Guarantees:
    - Zero reasoning tokens enter FINAL_CONTENT.
    - Robust detection across streamed chunk boundaries for opening and closing tags.
    - Safe buffering: partial tag prefixes are held until confirmed or refuted.
    - Malformed or unclosed reasoning blocks are never leaked to user output.
    - Structured provider reasoning (e.g. msg.thinking / reasoning_content) is captured internally.
    """

    OPENING_TAGS = ("<think>", "<thought>", "<reasoning>", "[THOUGHT]")
    CLOSING_TAGS = ("</think>", "</thought>", "</reasoning>", "[/THOUGHT]")

    def __init__(self):
        self.state = AssistantStreamState.FINAL_CONTENT
        self.internal_reasoning = ""
        self._pending_buffer = ""
        self.tool_calls: List[Any] = []

    def reset(self):
        """Resets the parser state for a fresh stream."""
        self.state = AssistantStreamState.FINAL_CONTENT
        self.internal_reasoning = ""
        self._pending_buffer = ""
        self.tool_calls.clear()

    def process_chunk(self, content_chunk: str, thinking_chunk: str = "") -> str:
        """
        Processes a streaming token chunk.
        - thinking_chunk: Structured thinking from provider (e.g. chunk.message.thinking)
        - content_chunk: Content string from provider (e.g. chunk.message.content)

        Returns:
        - clean content token string to be emitted to user/TTS (empty string if chunk is internal reasoning)
        """
        # 1. Capture structured provider thinking
        if thinking_chunk:
            self.internal_reasoning += thinking_chunk

        if not content_chunk:
            return ""

        text = self._pending_buffer + content_chunk
        self._pending_buffer = ""
        user_visible_out = []

        i = 0
        n = len(text)
        while i < n:
            if self.state == AssistantStreamState.REASONING:
                # Check for closing tags
                matched_close = None
                for ctag in self.CLOSING_TAGS:
                    if text.startswith(ctag, i):
                        matched_close = ctag
                        break

                if matched_close:
                    i += len(matched_close)
                    self.state = AssistantStreamState.FINAL_CONTENT
                    continue

                # Check if remainder could be prefix of a closing tag
                is_prefix = False
                for ctag in self.CLOSING_TAGS:
                    if ctag.startswith(text[i:]):
                        is_prefix = True
                        break

                if is_prefix:
                    self._pending_buffer = text[i:]
                    break
                else:
                    self.internal_reasoning += text[i]
                    i += 1

            else:  # FINAL_CONTENT
                # Check for opening tags
                matched_open = None
                for otag in self.OPENING_TAGS:
                    if text.startswith(otag, i):
                        matched_open = otag
                        break

                if matched_open:
                    i += len(matched_open)
                    self.state = AssistantStreamState.REASONING
                    continue

                # Check if remainder could be prefix of an opening tag
                is_prefix = False
                for otag in self.OPENING_TAGS:
                    if otag.startswith(text[i:]):
                        is_prefix = True
                        break

                if is_prefix:
                    self._pending_buffer = text[i:]
                    break
                else:
                    user_visible_out.append(text[i])
                    i += 1

        return "".join(user_visible_out)

    def flush(self) -> str:
        """Flushes remaining pending buffer at end of stream."""
        out = ""
        if self._pending_buffer:
            if self.state == AssistantStreamState.FINAL_CONTENT:
                # Pending buffer was not a tag, emit as final content
                out = self._pending_buffer
            else:
                # Unclosed reasoning tag at stream end: keep in internal reasoning
                self.internal_reasoning += self._pending_buffer
            self._pending_buffer = ""
        return out

    @classmethod
    def clean_final_content(cls, text: str) -> str:
        """
        Deep sanitization function to guarantee zero reasoning, tags, or planning text remain in final content.
        Can be used anywhere final user-facing text is produced.
        """
        if not text:
            return ""

        cleaned = text

        # 1. Strip complete reasoning tag blocks
        cleaned = re.sub(r"<(?:think|thought|reasoning)>[\s\S]*?</(?:think|thought|reasoning)>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[THOUGHT\][\s\S]*?\[/THOUGHT\]", "", cleaned, flags=re.IGNORECASE)

        # 2. Strip unclosed reasoning tags that may have terminated at EOF
        cleaned = re.sub(r"<(?:think|thought|reasoning)>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[THOUGHT\][\s\S]*$", "", cleaned, flags=re.IGNORECASE)

        # 3. Strip any stray closing tags
        cleaned = re.sub(r"</(?:think|thought|reasoning)>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[/THOUGHT\]", "", cleaned, flags=re.IGNORECASE)

        # 4. Strip plaintext thinking process headers anywhere in content
        cleaned = re.sub(r"(?:^|\n)(?:Thinking|Thought)\s+Process:[\s\S]*?(?:\n\s*\n|$)", "\n", cleaned, flags=re.IGNORECASE)

        # 5. Strip tool traces & system provenance markers
        cleaned = re.sub(r"\[(?:TOOL|TRACE|ACTION|RESULT)[\s\S]*?\]", "", cleaned, flags=re.IGNORECASE)

        # 6. Strip nested tool JSON payloads
        for _ in range(5):
            new_cleaned = re.sub(r"\{[^{}]*?(?:name|arguments|tool_calls|expression|query)[^{}]*?\}", "", cleaned, flags=re.IGNORECASE)
            if new_cleaned == cleaned:
                break
            cleaned = new_cleaned
        cleaned = re.sub(r"\{\s*\}", "", cleaned)

        # 7. Clean excess empty lines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @classmethod
    def extract_reasoning_and_content(cls, raw_content: str, raw_thinking: str = "") -> Tuple[str, str]:
        """
        Stateless extraction for complete/non-streaming turns.
        Returns: (clean_final_content, internal_reasoning)
        """
        parser = cls()
        final_tokens = []
        if raw_thinking:
            parser.process_chunk("", thinking_chunk=raw_thinking)
        if raw_content:
            final_tokens.append(parser.process_chunk(raw_content))
        final_tokens.append(parser.flush())

        candidate_content = "".join(final_tokens)
        clean_content = cls.clean_final_content(candidate_content)

        return clean_content, parser.internal_reasoning.strip()
