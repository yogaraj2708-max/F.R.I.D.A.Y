"""
Tests ensuring NO Python Keyword or Intent-Based Tool Selection (Section 13, 14, 39).
Verifies:
1. Python never inspects user text to independently select tools based on keywords:
   - 'search' in message
   - 'latest' in message
   - 'pdf' in message
   - 'image' in message
   - 'open' in message
   - 'type' in message
2. If the model produces content without native tool calls, NO tool is executed.
3. No hidden 1B preflight model overrides tool selection.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestNoPythonToolSelection(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.cancel_event = MagicMock()
        self.tts.cancel_event.is_set.return_value = False
        self.brain = FridayBrain(self.signals, self.tts)
        self.brain._tool_capability_cache[self.brain.model] = "VERIFIED"

    def test_keywords_do_not_trigger_python_tool_selection(self):
        async def _test():
            keyword_prompts = [
                "search for the meaning of life",
                "what is the latest news in science",
                "tell me about how pdf files work internally",
                "what is the history of the word image",
                "open a conversation about philosophy",
                "what type of computer do you like"
            ]

            mock_client = AsyncMock()
            self.brain.client = mock_client

            # For each prompt, the model responds purely with text (zero tool calls)
            for prompt in keyword_prompts:
                mock_resp = MagicMock()
                mock_resp.message = MagicMock()
                mock_resp.message.content = f"Conversational reflection on: {prompt}"
                mock_resp.message.tool_calls = None
                mock_client.chat.return_value = mock_resp

                with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                    res = await self.brain.query_llm(prompt, stream_to_ui=False, stream_to_speech=False, save_history=False)
                    self.assertIn("Conversational reflection", res)
                    # Dispatcher MUST NEVER be invoked because model did not emit tool_calls
                    mock_dispatch.assert_not_called()
                    trace = self.brain.last_agent_trace
                    self.assertFalse(trace["native_tool_call_detected"])
                    self.assertEqual(len(trace.get("tool_calls", [])), 0)

        asyncio.run(_test())

    def test_no_preflight_1b_router_interception(self):
        """Verifies that no hidden 1B model selects tools before the main agent model."""
        self.assertFalse(hasattr(self.brain, "tool_model"))
        self.assertFalse(hasattr(self.brain, "_detect_tool_model"))


if __name__ == "__main__":
    unittest.main()
