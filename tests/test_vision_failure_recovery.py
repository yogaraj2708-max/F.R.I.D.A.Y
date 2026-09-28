"""
F.R.I.D.A.Y. 3.0 — Vision Failure Recovery & Honest Error Propagation Test Battery
Validates Section 19:
System gracefully handles Ollama offline, model unavailable, HTTP errors, empty model responses,
malformed JSON, and ensures honest failure propagation without hallucination.
"""

import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from friday_core.vision.vision_model import VisionModelClient


@pytest.fixture
def valid_img():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (80, 80), color="yellow")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.mark.asyncio
async def test_ollama_offline_honest_failure(valid_img):
    client = VisionModelClient()
    with patch.object(client, "check_ollama_online", return_value=False):
        ctx, err = await client.analyze_image_structured(valid_img)
        assert ctx is None
        assert "offline or unreachable" in err


@pytest.mark.asyncio
async def test_vision_model_unavailable_honest_failure(valid_img):
    """MISSION 10: Vision model unavailable in Ollama."""
    client = VisionModelClient()
    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value=None):
        ctx, err = await client.analyze_image_structured(valid_img)
        assert ctx is None
        assert "UNAVAILABLE" in err or "is not available" in err


@pytest.mark.asyncio
async def test_provider_http_500_error(valid_img):
    client = VisionModelClient()
    mock_resp = MagicMock(status_code=500)

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):
        ctx, err = await client.analyze_image_structured(valid_img)
        assert ctx is None
        assert "HTTP status 500" in err


@pytest.mark.asyncio
async def test_empty_response_from_vision_model(valid_img):
    client = VisionModelClient()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"response": ""}

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):
        ctx, err = await client.analyze_image_structured(valid_img)
        assert ctx is None
        assert "empty response" in err.lower()


@pytest.mark.asyncio
async def test_malformed_json_fallback_resilience(valid_img):
    client = VisionModelClient()
    mock_resp = MagicMock(status_code=200)
    # Model returns raw markdown / unformatted text instead of JSON
    mock_resp.json.return_value = {"response": "I see a bright yellow square on a plain background."}

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):
        ctx, err = await client.analyze_image_structured(valid_img)
        assert err == ""
        assert ctx is not None
        assert "yellow square" in ctx.description
        assert ctx.uncertainty_rating in ["OBSERVED", "UNCERTAIN"]
