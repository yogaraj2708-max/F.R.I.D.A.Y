"""
Tests for friday_core.router.semantic_router (Hybrid Cascading Intent Router)
Verifies:
1. FastLocalEmbedder determinism, dimensionality, normalization, and sub-millisecond execution.
2. Centroid precomputation and semantic vector cluster separation.
3. Tier 1 fast-path routing accuracy across 10 operational domains.
4. Entity and parameter extraction (volume direction, location, query, app name).
5. Seamless integration and fallback in FridayBrain.execute_smart_skill.
"""

import unittest
import asyncio
import time
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

from friday_core.router.semantic_router import (
    FastLocalEmbedder,
    SemanticIntentRouter,
    SkillIntent,
    RouteResult,
    extract_parameters
)
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.settings import settings


class TestFastLocalEmbedder(unittest.TestCase):
    def setUp(self):
        self.embedder = FastLocalEmbedder(dim=384)

    def test_dimensions_and_normalization(self):
        v1 = self.embedder.embed_text("how much juice is left")
        self.assertEqual(v1.shape[0], 384)
        self.assertAlmostEqual(float(np.linalg.norm(v1)), 1.0, places=5)

        # Empty string yields zero vector
        v_empty = self.embedder.embed_text("")
        self.assertEqual(float(np.linalg.norm(v_empty)), 0.0)

    def test_determinism(self):
        phrase = "crank the tunes and play some rock"
        v1 = self.embedder.embed_text(phrase)
        v2 = self.embedder.embed_text(phrase)
        np.testing.assert_array_almost_equal(v1, v2)

    def test_submillisecond_performance(self):
        t0 = time.perf_counter()
        iterations = 500
        for _ in range(iterations):
            self.embedder.embed_text("battery status and hardware diagnostics")
        elapsed = time.perf_counter() - t0
        avg_ms = (elapsed / iterations) * 1000.0
        # Average per-embedding time must be well under 0.5ms
        self.assertLess(avg_ms, 0.5, f"Embedding too slow: {avg_ms:.3f}ms")


class TestSemanticIntentRouter(unittest.TestCase):
    def setUp(self):
        self.router = SemanticIntentRouter(threshold=0.76)

    def test_centroids_precomputed(self):
        self.assertIn(SkillIntent.MEDIA_CONTROL, self.router.centroids)
        self.assertIn(SkillIntent.SYSTEM_TELEMETRY, self.router.centroids)
        self.assertIn(SkillIntent.DESKTOP_AUDIO, self.router.centroids)
        self.assertIn(SkillIntent.SYSTEM_TIME_DATE, self.router.centroids)
        self.assertIn(SkillIntent.DESKTOP_ACTION, self.router.centroids)
        self.assertIn(SkillIntent.APP_LAUNCH, self.router.centroids)
        self.assertIn(SkillIntent.WEATHER, self.router.centroids)
        self.assertIn(SkillIntent.DEEP_RESEARCH, self.router.centroids)

        for intent, c in self.router.centroids.items():
            self.assertAlmostEqual(float(np.linalg.norm(c)), 1.0, places=5)

    def test_colloquial_phrasing_accuracy(self):
        test_cases = [
            ("how much juice is left", SkillIntent.SYSTEM_TELEMETRY),
            ("how much battery is left", SkillIntent.SYSTEM_TELEMETRY),
            ("crank the tunes", SkillIntent.MEDIA_CONTROL),
            ("volume up", SkillIntent.DESKTOP_AUDIO),
            ("turn up the volume", SkillIntent.DESKTOP_AUDIO),
            ("snap my desktop", SkillIntent.DESKTOP_ACTION),
            ("take a screenshot", SkillIntent.DESKTOP_ACTION),
            ("what time is it", SkillIntent.SYSTEM_TIME_DATE),
            ("tell me the date", SkillIntent.SYSTEM_TIME_DATE),
            ("what is the weather today", SkillIntent.WEATHER),
            ("deeply research solid state batteries", SkillIntent.DEEP_RESEARCH),
            ("open word", SkillIntent.APP_LAUNCH),
            ("who was abraham lincoln", SkillIntent.GENERAL_CHAT),
            ("write python code for a calculator", SkillIntent.GENERAL_CHAT),
        ]

        for query, expected_intent in test_cases:
            res = asyncio.run(self.router.route(query))
            self.assertEqual(
                res.intent,
                expected_intent,
                f"Query '{query}' expected {expected_intent} but got {res.intent} (score: {res.confidence:.3f})"
            )

    def test_parameter_extraction(self):
        # Audio actions
        p_up = extract_parameters(SkillIntent.DESKTOP_AUDIO, "turn up the volume")
        self.assertEqual(p_up.get("action"), "up")
        p_down = extract_parameters(SkillIntent.DESKTOP_AUDIO, "lower the volume")
        self.assertEqual(p_down.get("action"), "down")
        p_mute = extract_parameters(SkillIntent.DESKTOP_AUDIO, "mute sound")
        self.assertEqual(p_mute.get("action"), "mute")

        # Time/date actions
        p_date = extract_parameters(SkillIntent.SYSTEM_TIME_DATE, "tell me today's date")
        self.assertEqual(p_date.get("action"), "date")
        p_time = extract_parameters(SkillIntent.SYSTEM_TIME_DATE, "what time is it")
        self.assertEqual(p_time.get("action"), "time")

        # App launch
        p_app = extract_parameters(SkillIntent.APP_LAUNCH, "launch vs code")
        self.assertEqual(p_app.get("app_name"), "vs code")

        # Weather location
        p_weather = extract_parameters(SkillIntent.WEATHER, "weather in tokyo")
        self.assertEqual(p_weather.get("location"), "tokyo")

        # Deep research
        p_research = extract_parameters(SkillIntent.DEEP_RESEARCH, "deep research on fusion reactors")
        self.assertEqual(p_research.get("query"), "fusion reactors")


