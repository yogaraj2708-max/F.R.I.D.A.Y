import sys
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from friday_core.agent.compound import compound_parser
from friday_core.agent.planner import PEOVPlanner
from friday_core.agent.executor import PEOVExecutor
from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_core.skills.builtins.content import ContentGenerationSkill
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine
from friday_core.automation.action_engine import ui_action_engine

class TestCCalculatorNotepadRegression(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.signals = FridaySignals()
        self.state_transitions = []
        self.signals.state_changed.connect(lambda s: self.state_transitions.append(s))
        self.tts = FridayVoiceEngine(self.signals)
        self.brain = FridayBrain(self.signals, self.tts)
        self.planner = PEOVPlanner()
        self.executor = PEOVExecutor()

    async def asyncTearDown(self):
        self.tts.stop_speaking()

    def test_exact_user_command_parsing(self):
        """Test exact command: 'write a c program to make a working calculator and put it in my note pad'"""
        cmd = "write a c program to make a working calculator and put it in my note pad"
        plan = compound_parser.parse(cmd)
        self.assertIsNotNone(plan, "Compound parser must successfully parse reversed-syntax code directive")
        actions = [s.action for s in plan.steps]
        self.assertEqual(actions, ["open_app", "content_generation", "ui_focus", "ui_type_text", "ui_verify_content"])
        self.assertEqual(plan.steps[0].target, "Notepad")
        self.assertEqual(plan.steps[1].params.get("target_app"), "Notepad")
        self.assertEqual(plan.steps[3].params.get("app_name"), "Notepad")
        self.assertEqual(plan.steps[3].params.get("text"), "$content_generation.generated_text")

    def test_risk_gate_authoritative_app_selection(self):
        """Verify risk gate permits Notepad for 'note pad' and strictly blocks VS Code and Word."""
        cmd = "write a c program to make a working calculator and put it in my note pad"
        
        # Notepad must be authorized
        ok_np, r_np = agent_tool_bridge.risk_gate("launch_app", {"target_app": "Notepad"}, user_query=cmd)
        self.assertTrue(ok_np, f"Notepad must be authorized: {r_np}")
        
        # VS Code must be blocked
        ok_vsc, r_vsc = agent_tool_bridge.risk_gate("launch_app", {"app_name": "vscode"}, user_query=cmd)
        self.assertFalse(ok_vsc, "VS Code must be strictly blocked")
        self.assertIn("Target application 'vscode' was not requested", r_vsc)

        # Word must be blocked
        ok_wrd, r_wrd = agent_tool_bridge.risk_gate("launch_app", {"app_name": "word"}, user_query=cmd)
        self.assertFalse(ok_wrd, "Word must be strictly blocked")
        self.assertIn("Target application 'word' was not requested", r_wrd)

    def test_content_generation_produces_valid_c_calculator(self):
        """Verify content generation produces clean working C calculator source code without markdown fences."""
        skill = ContentGenerationSkill()
        res = skill.execute({"prompt": "a c program to make a working calculator", "target_app": "Notepad"}, "op_test")
        self.assertTrue(res.get("success"))
        code = res.get("generated_text", "")
        self.assertIn("#include", code)
        self.assertIn("main", code)
        self.assertTrue(any(op in code for op in ["+", "-", "*", "/"]))
        # Must not contain unstripped markdown fences at boundary
        self.assertFalse(code.strip().startswith("```c"))
        self.assertFalse(code.strip().endswith("```"))

    def test_adjacent_case_1_put_hello_world(self):
        """1. 'put hello world in my Notepad'"""
        cmd = "put hello world in my Notepad"
        ok, r = agent_tool_bridge.risk_gate("type_text", {"app_name": "notepad", "text": "hello world"}, user_query=cmd)
        self.assertTrue(ok)
        ok_vsc, _ = agent_tool_bridge.risk_gate("launch_app", {"app_name": "vscode"}, user_query=cmd)
        self.assertFalse(ok_vsc)

    def test_adjacent_case_2_write_c_program(self):
        """2. 'write a C program and put it in my Notepad'"""
        cmd = "write a C program and put it in my Notepad"
        plan = compound_parser.parse(cmd)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.steps[0].target, "Notepad")

    def test_adjacent_case_3_write_python_program(self):
        """3. 'write a Python program and put it in my Notepad'"""
        cmd = "write a Python program and put it in my Notepad"
        plan = compound_parser.parse(cmd)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.steps[0].target, "Notepad")

    def test_adjacent_case_4_open_notepad(self):
        """4. 'open Notepad'"""
        cmd = "open Notepad"
        ok, _ = agent_tool_bridge.risk_gate("launch_app", {"app_name": "notepad"}, user_query=cmd)
        self.assertTrue(ok)

    def test_adjacent_case_5_open_calculator(self):
        """5. 'open Calculator'"""
        cmd = "open Calculator"
        ok, _ = agent_tool_bridge.risk_gate("launch_app", {"app_name": "calculator"}, user_query=cmd)
        self.assertTrue(ok)
        ok_np, _ = agent_tool_bridge.risk_gate("launch_app", {"app_name": "notepad"}, user_query=cmd)
        self.assertFalse(ok_np)

    async def test_adjacent_case_6_failed_notepad_launch(self):
        """6. Failed Notepad launch returns honest error, never claims security filters or suggests VS Code."""
        with patch.object(ui_action_engine, "launch_app", return_value={"success": False, "message": "Executable not found."}):
            res = await self.brain.dispatch_agent_tool("launch_app", {"app_name": "notepad"})
            self.assertIn("Failed to launch application 'notepad'", res)
            self.assertNotIn("security filters", res)
            self.assertNotIn("VS Code", res)

    async def test_adjacent_case_7_failed_focus(self):
        """7. Failed focus acquisition returns honest error."""
        with patch.object(ui_action_engine, "type_text", return_value={"success": False, "message": "Could not focus window."}):
            res = await self.brain.dispatch_agent_tool("type_text", {"app_name": "notepad", "text": "test"})
            self.assertIn("Typing operation failed", res)
            self.assertNotIn("security filters", res)

    async def test_adjacent_case_8_failed_keyboard_input(self):
        """8. Failed keyboard input reports actual failure."""
        with patch.object(ui_action_engine, "type_text", return_value={"success": False, "message": "SendInput failed."}):
            res = await self.brain.dispatch_agent_tool("type_text", {"app_name": "notepad", "text": "test"})
            self.assertIn("Typing operation failed", res)

    async def test_adjacent_case_9_tool_timeout(self):
        """9. Tool timeout returns bounded message and clears generating/speaking state."""
        with patch.object(self.brain.client, "chat", side_effect=asyncio.TimeoutError("Stalled")):
            try:
                await asyncio.wait_for(self.brain.query_llm("test stalled query", stream_to_ui=False, stream_to_speech=False), timeout=1.0)
            except Exception:
                pass
            self.assertFalse(self.brain.is_generating)
            self.assertFalse(self.tts.is_speaking)
            self.assertEqual(self.state_transitions[-1], "idle")

    def test_adjacent_case_10_user_interruption_during_tts(self):
        """10. User interruption during TTS cleanly clears speaking state."""
        self.tts.is_speaking = True
        self.signals.state_changed.emit("speaking")
        self.tts.stop_speaking()
        self.assertFalse(self.tts.is_speaking)
        self.assertEqual(self.state_transitions[-1], "idle")

if __name__ == "__main__":
    unittest.main()
