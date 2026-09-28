"""
Tests for Model Switching at Runtime (Section 4, 30, TEST 11, TEST 12).
Verifies:
1. When user switches MAIN AGENT MODEL from Model A to Model B, next turn uses Model B.
2. No restart required; cache is invalidated.
3. If Model B lacks native tool capability, report UNSUPPORTED honestly without silent fallback to Model A.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_core.settings import settings
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestModelSwitching(unittest.TestCase):
    def setUp(self):
        self.original_model = settings.get("model")
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.cancel_event = MagicMock()
        self.tts.cancel_event.is_set.return_value = False

    def tearDown(self):
        if self.original_model:
            settings.set("model", self.original_model)

    def test_model_switching_between_turns(self):
        async def _test():
            settings.set("model", "model-a:latest")
            brain = FridayBrain(self.signals, self.tts)
            self.assertEqual(brain.model, "model-a:latest")

            # Mock client.chat to capture model passed in
            mock_client = AsyncMock()
            brain.client = mock_client

            # Probe mock returns VERIFIED for model-a
            brain._tool_capability_cache["model-a:latest"] = "VERIFIED"
            brain._tool_capability_cache["model-b:latest"] = "VERIFIED"

            # Mock model-a response: zero tools, final answer
            mock_resp_a = MagicMock()
            mock_resp_a.message = MagicMock()
            mock_resp_a.message.content = "Response from Model A"
            mock_resp_a.message.tool_calls = None
            mock_client.chat.return_value = mock_resp_a

            res_a = await brain.query_llm("Hi", stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertEqual(res_a, "Response from Model A")
            self.assertEqual(mock_client.chat.call_args.kwargs["model"], "model-a:latest")
            self.assertEqual(brain.last_agent_trace["main_model"], "model-a:latest")

            # Switch model setting to Model B
            settings.set("model", "model-b:latest")
            self.assertEqual(brain.model, "model-b:latest")
            brain._tool_capability_cache["model-b:latest"] = "VERIFIED"

            # Mock model-b response
            mock_resp_b = MagicMock()
            mock_resp_b.message = MagicMock()
            mock_resp_b.message.content = "Response from Model B"
            mock_resp_b.message.tool_calls = None
            mock_client.chat.return_value = mock_resp_b

            res_b = await brain.query_llm("Hi", stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertEqual(res_b, "Response from Model B")
            self.assertEqual(mock_client.chat.call_args.kwargs["model"], "model-b:latest")
            self.assertEqual(brain.last_agent_trace["main_model"], "model-b:latest")

        asyncio.run(_test())

    def test_switching_to_unsupported_model_reports_honestly(self):
        async def _test():
            settings.set("model", "capable-model:latest")
            brain = FridayBrain(self.signals, self.tts)
            brain._tool_capability_cache["capable-model:latest"] = "VERIFIED"
            brain._tool_capability_cache["unsupported-model:latest"] = "UNAVAILABLE"

            # Switch to unsupported model
            settings.set("model", "unsupported-model:latest")
            self.assertEqual(brain.model, "unsupported-model:latest")

            mock_client = AsyncMock()
            brain.client = mock_client

            # Mock capability probe response (no tool calls returned -> UNAVAILABLE)
            mock_probe_resp = MagicMock()
            mock_probe_resp.message = MagicMock()
            mock_probe_resp.message.tool_calls = None
            mock_probe_resp.message.content = "No tools available."

            # Normal stream mock for chat
            mock_stream = AsyncMock()
            mock_chunk = MagicMock()
            mock_chunk.message = MagicMock()
            mock_chunk.message.content = "Standard chat answer without tools"
            mock_chunk.message.thinking = ""
            mock_stream.__aiter__.return_value = [mock_chunk]

            mock_client.chat.side_effect = [mock_probe_resp, mock_stream]

            status = await brain.get_model_tool_capability_status("unsupported-model:latest")
            self.assertEqual(status, "UNAVAILABLE")
            self.assertFalse(await brain.is_model_tool_capable("unsupported-model:latest"))

            res = await brain.query_llm("What is happening with tech?", stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertIn("Standard chat answer", res)
            self.assertEqual(brain.last_agent_trace["main_model"], "unsupported-model:latest")
            self.assertEqual(brain.last_agent_trace["native_tool_calling"], "UNSUPPORTED_FOR_SELECTED_MODEL")
            self.assertEqual(brain.last_agent_trace["capability_status"], "UNAVAILABLE")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
