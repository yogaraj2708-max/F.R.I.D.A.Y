"""
Tests for Native Tool Calling Capability and Schemas (Section 8, 9, 10, 11, 28, 29).
Verifies:
1. Runtime capability probe using test_echo schema.
2. Verified models return VERIFIED; non-tool models return UNAVAILABLE / BLOCKED.
3. Registered tool schemas exposed to the model match valid functions.
4. Unknown tools safely rejected by dispatcher.
5. Malformed arguments safely rejected by argument validation without executing OS action.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from friday_core.settings import settings
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestNativeToolCalling(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.brain = FridayBrain(self.signals, self.tts)

    def test_registered_tool_schemas_exposed(self):
        tools = self.brain.get_agent_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 5)

        tool_names = [t["function"]["name"] for t in tools if "function" in t]
        expected_tools = [
            "web_search", "deep_research", "web_fetch", "launch_app",
            "inspect_ui", "click_control", "type_text", "analyze_image",
            "read_document", "weather", "timer", "system_telemetry",
            "system_time_date", "calculate"
        ]
        for expected in expected_tools:
            self.assertIn(expected, tool_names, f"Tool schema for '{expected}' missing from get_agent_tools()")

    def test_capability_probe_verified(self):
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client
            self.brain._tool_capability_cache.clear()

            # Simulate model returning native tool call for test_echo
            mock_tc = MagicMock()
            mock_tc.function = MagicMock()
            mock_tc.function.name = "test_echo"
            mock_resp = MagicMock()
            mock_resp.message = MagicMock()
            mock_resp.message.tool_calls = [mock_tc]
            mock_client.chat.return_value = mock_resp

            status = await self.brain.get_model_tool_capability_status("probe-model:1b")
            self.assertEqual(status, "VERIFIED")
            self.assertTrue(await self.brain.is_model_tool_capable("probe-model:1b"))

        asyncio.run(_test())

    def test_capability_probe_unavailable(self):
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client
            self.brain._tool_capability_cache.clear()

            # Simulate model returning regular text without tool calls
            mock_resp = MagicMock()
            mock_resp.message = MagicMock()
            mock_resp.message.tool_calls = None
            mock_resp.message.content = "I cannot call tools."
            mock_client.chat.return_value = mock_resp

            status = await self.brain.get_model_tool_capability_status("reasoning-model:8b")
            self.assertEqual(status, "UNAVAILABLE")
            self.assertFalse(await self.brain.is_model_tool_capable("reasoning-model:8b"))

        asyncio.run(_test())

    def test_unknown_tool_rejection(self):
        async def _test():
            res = await self.brain.dispatch_agent_tool("format_hard_drive", {"drive": "C:"})
            self.assertIn("Error: Unknown tool", res)
            self.assertIn("format_hard_drive", res)

        asyncio.run(_test())

    def test_malformed_arguments_safe_rejection(self):
        async def _test():
            # Missing required argument 'app_name' for launch_app
            res_launch = await self.brain.dispatch_agent_tool("launch_app", {})
            self.assertIn("Error: Argument validation failed", res_launch)

            # Missing required argument 'text' for type_text
            res_type = await self.brain.dispatch_agent_tool("type_text", {"app_name": "notepad"})
            self.assertIn("Error: Argument validation failed", res_type)

            # Missing required argument 'query' for web_search
            res_search = await self.brain.dispatch_agent_tool("web_search", {})
            self.assertIn("Error: Argument validation failed", res_search)

            # Invalid timer seconds
            res_timer = await self.brain.dispatch_agent_tool("timer", {"seconds": -10})
            self.assertIn("Error: Argument validation failed", res_timer)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
