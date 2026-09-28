"""
F.R.I.D.A.Y. 3.0 — Vision Concurrency & Isolation Test Battery
Validates Section 33:
Concurrent execution of Vision tasks maintains separate task IDs, image IDs,
contexts, cancellation isolation, and result isolation.
"""

import asyncio
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from friday_core.vision.vision_model import VisionModelClient
from friday_core.vision.image_context import ImageContextManager


@pytest.fixture
def img_a():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (60, 60), color="red")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def img_b():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (60, 60), color="blue")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.mark.asyncio
async def test_concurrent_vision_requests_isolated_results(img_a, img_b):
    """
    Execute Vision A and Vision B concurrently.
    Verify separate image IDs, separate responses, and zero cross-talk.
    """
    client = VisionModelClient()

    async def _mock_post(url, json=None, **kwargs):
        # Inspect which image was passed in payload
        # A returns red, B returns blue
        prompt = json.get("prompt", "")
        if "Image A" in prompt:
            res_json = '{"description": "A solid red square", "objects": ["red square"], "uncertainty": "OBSERVED"}'
        else:
            res_json = '{"description": "A solid blue square", "objects": ["blue square"], "uncertainty": "OBSERVED"}'
        mock_r = MagicMock(status_code=200)
        mock_r.json.return_value = {"response": res_json}
        await asyncio.sleep(0.02)
        return mock_r

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=_mock_post):

        task_a = asyncio.create_task(client.analyze_image_structured(
            img_a, prompt="Describe Image A", session_id="session_concurrent"
        ))
        task_b = asyncio.create_task(client.analyze_image_structured(
            img_b, prompt="Describe Image B", session_id="session_concurrent"
        ))

        ctx_a, err_a = await task_a
        ctx_b, err_b = await task_b

        assert err_a == "" and err_b == ""
        assert ctx_a is not None and ctx_b is not None

        # Distinct IDs within the same session
        assert ctx_a.image_id != ctx_b.image_id

        # Isolated descriptions
        assert "red square" in ctx_a.description
        assert "blue square" in ctx_b.description
        assert "blue" not in ctx_a.description
        assert "red" not in ctx_b.description


@pytest.mark.asyncio
async def test_concurrency_cancellation_isolation(img_a, img_b):
    """
    Cancelling Task A during concurrent execution must NOT cancel Task B.
    """
    client = VisionModelClient()

    async def _mock_post(url, json=None, **kwargs):
        prompt = json.get("prompt", "")
        if "Task A" in prompt:
            await asyncio.sleep(5.0)  # Slow task to be cancelled
        else:
            await asyncio.sleep(0.05)  # Fast task that should succeed
        mock_r = MagicMock(status_code=200)
        mock_r.json.return_value = {"response": '{"description": "Completed Task B", "uncertainty": "OBSERVED"}'}
        return mock_r

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=_mock_post):

        task_a = asyncio.create_task(client.analyze_image_structured(
            img_a, prompt="Task A slow", session_id="session_canc"
        ))
        task_b = asyncio.create_task(client.analyze_image_structured(
            img_b, prompt="Task B fast", session_id="session_canc"
        ))

        # Cancel Task A shortly after starting
        await asyncio.sleep(0.02)
        task_a.cancel()

        ctx_a, err_a = await task_a
        ctx_b, err_b = await task_b

        # Task A is cancelled
        assert ctx_a is None
        assert "cancelled" in err_a.lower() or "aborted" in err_a.lower()

        # Task B succeeds unaffected
        assert err_b == ""
        assert ctx_b is not None
        assert "Completed Task B" in ctx_b.description
