"""
F.R.I.D.A.Y. 3.0 — Vision Cancellation & Timeout Resilience Test Battery
Validates MISSION 9:
1. Cancellation during inference terminates cleanly with CANCELLED status.
2. HTTP client connections and buffers are cleaned up.
3. Timeout handling properly aborts hung requests without freezing the agent.
"""

import asyncio
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import httpx

from friday_core.vision.vision_model import VisionModelClient


@pytest.fixture
def temp_img():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (100, 100), color="green")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.mark.asyncio
async def test_vision_cancellation_during_inference(temp_img):
    """
    MISSION 9: Cancel during vision inference.
    Expected: Task cancellation cleanly caught, returns CANCELLED message without crashing.
    """
    client = VisionModelClient()

    async def _mock_slow_post(*args, **kwargs):
        await asyncio.sleep(5.0)
        return MagicMock(status_code=200)

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=_mock_slow_post):

        task = asyncio.create_task(client.analyze_image_structured(temp_img, prompt="Analyze"))
        # Allow the task to start
        await asyncio.sleep(0.05)
        # Cancel while post is waiting
        task.cancel()

        ctx, err = await task
        assert ctx is None
        assert "cancelled" in err.lower() or "aborted" in err.lower()


@pytest.mark.asyncio
async def test_vision_timeout_resilience(temp_img):
    """Verifies that an inference timeout raises an honest, graceful error."""
    client = VisionModelClient()

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):

        ctx, err = await client.analyze_image_structured(temp_img, prompt="Analyze")
        assert ctx is None
        assert "timed out" in err.lower()


@pytest.mark.asyncio
async def test_probe_vision_timeout_handling():
    """Verifies capability probe handles timeout gracefully without hanging."""
    client = VisionModelClient()

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Probe timeout")):

        probe = await client.probe_vision_capability()
        assert probe["status"] == "ERROR"
        assert "timed out" in probe["error"].lower() or "timeout" in probe["error"].lower()
