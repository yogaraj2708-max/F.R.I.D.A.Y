"""
F.R.I.D.A.Y. 3.0 — Vision Model Dynamic Resolution & Capability Probe Test Battery
Validates dynamic model resolution from settings, prevention of silent model fallback,
and live capability probing.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from friday_core.vision.vision_model import VisionModelClient


@pytest.fixture
def vision_client():
    return VisionModelClient()


@pytest.mark.asyncio
async def test_dynamic_model_resolution_from_settings(vision_client):
    mock_tags = {
        "models": [
            {"name": "llama3.2-vision:latest"},
            {"name": "qwen2.5-coder:latest"}
        ]
    }
    with patch("friday_core.settings.settings.get", return_value="llama3.2-vision:latest"), \
         patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=200, json=lambda: mock_tags)):
        resolved = await vision_client.get_available_vision_model()
        assert resolved == "llama3.2-vision:latest"


@pytest.mark.asyncio
async def test_dynamic_fallback_through_preferred_list(vision_client):
    mock_tags = {
        "models": [
            {"name": "llava:7b"},
            {"name": "qwen2.5-coder:latest"}
        ]
    }
    # No configured model, searches preferred list
    with patch("friday_core.settings.settings.get", return_value=None), \
         patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=200, json=lambda: mock_tags)):
        resolved = await vision_client.get_available_vision_model()
        assert resolved == "llava:7b"


@pytest.mark.asyncio
async def test_no_silent_fallback_when_model_missing(vision_client):
    # Only text models installed, no vision models
    mock_tags = {
        "models": [
            {"name": "qwen2.5:0.5b"},
            {"name": "deepseek-r1:8b"}
        ]
    }
    with patch("friday_core.settings.settings.get", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=200, json=lambda: mock_tags)):
        resolved = await vision_client.get_available_vision_model()
        # Must return None, NOT silently substitute another model!
        assert resolved is None


@pytest.mark.asyncio
async def test_vision_status_reporting(vision_client):
    # Case 1: Offline
    with patch.object(vision_client, "check_ollama_online", return_value=False):
        status = await vision_client.get_vision_status()
        assert status["CAPABILITY_STATUS"] == "OFFLINE"
        assert status["PROVIDER"] == "Ollama"

    # Case 2: Online but Unavailable
    with patch.object(vision_client, "check_ollama_online", return_value=True), \
         patch.object(vision_client, "get_available_vision_model", return_value=None):
        status = await vision_client.get_vision_status()
        assert status["CAPABILITY_STATUS"] == "UNAVAILABLE"
        assert status["AVAILABLE_MODEL"] is None

    # Case 3: Ready
    with patch.object(vision_client, "check_ollama_online", return_value=True), \
         patch.object(vision_client, "get_available_vision_model", return_value="qwen2.5vl:3b"):
        status = await vision_client.get_vision_status()
        assert status["CAPABILITY_STATUS"] == "READY"
        assert status["AVAILABLE_MODEL"] == "qwen2.5vl:3b"


@pytest.mark.asyncio
async def test_probe_vision_capability_ready(vision_client):
    mock_gen_resp = MagicMock(status_code=200)
    mock_gen_resp.json.return_value = {"response": '{"status": "READY", "description": "white pixel"}'}

    with patch.object(vision_client, "check_ollama_online", return_value=True), \
         patch.object(vision_client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_gen_resp):
        probe = await vision_client.probe_vision_capability()
        assert probe["status"] == "READY"
        assert probe["model"] == "qwen2.5vl:3b"
        assert probe["error"] is None
        assert probe["latency_ms"] >= 0
        assert probe["total_response_chars"] > 0


@pytest.mark.asyncio
async def test_probe_vision_capability_unavailable(vision_client):
    with patch.object(vision_client, "check_ollama_online", return_value=True), \
         patch.object(vision_client, "get_available_vision_model", return_value=None):
        probe = await vision_client.probe_vision_capability()
        assert probe["status"] == "UNAVAILABLE"
        assert "unavailable" in probe["error"]
