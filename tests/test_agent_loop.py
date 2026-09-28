"""
Tests for Core Agent Loop and Same-Model Execution (Section 15, 16, 18, 31, 36).
Verifies:
1. Agent loop is model-agnostic (does not hard-code model names).
2. Model emits native tool call -> Python executes and verifies -> returns tool result to SAME MAIN MODEL.
3. Message history contains correct provider structured tool message:
   role: "tool", content: formatted_result, tool_call_id, name.
4. Traces record all required observability fields: trace_id, main_model, available_tools, execution_status, etc.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.cancel_event = MagicMock()
        self.tts.cancel_event.is_set.return_value = False
        self.brain = FridayBrain(self.signals, self.tts)
        self.brain._tool_capability_cache[self.brain.model] = "VERIFIED"

    def test_same_model_called_with_tool_result(self):
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client
            active_model = self.brain.model

            # Turn 1: Model calls calculate tool
            mock_tc = MagicMock()
            mock_tc.id = "calc_call_101"
            mock_tc.function = MagicMock()
            mock_tc.function.name = "calculate"
            mock_tc.function.arguments = {"expression": "128 * 4"}

            resp_turn1 = MagicMock()
            resp_turn1.message = MagicMock()
            resp_turn1.message.content = ""
            resp_turn1.message.tool_calls = [mock_tc]

            # Turn 2: Model receives result and returns final answer
            resp_turn2 = MagicMock()
            resp_turn2.message = MagicMock()
            resp_turn2.message.content = "128 multiplied by 4 equals 512."
            resp_turn2.message.tool_calls = None

            mock_client.chat.side_effect = [resp_turn1, resp_turn2]

            res = await self.brain.query_llm("Calculate 128 * 4", stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertEqual(res, "128 multiplied by 4 equals 512.")

            # Verify client.chat was called twice with the EXACT SAME MODEL
            self.assertEqual(mock_client.chat.call_count, 2)
            for call in mock_client.chat.call_args_list:
                self.assertEqual(call.kwargs["model"], active_model)

            # Inspect the messages sent in Turn 2
            messages_turn2 = mock_client.chat.call_args_list[1].kwargs["messages"]
            tool_msg = next((m for m in messages_turn2 if m.get("role") == "tool"), None)
            self.assertIsNotNone(tool_msg, "Structured tool response message missing in turn 2")
            self.assertEqual(tool_msg["tool_call_id"], "calc_call_101")
            self.assertEqual(tool_msg["name"], "calculate")
            self.assertIn("512", tool_msg["content"])

            # Verify observability trace
            trace = self.brain.last_agent_trace
            self.assertIsNotNone(trace)
            self.assertEqual(trace["main_model"], active_model)
            self.assertTrue(trace["native_tool_call_detected"])
            self.assertEqual(trace["loop_iteration"], 2)
            self.assertEqual(trace["final_status"], "COMPLETED")
            self.assertEqual(len(trace["tool_calls"]), 1)
            self.assertEqual(trace["tool_calls"][0]["execution_status"], "SUCCESS")
            self.assertEqual(trace["tool_calls"][0]["verification_status"], "VERIFIED")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
