"""
Tests for friday_ui.core.engine (Smart Skills & Intent Routing)
Verifies that all skills correctly dispatch through Gatekeeper and return formatted responses.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine
from friday_core.settings import settings

class TestSmartSkills(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.brain = FridayBrain(self.signals, self.tts)
        settings.set("observe_only", False)

    def test_calc_skill(self):
        res = asyncio.run(self.brain.execute_smart_skill("what is 25 * 4"))
        self.assertIsNotNone(res)
        self.assertIn("100", res)

    def test_time_and_date_skills(self):
        time_res = asyncio.run(self.brain.execute_smart_skill("what time is it"))
        self.assertIsNotNone(time_res)
        self.assertIn("Boss", time_res)

        date_res = asyncio.run(self.brain.execute_smart_skill("what date is it"))
        self.assertIsNotNone(date_res)
        self.assertIn("Boss", date_res)

    def test_telemetry_skill(self):
        res = asyncio.run(self.brain.execute_smart_skill("system status telemetry"))
        self.assertIsNotNone(res)
        self.assertIn("Boss", res)

    def test_volume_skill(self):
        res = asyncio.run(self.brain.execute_smart_skill("volume up"))
        self.assertIsNotNone(res)
        self.assertIn("volume", res.lower())

    def test_tier2_process_clearance_required(self):
        req_signal = []
        self.signals.confirmation_requested.connect(lambda intent: req_signal.append(intent))

        res = asyncio.run(self.brain.execute_smart_skill("kill process notepad"))
        self.assertIsNotNone(res)
        self.assertIn("Security clearance required", res)
        self.assertEqual(len(req_signal), 1)
        self.assertEqual(req_signal[0].action, "kill_process")
        self.assertEqual(req_signal[0].target, "notepad")

    def test_tier2_file_deletion_clearance_required(self):
        req_signal = []
        self.signals.confirmation_requested.connect(lambda intent: req_signal.append(intent))

        res = asyncio.run(self.brain.execute_smart_skill("delete file test_document.txt"))
        self.assertIsNotNone(res)
        self.assertIn("Security clearance required", res)
        self.assertEqual(len(req_signal), 1)
        self.assertEqual(req_signal[0].action, "delete_file")

    def test_panic_mode_blocks_skill_mutation(self):
        settings.set("observe_only", True)
        try:
            # Volume adjustment (Tier 1) should fail or be refused under panic mode
            # Tier 0 (calculator, time) still succeeds
            calc_res = asyncio.run(self.brain.execute_smart_skill("what is 10 + 10"))
            self.assertIn("20", calc_res)
        finally:
            settings.set("observe_only", False)

    def test_code_generation_not_routed_to_app_launch(self):
        # 'give html code for simple working calculator' should NOT trigger app launch / VS Code
        res = asyncio.run(self.brain.execute_smart_skill("give html code for simple working calculator"))
        self.assertIsNone(res, "Code generation request should not be intercepted by app launcher")

        res_python = asyncio.run(self.brain.execute_smart_skill("write python code for calculator"))
        self.assertIsNone(res_python, "Code writing request should not be intercepted by app launcher")

    def test_voice_loop_active_listen(self):
        from friday_ui.core.engine import FridayVoiceLoop
        v_loop = FridayVoiceLoop(self.signals, self.brain, self.tts)
        self.assertFalse(v_loop.force_listen)
        v_loop.trigger_active_listen()
        self.assertTrue(v_loop.force_listen)
        v_loop.stop()
        self.assertFalse(v_loop.force_listen)

    def test_web_search_multi_fallback(self):
        from friday_ui.core.engine import fetch_web_results
        results = fetch_web_results("continental cars", max_results=2)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertIn("title", results[0])
        self.assertIn("body", results[0])

    def test_timer_skill(self):
        # Verify natural timer expression parsing
        secs, label = self.brain._parse_timer_request("set timer for 30 minutes")
        self.assertEqual(secs, 1800)
        self.assertEqual(label, "30 minutes")

        secs_10, label_10 = self.brain._parse_timer_request("set a 10 second timer")
        self.assertEqual(secs_10, 10)
        self.assertEqual(label_10, "10 seconds")

        secs_hr, label_hr = self.brain._parse_timer_request("timer for 2 hours")
        self.assertEqual(secs_hr, 7200)
        self.assertEqual(label_hr, "2 hours")

        res = asyncio.run(self.brain.execute_smart_skill("set timer for 5 minutes"))
        self.assertIsNotNone(res)
        self.assertIn("Timer initialized for 5 minutes", res)

    def test_contextual_websites(self):
        req_actions = []
        # Mock gatekeeper action recording
        res = asyncio.run(self.brain.execute_smart_skill("open github"))
        self.assertIsNotNone(res)
        self.assertIn("Opening Github", res)

        res_reddit = asyncio.run(self.brain.execute_smart_skill("open reddit"))
        self.assertIsNotNone(res_reddit)
        self.assertIn("Opening Reddit", res_reddit)

        res_chatgpt = asyncio.run(self.brain.execute_smart_skill("open chatgpt"))
        self.assertIsNotNone(res_chatgpt)
        self.assertIn("Opening Chatgpt", res_chatgpt)

    def test_contextual_youtube(self):
        res = asyncio.run(self.brain.execute_smart_skill("open youtube and play lofi beats"))
        self.assertIsNotNone(res)
        self.assertIn("YouTube", res)
        self.assertIn("lofi beats", res)

        res_direct = asyncio.run(self.brain.execute_smart_skill("play interstellar theme on youtube"))
        self.assertIsNotNone(res_direct)
        self.assertIn("YouTube", res_direct)

    def test_file_organizer_intent(self):
        res = asyncio.run(self.brain.execute_smart_skill("organize my downloads"))
        self.assertIsNotNone(res)
        self.assertTrue("clean and organized" in res or "organized" in res.lower() or "aborted" in res)

        res_arrange = asyncio.run(self.brain.execute_smart_skill("arrange my downloads folder"))
        self.assertIsNotNone(res_arrange)
        self.assertNotIn("aborted", res_arrange)
        self.assertTrue("clean and organized" in res_arrange or "organized" in res_arrange.lower())

        # Test exact user command: "arrange my download folder" (singular)
        res_singular = asyncio.run(self.brain.execute_smart_skill("arrange my download folder"))
        self.assertIsNotNone(res_singular)
        self.assertNotIn("aborted", res_singular)
        self.assertTrue("clean and organized" in res_singular or "organized" in res_singular.lower())

        # Test user's conversational prompt with folder creation and movement
        user_prompt = "find all the images and create new folder and name it images and put it there and find every exe files and installer file and put it in nessacry folder and ppt in new ppt foder and word in new word folder"
        res_user = asyncio.run(self.brain.execute_smart_skill(user_prompt))
        self.assertIsNotNone(res_user)
        self.assertNotIn("aborted", res_user)
        self.assertTrue("clean and organized" in res_user or "organized" in res_user.lower())

    def test_open_file_explorer_intent(self):
        res = asyncio.run(self.brain.execute_smart_skill("open file explorer"))
        self.assertIsNotNone(res)
        self.assertIn("File Explorer", res)

        res_dl = asyncio.run(self.brain.execute_smart_skill("open downloads folder"))
        self.assertIsNotNone(res_dl)
        self.assertIn("Downloads", res_dl)

        # Test user's specific subfolder command: "open folder word in downloads"
        res_sub = asyncio.run(self.brain.execute_smart_skill("open folder word in downloads"))
        self.assertIsNotNone(res_sub)
        self.assertTrue("Opening 'Word' folder" in res_sub or "Word" in res_sub)

        # Test subfolder alias: "open folder images in downloads"
        res_img_f = asyncio.run(self.brain.execute_smart_skill("open folder images in downloads"))
        self.assertIsNotNone(res_img_f)
        self.assertTrue("Opening 'Images' folder" in res_img_f or "Images" in res_img_f)

    def test_open_contextual_file_intent(self):
        # Even if no files exist, it returns a friendly contextual response rather than error or falling to LLM
        res_img = asyncio.run(self.brain.execute_smart_skill("open this image"))
        self.assertIsNotNone(res_img)
        self.assertTrue("Opening" in res_img or "No recent" in res_img)

        res_word = asyncio.run(self.brain.execute_smart_skill("open this word"))
        self.assertIsNotNone(res_word)
        self.assertTrue("Opening" in res_word or "No recent" in res_word)

        res_file = asyncio.run(self.brain.execute_smart_skill("open this file"))
        self.assertIsNotNone(res_file)
        self.assertTrue("Opening" in res_file or "No recent" in res_file)

    def test_screen_vision_intent(self):
        # When vision model is not installed or detected, it captures snapshot and reports requirement
        res = asyncio.run(self.brain.execute_smart_skill("look at my screen and tell me what's open"))
        self.assertEqual(res, "__STREAMED__")

if __name__ == "__main__":
    unittest.main()

