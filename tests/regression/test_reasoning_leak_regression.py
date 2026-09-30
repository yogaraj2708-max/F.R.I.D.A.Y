"""
Regression Test Suite: Critical Reasoning-Leak Isolation
Tests all 10 mandatory safety scenarios:
1. reasoning before final answer
2. reasoning + final answer in same stream
3. reasoning split across chunks
4. reasoning around native tool calls
5. tool result followed by reasoning then final answer
6. no reasoning at all
7. malformed/incomplete reasoning markers
8. cancellation during reasoning
9. TTS receives final content only
10. UI receives final content only
"""

import sys
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for UI tests
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from friday_core.models.stream_parser import (
    ReasoningStreamParser,
    AssistantStreamState,
)
from friday_ui.widgets.chat_bubble import ChatBubble
from friday_ui.views.chat_view import ChatView
from friday_core.voice.tts import TextToSpeechOrchestrator
from friday_ui.core.engine import FridayBrain


class TestReasoningLeakRegression(unittest.TestCase):

    def setUp(self):
        self.parser = ReasoningStreamParser()

    # -------------------------------------------------------------------------
    # Scenario 1: reasoning before final answer
    # -------------------------------------------------------------------------
    def test_01_reasoning_before_final_answer(self):
        # Structured thinking chunk followed by content chunk
        t_chunk = "Understanding the directive involves dissecting its core tasks..."
        c_chunk = "62"

        out1 = self.parser.process_chunk("", thinking_chunk=t_chunk)
        self.assertEqual(out1, "")
        self.assertEqual(self.parser.internal_reasoning, t_chunk)

        out2 = self.parser.process_chunk(c_chunk)
        self.assertEqual(out2, "62")

        flush_out = self.parser.flush()
        final_answer = ReasoningStreamParser.clean_final_content(out2 + flush_out)

        self.assertEqual(final_answer, "62")
        self.assertNotIn("Understanding the directive", final_answer)
        self.assertIn("Understanding the directive", self.parser.internal_reasoning)

    # -------------------------------------------------------------------------
    # Scenario 2: reasoning + final answer in same stream
    # -------------------------------------------------------------------------
    def test_02_reasoning_and_final_answer_in_same_stream(self):
        # Multiple inline thinking blocks mixed with final content
        chunks = [
            "<think>Calculating first component: 25</think>",
            "25 + ",
            "<think>Calculating second component: 37</think>",
            "37 = 62",
        ]
        emitted = []
        for c in chunks:
            token = self.parser.process_chunk(c)
            if token:
                emitted.append(token)
        emitted.append(self.parser.flush())

        final_content = ReasoningStreamParser.clean_final_content("".join(emitted))
        self.assertEqual(final_content, "25 + 37 = 62")
        self.assertNotIn("Calculating", final_content)
        self.assertIn("Calculating first component: 25", self.parser.internal_reasoning)
        self.assertIn("Calculating second component: 37", self.parser.internal_reasoning)

    # -------------------------------------------------------------------------
    # Scenario 3: reasoning split across chunks
    # -------------------------------------------------------------------------
    def test_03_reasoning_split_across_chunks(self):
        # Tags split across token boundaries: <th | ink> and </th | ink>
        chunks = [
            "Directive recognized. <th",
            "ink>Analyzing operational ",
            "parameters in deep memory...</th",
            "ink> All systems nominal.",
        ]
        emitted = []
        for c in chunks:
            token = self.parser.process_chunk(c)
            if token:
                emitted.append(token)
        emitted.append(self.parser.flush())

        final_content = ReasoningStreamParser.clean_final_content("".join(emitted))
        self.assertEqual(final_content, "Directive recognized.  All systems nominal.")
        self.assertNotIn("<think>", final_content)
        self.assertNotIn("operational parameters", final_content)
        self.assertIn("Analyzing operational parameters in deep memory...", self.parser.internal_reasoning)

    # -------------------------------------------------------------------------
    # Scenario 4: reasoning around native tool calls
    # -------------------------------------------------------------------------
    def test_04_reasoning_around_native_tool_calls(self):
        # Mock step response containing tool call and structured thinking
        mock_step_resp = MagicMock()
        mock_msg = MagicMock()
        mock_msg.thinking = "Thinking: User asked to launch notepad. Checking launch_app schema."
        mock_msg.content = ""
        mock_msg.tool_calls = [{"function": {"name": "launch_app", "arguments": {"app_name": "notepad"}}}]
        mock_step_resp.message = mock_msg

        loop = asyncio.new_event_loop()
        try:
            msg, t_calls, clean_content = loop.run_until_complete(
                FridayBrain._normalize_chat_message(mock_step_resp)
            )
        finally:
            loop.close()

        # Tool calls preserved
        self.assertEqual(len(t_calls), 1)
        self.assertEqual(t_calls[0]["function"]["name"], "launch_app")
        # Content MUST be clean / empty, NOT containing reasoning
        self.assertEqual(clean_content, "")
        # Reasoning captured internally
        self.assertIn("launch_app schema", getattr(msg, "internal_reasoning", ""))

    # -------------------------------------------------------------------------
    # Scenario 5: tool result followed by reasoning then final answer
    # -------------------------------------------------------------------------
    def test_05_tool_result_followed_by_reasoning_then_final_answer(self):
        # Assistant Turn 2 after tool execution: contains inline reasoning and final answer
        mock_step_resp = {
            "message": {
                "thinking": "Process notepad.exe confirmed with PID 4321.",
                "content": "<think>Tool succeeded, formatting response for user.</think>Notepad has been successfully opened, Boss.",
                "tool_calls": None
            }
        }
        loop = asyncio.new_event_loop()
        try:
            msg, t_calls, clean_content = loop.run_until_complete(
                FridayBrain._normalize_chat_message(mock_step_resp)
            )
        finally:
            loop.close()

        self.assertIsNone(t_calls)
        self.assertEqual(clean_content, "Notepad has been successfully opened, Boss.")
        self.assertNotIn("confirmed with PID", clean_content)
        self.assertNotIn("<think>", clean_content)
        self.assertNotIn("Tool succeeded", clean_content)
        self.assertIn("Process notepad.exe confirmed", msg["internal_reasoning"])
        self.assertIn("Tool succeeded", msg["internal_reasoning"])

    # -------------------------------------------------------------------------
    # Scenario 6: no reasoning at all
    # -------------------------------------------------------------------------
    def test_06_no_reasoning_at_all(self):
        chunks = ["Greetings, ", "Boss. ", "How may I assist?"]
        emitted = []
        for c in chunks:
            token = self.parser.process_chunk(c)
            if token:
                emitted.append(token)
        emitted.append(self.parser.flush())

        final_content = ReasoningStreamParser.clean_final_content("".join(emitted))
        self.assertEqual(final_content, "Greetings, Boss. How may I assist?")
        self.assertEqual(self.parser.internal_reasoning, "")

    # -------------------------------------------------------------------------
    # Scenario 7: malformed/incomplete reasoning markers
    # -------------------------------------------------------------------------
    def test_07_malformed_incomplete_reasoning_markers(self):
        # Case A: Unclosed <think> tag cut off at end of stream
        parser_a = ReasoningStreamParser()
        parser_a.process_chunk("Hello! <think>Neverending internal thoughts...")
        flush_a = parser_a.flush()
        self.assertEqual(flush_a, "")
        self.assertIn("Neverending internal thoughts...", parser_a.internal_reasoning)

        # Case B: Stray closing tag with no opening tag
        parser_b = ReasoningStreamParser()
        out_b = parser_b.process_chunk("Some answer text</think> continues here.")
        flush_b = parser_b.flush()
        clean_b = ReasoningStreamParser.clean_final_content(out_b + flush_b)
        self.assertEqual(clean_b, "Some answer text continues here.")
        self.assertNotIn("</think>", clean_b)

        # Case C: Thought process plain-text prefix
        raw_msg = "Thinking Process:\n1. Analyze query\n2. Solve\n\nThe sum is 42."
        clean_c = ReasoningStreamParser.clean_final_content(raw_msg)
        self.assertEqual(clean_c, "The sum is 42.")

    # -------------------------------------------------------------------------
    # Scenario 8: cancellation during reasoning
    # -------------------------------------------------------------------------
    def test_08_cancellation_during_reasoning(self):
        # Stream aborted while emitting thinking
        collected = []
        is_cancelled = False

        stream_chunks = [
            {"thinking": "Initial thought chunk 1", "content": ""},
            {"thinking": "Initial thought chunk 2", "content": ""},
            # User presses stop
        ]

        parser = ReasoningStreamParser()
        for c in stream_chunks:
            token = parser.process_chunk(c["content"], c["thinking"])
            if token:
                collected.append(token)
            # Simulate cancellation trigger
            is_cancelled = True
            break

        # Flush should NOT be called on cancellation, or if called, unclosed reasoning remains internal
        reply = ReasoningStreamParser.clean_final_content("".join(collected).strip())
        self.assertEqual(reply, "")
        self.assertIn("Initial thought chunk 1", parser.internal_reasoning)

    # -------------------------------------------------------------------------
    # Scenario 9: TTS receives final content only
    # -------------------------------------------------------------------------
    def test_09_tts_receives_final_content_only(self):
        tts = TextToSpeechOrchestrator()

        # Poisoned input containing reasoning, tags, tool JSON, and system markdown
        dirty_input = (
            "<think>Understanding the directive involves dissecting its core tasks...</think>\n"
            "[TOOL: calculate_math]\n"
            '{"name": "calculate_math", "arguments": {"expression": "25 + 37"}}\n'
            "Thinking Process:\n"
            "1. Compute 25 + 37 = 62\n\n"
            "The calculation result is 62, Boss."
        )

        spoken_clean = tts.clean_text_for_speech(dirty_input)

        self.assertNotIn("Understanding the directive", spoken_clean)
        self.assertNotIn("core tasks", spoken_clean)
        self.assertNotIn("<think>", spoken_clean)
        self.assertNotIn("calculate_math", spoken_clean)
        self.assertNotIn("Thinking Process", spoken_clean)
        self.assertNotIn("expression", spoken_clean)
        self.assertIn("The calculation result is 62, Boss.", spoken_clean)

    # -------------------------------------------------------------------------
    # Scenario 10: UI receives final content only
    # -------------------------------------------------------------------------
    def test_10_ui_receives_final_content_only(self):
        # 1. ChatBubble streaming lifecycle
        bubble = ChatBubble("friday", "", is_streaming=True)
        self.assertTrue(bubble.thinking_container.isHidden())

        # Stream thinking chunks
        bubble.append_thinking("Understanding the directive involves dissecting its core tasks...")
        self.assertTrue(bubble.thinking_container.isHidden())
        self.assertNotIn("Understanding the directive", bubble.raw_text)

        # Stream final content
        bubble.append_token("62")
        bubble.finish_stream()

        # Check visible bubble UI
        self.assertTrue(bubble.thinking_container.isHidden())
        self.assertEqual(bubble.raw_text, "62")
        self.assertIn("62", bubble.text_browser.toPlainText())
        self.assertNotIn("Understanding the directive", bubble.text_browser.toPlainText())

        # Check clipboard safety
        bubble._copy_content()
        clip_text = QApplication.clipboard().text()
        self.assertEqual(clip_text, "62")
        self.assertNotIn("Understanding the directive", clip_text)

        # 2. ChatView session persistence
        mock_store = MagicMock()
        chat_view = ChatView(session_store=mock_store)
        chat_view._current_streaming_bubble = bubble
        chat_view.current_session_id = "test-session-123"
        chat_view._streaming_session_id = "test-session-123"

        chat_view.finish_stream("62")

        # Verify persisted text to database contains ZERO reasoning
        mock_store.add_message.assert_called_with("test-session-123", "friday", "62")
        calls = mock_store.add_message.call_args_list
        for c in calls:
            persisted_text = c[0][2]
            self.assertNotIn("<think>", persisted_text)
            self.assertNotIn("Understanding the directive", persisted_text)


if __name__ == "__main__":
    unittest.main()
