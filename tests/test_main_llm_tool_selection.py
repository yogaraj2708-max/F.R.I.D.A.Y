"""
Tests for Main LLM Tool Selection Authority (Section 1, 13, 14, 21, 22, 23, 25, 26, TEST 01-03, 05-07).
Verifies:
1. MAIN AGENT MODEL alone decides whether a tool is needed.
2. "Hi" causes ZERO tools (TEST 01).
3. "What's happening with NVIDIA right now?" invokes native web_search from model (TEST 02).
4. "this is your brain" causes ZERO web_search even with Graphify context (TEST 03).
5. Attached PDF + "Explain item 12" allows model to choose read_document (TEST 05).
6. Attached Image + "Describe this image" allows model to choose analyze_image (TEST 06).
7. Attached Image + "Hi" causes ZERO vision calls (TEST 07).
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from friday_core.settings import settings
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestMainLLMToolSelection(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.cancel_event = MagicMock()
        self.tts.cancel_event.is_set.return_value = False
        self.brain = FridayBrain(self.signals, self.tts)
        self.brain._tool_capability_cache[self.brain.model] = "VERIFIED"

    def test_test01_hi_causes_zero_tool_calls(self):
        """TEST 01: 'Hi' -> Expected: 0 tool calls, final conversational answer."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client

            # Model decides no tools are needed and directly produces final content
            mock_resp = MagicMock()
            mock_resp.message = MagicMock()
            mock_resp.message.content = "Greetings, Boss. Systems are fully nominal. How can I assist you?"
            mock_resp.message.tool_calls = None
            mock_client.chat.return_value = mock_resp

            res = await self.brain.query_llm("Hi", stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertIn("Greetings, Boss", res)

            # Verify trace records 0 tool calls
            trace = self.brain.last_agent_trace
            self.assertIsNotNone(trace)
            self.assertFalse(trace["native_tool_call_detected"])
            self.assertEqual(len(trace.get("tool_calls", [])), 0)
            self.assertEqual(trace["final_status"], "COMPLETED")

        asyncio.run(_test())

    def test_test02_web_autonomy_nvidia_invokes_web_search(self):
        """TEST 02: 'What's happening with NVIDIA right now?' -> Expected: Model calls web_search."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client

            # Turn 1: Model requests web_search natively
            mock_tc = MagicMock()
            mock_tc.id = "call_nvidia_1"
            mock_tc.function = MagicMock()
            mock_tc.function.name = "web_search"
            mock_tc.function.arguments = {"query": "NVIDIA latest news and stock updates"}

            mock_resp_1 = MagicMock()
            mock_resp_1.message = MagicMock()
            mock_resp_1.message.content = ""
            mock_resp_1.message.tool_calls = [mock_tc]

            # Turn 2: Same model receives tool result and produces final answer
            mock_resp_2 = MagicMock()
            mock_resp_2.message = MagicMock()
            mock_resp_2.message.content = "NVIDIA has announced new Blackwell GPUs with enhanced AI inference capability."
            mock_resp_2.message.tool_calls = None

            mock_client.chat.side_effect = [mock_resp_1, mock_resp_2]

            with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                mock_dispatch.return_value = "Search Results: NVIDIA reveals next-generation architecture and record quarterly revenue."

                res = await self.brain.query_llm("What's happening with NVIDIA right now?", stream_to_ui=False, stream_to_speech=False, save_history=False)
                self.assertIn("Blackwell", res)

                # Verify tool dispatch occurred for web_search
                mock_dispatch.assert_called_once_with("web_search", {"query": "NVIDIA latest news and stock updates"})

                # Verify trace
                trace = self.brain.last_agent_trace
                self.assertTrue(trace["native_tool_call_detected"])
                self.assertEqual(trace["tool_calls"][0]["tool_name"], "web_search")
                self.assertEqual(trace["tool_calls"][0]["risk_status"], "AUTHORIZED")

        asyncio.run(_test())

    def test_test03_graphify_this_is_your_brain_causes_zero_web_search(self):
        """TEST 03: 'this is your brain' with Graphify context -> Expected: 0 web_search."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client

            # Model answers using internal context, deciding NO tools are needed
            mock_resp = MagicMock()
            mock_resp.message = MagicMock()
            mock_resp.message.content = "I recognize my core neural topology and modular architecture, Boss."
            mock_resp.message.tool_calls = None
            mock_client.chat.return_value = mock_resp

            prompt_with_graphify = (
                "[Graphify System Context: friday_core/engine.py: 5022 lines, PEOVPlanner, MemoryManager]\n"
                "this is your brain"
            )
            res = await self.brain.query_llm(prompt_with_graphify, stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertIn("neural topology", res)

            # Verify zero tool calls
            trace = self.brain.last_agent_trace
            self.assertFalse(trace["native_tool_call_detected"])
            self.assertEqual(len(trace.get("tool_calls", [])), 0)

        asyncio.run(_test())

    def test_test05_document_test_pdf_explanation(self):
        """TEST 05: PDF attached + 'Explain item 12 from this PDF' -> Model calls read_document."""
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client

            mock_tc = MagicMock()
            mock_tc.id = "call_pdf_12"
            mock_tc.function = MagicMock()
            mock_tc.function.name = "read_document"
            mock_tc.function.arguments = {"file_path": "C:\\docs\\report.pdf", "query": "item 12"}

            mock_resp_1 = MagicMock()
            mock_resp_1.message = MagicMock()
            mock_resp_1.message.content = ""
            mock_resp_1.message.tool_calls = [mock_tc]

            mock_resp_2 = MagicMock()
            mock_resp_2.message = MagicMock()
            mock_resp_2.message.content = "Item 12 describes the security validation protocol for automated agent operations."
            mock_resp_2.message.tool_calls = None

            mock_client.chat.side_effect = [mock_resp_1, mock_resp_2]

            with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                mock_dispatch.return_value = "Document Content: [Page 4] Item 12: Security validation protocol mandates risk gating."

                prompt = "[Attached PDF: report.pdf | Path: C:\\docs\\report.pdf]\nExplain item 12 from this PDF."
                res = await self.brain.query_llm(prompt, stream_to_ui=False, stream_to_speech=False, save_history=False)
                self.assertIn("security validation protocol", res)
                mock_dispatch.assert_called_once_with("read_document", {"file_path": "C:\\docs\\report.pdf", "query": "item 12"})

        asyncio.run(_test())

    def test_test06_and_test07_image_attached_handling(self):
        """
        TEST 06: Attached Image + 'Describe this image' -> Model calls analyze_image.
        TEST 07: Attached Image + 'Hi' -> ZERO vision tool calls.
        """
        async def _test():
            mock_client = AsyncMock()
            self.brain.client = mock_client

            # TEST 07: Image attached + "Hi" -> Model does NOT call vision tool
            mock_resp_hi = MagicMock()
            mock_resp_hi.message = MagicMock()
            mock_resp_hi.message.content = "Hello, Boss! I see you uploaded an image. How can I help you with it?"
            mock_resp_hi.message.tool_calls = None
            mock_client.chat.return_value = mock_resp_hi

            prompt_hi = "[Attached Image: diagram.png | Path: C:\\images\\diagram.png]\nBoss Directive:\nHi"
            res_hi = await self.brain.query_llm(prompt_hi, stream_to_ui=False, stream_to_speech=False, save_history=False)
            self.assertIn("Hello, Boss", res_hi)
            self.assertFalse(self.brain.last_agent_trace["native_tool_call_detected"])

            # TEST 06: Image attached + "Describe this image" -> Model calls analyze_image
            mock_tc = MagicMock()
            mock_tc.id = "call_img_1"
            mock_tc.function = MagicMock()
            mock_tc.function.name = "analyze_image"
            mock_tc.function.arguments = {"image_path": "C:\\images\\diagram.png", "prompt": "Describe this image"}

            mock_resp_img1 = MagicMock()
            mock_resp_img1.message = MagicMock()
            mock_resp_img1.message.content = ""
            mock_resp_img1.message.tool_calls = [mock_tc]

            mock_resp_img2 = MagicMock()
            mock_resp_img2.message = MagicMock()
            mock_resp_img2.message.content = "The image illustrates a distributed system network architecture."
            mock_resp_img2.message.tool_calls = None

            mock_client.chat.side_effect = [mock_resp_img1, mock_resp_img2]

            with patch.object(self.brain, "dispatch_agent_tool", new_callable=AsyncMock) as mock_dispatch:
                mock_dispatch.return_value = "Vision Analysis: The diagram shows 3 server nodes connected to a central load balancer."
                prompt_describe = "[Attached Image: diagram.png | Path: C:\\images\\diagram.png]\nBoss Directive:\nDescribe this image"
                res_desc = await self.brain.query_llm(prompt_describe, stream_to_ui=False, stream_to_speech=False, save_history=False)
                self.assertIn("distributed system network architecture", res_desc)
                mock_dispatch.assert_called_once_with("analyze_image", {"image_path": "C:\\images\\diagram.png", "prompt": "Describe this image"})

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
