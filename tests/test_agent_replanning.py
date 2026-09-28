"""
Tests for Agent Replanning and Multi-Step Sequences (Section 17, 24, 27, TEST 04, TEST 08).
Verifies:
1. TEST 04: Desktop agent multi-step sequence generated autonomously by model:
   launch_app -> tool result -> type_text -> tool result -> final answer.
2. TEST 08: Tool failure returned to same model, which replans or reports failure honestly without fabricating success.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestAgentReplanning(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.cancel_event = MagicMock()
        self.tts.cancel_event.is_set.return_value = False
        self.brain = FridayBrain(self.signals, self.tts)
        self.brain._tool_capability_cache[self.brain.model] = "VERIFIED"

    def test_test04_desktop_agent_autonomous_multistep_sequence(self):
        """TEST 04: 'Open Notepad and type hello.' -> Model generates multi-step sequence."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client
            active_model = self.brain.model

            # Turn 1: Model calls launch_app(app_name="notepad")
            tc_launch = MagicMock()
            tc_launch.id = "tc_launch_1"
            tc_launch.function = MagicMock()
            tc_launch.function.name = "launch_app"
            tc_launch.function.arguments = {"app_name": "notepad"}

            resp_1 = MagicMock()
            resp_1.message = MagicMock()
            resp_1.message.content = ""
            resp_1.message.tool_calls = [tc_launch]

            # Turn 2: Same model receives launch success, then decides to call type_text
            tc_type = MagicMock()
            tc_type.id = "tc_type_2"
            tc_type.function = MagicMock()
            tc_type.function.name = "type_text"
            tc_type.function.arguments = {"app_name": "notepad", "text": "hello"}

            resp_2 = MagicMock()
            resp_2.message = MagicMock()
            resp_2.message.content = ""
            resp_2.message.tool_calls = [tc_type]

            # Turn 3: Same model receives type success, produces final completion answer
            resp_3 = MagicMock()
            resp_3.message = MagicMock()
            resp_3.message.content = "Notepad has been opened and 'hello' was typed into the window."
            resp_3.message.tool_calls = None

            mock_client.chat.side_effect = [resp_1, resp_2, resp_3]

            with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                mock_dispatch.side_effect = [
                    "Launched notepad successfully (PID 4080).",
                    "Typed 'hello' into notepad and verified content."
                ]

                res = await self.brain.query_llm("Open Notepad and type hello.", stream_to_ui=False, stream_to_speech=False, save_history=False)
                self.assertIn("Notepad has been opened", res)
                self.assertEqual(mock_dispatch.call_count, 2)
                mock_dispatch.assert_any_call("launch_app", {"app_name": "notepad"})
                mock_dispatch.assert_any_call("type_text", {"app_name": "notepad", "text": "hello"})

                # Verify all calls went to the same main model
                self.assertEqual(mock_client.chat.call_count, 3)
                for call in mock_client.chat.call_args_list:
                    self.assertEqual(call.kwargs["model"], active_model)

                trace = self.brain.last_agent_trace
                self.assertEqual(len(trace["tool_calls"]), 2)
                self.assertEqual(trace["tool_calls"][0]["tool_name"], "launch_app")
                self.assertEqual(trace["tool_calls"][1]["tool_name"], "type_text")

        asyncio.run(_test())

    def test_test08_tool_failure_returned_to_same_model_for_replanning(self):
        """TEST 08: Tool failure returns to same model, which handles it without fabricating success."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client
            active_model = self.brain.model

            # Turn 1: Model calls web_search
            tc_search = MagicMock()
            tc_search.id = "tc_search_err"
            tc_search.function = MagicMock()
            tc_search.function.name = "web_search"
            tc_search.function.arguments = {"query": "weather forecast Tokyo"}

            resp_1 = MagicMock()
            resp_1.message = MagicMock()
            resp_1.message.content = ""
            resp_1.message.tool_calls = [tc_search]

            # Turn 2: Same model receives failure, decides to inform user honestly
            resp_2 = MagicMock()
            resp_2.message = MagicMock()
            resp_2.message.content = "I attempted to search for the Tokyo weather, but the network request failed. Please check your internet connection."
            resp_2.message.tool_calls = None

            mock_client.chat.side_effect = [resp_1, resp_2]

            with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                mock_dispatch.return_value = "Error: Web search failed (HTTP 503 Service Unavailable)."

                res = await self.brain.query_llm("Check Tokyo weather", stream_to_ui=False, stream_to_speech=False, save_history=False)
                self.assertIn("network request failed", res)

                # Verify failure status captured in trace
                trace = self.brain.last_agent_trace
                self.assertEqual(trace["tool_calls"][0]["execution_status"], "FAILED")
                self.assertEqual(trace["tool_calls"][0]["verification_status"], "REJECTED")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