class TestFridayBrainSemanticIntegration(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.brain = FridayBrain(self.signals, self.tts)
        settings.set("observe_only", False)
        settings.set("semantic_routing", True)

    def test_semantic_telemetry_dispatch(self):
        # "how much juice is left" previously had no regex match
        res = asyncio.run(self.brain.execute_smart_skill("how much juice is left"))
        self.assertIsNotNone(res)
        self.assertTrue("battery" in res.lower() or "operational" in res.lower())

    def test_semantic_screenshot_dispatch(self):
        # "snap my desktop" previously had no regex match
        res = asyncio.run(self.brain.execute_smart_skill("snap my desktop"))
        self.assertIsNotNone(res)
        self.assertIn("Screenshot snipping tool activated", res)

    def test_semantic_volume_dispatch(self):
        res = asyncio.run(self.brain.execute_smart_skill("crank the volume"))
        self.assertIsNotNone(res)
        self.assertIn("Master volume increased", res)

    def test_code_requests_bypass_skills(self):
        # Full code generation must bypass skills and go straight to LLM
        res = asyncio.run(self.brain.execute_smart_skill("give html code for simple working calculator"))
        self.assertIsNone(res)

        res_py = asyncio.run(self.brain.execute_smart_skill("write python code for a calculator"))
        self.assertIsNone(res_py)

    def test_math_calculation_preservation(self):
        res = asyncio.run(self.brain.execute_smart_skill("what is 25 * 4"))
        self.assertIsNotNone(res)
        self.assertIn("100", res)

    def test_app_launch_typo_disambiguation(self):
        # "ope vs coe for me" typo must map to VS Code launch instead of logistics comparison chat
        res_vsc = asyncio.run(self.brain.execute_smart_skill("ope vs coe for me"))
        self.assertIsNotNone(res_vsc)
        self.assertTrue("vs code" in res_vsc.lower() or "opening" in res_vsc.lower())

        # "ope wrd for me" typo must map to Word launch
        res_wrd = asyncio.run(self.brain.execute_smart_skill("ope wrd for me"))
        self.assertIsNotNone(res_wrd)
        self.assertTrue("word" in res_wrd.lower())

    def test_youtube_typo_media_dispatch(self):
        # "open youtibe and olay socle" typo must map to YouTube media play rather than chat hallucination
        res = asyncio.run(self.brain.execute_smart_skill("open youtibe and olay socle"))
        self.assertIsNotNone(res)
        self.assertTrue("youtube" in res.lower() or "playing" in res.lower())


class TestLayaDecisionEngineIntegration(unittest.TestCase):
    """Unit tests for Convai Innovations Laya System 1 decision engine integration."""

    def setUp(self):
        self.router = SemanticIntentRouter(threshold=0.76, decision_engine="laya")

    def test_laya_graceful_fallback_when_uninstalled(self):
        """When laya is not installed, router must fall back to Ollama or Tier 1 without throwing."""
        with patch.object(self.router, "_get_laya_router", return_value=None):
            res = asyncio.run(self.router.route("volume up"))
            self.assertIsNotNone(res)
            self.assertEqual(res.intent, SkillIntent.DESKTOP_AUDIO)

    def test_laya_prediction_dispatch(self):
        """When laya router is available, single-pass typed choice is dispatched."""
        mock_laya = MagicMock()
        mock_laya.predict.return_value = {"intent": "media_control"}

        with patch.object(self.router, "_get_laya_router", return_value=mock_laya):
            res = asyncio.run(self.router.route("crank the tunes"))
            self.assertIsNotNone(res)
            self.assertEqual(res.intent, SkillIntent.MEDIA_CONTROL)
            self.assertEqual(res.matched_exemplar, "laya_convai")
            self.assertEqual(res.confidence, 0.98)
            mock_laya.predict.assert_called_once()

    def test_decision_engine_mode_switching(self):
        """Switching decision engine between vector, laya, and ollama modes."""
        # 1. Vector mode (forces Tier 1 embedder)
        self.router.decision_engine = "vector"
        res_vec = asyncio.run(self.router.route("volume up"))
        self.assertEqual(res_vec.tier, 1)

        # 2. Ollama mode (Tier 2 nano decision maker)
        self.router.decision_engine = "ollama"
        res_ollama = asyncio.run(self.router.route("volume up"))
        self.assertEqual(res_ollama.intent, SkillIntent.DESKTOP_AUDIO)


if __name__ == "__main__":
    unittest.main()
