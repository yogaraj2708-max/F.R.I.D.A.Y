"""
F.R.I.D.A.Y. 3.0 — Comprehensive Vision Architecture Test Battery
Validates specialist vision model (qwen2.5vl:3b) integration, structured ImageContext,
handoff to main conversational model, follow-up memory, and failure resilience.
"""

import asyncio
import base64
import io
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image, ImageDraw

from friday_core.vision.image_context import ImageContext, ImageContextManager
from friday_core.vision.vision_model import VisionModelClient, DEFAULT_VISION_MODEL


@pytest.fixture
def temp_image_file():
    """Creates a temporary valid PNG image file with known visual elements."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (320, 160), color=(230, 240, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([(20, 20), (300, 50)], fill=(30, 60, 120))
        d.text((30, 28), "FRIDAY SYSTEM DIAGNOSTICS", fill=(255, 255, 255))
        d.rectangle([(20, 70), (140, 110)], fill=(40, 180, 90))
        d.text((40, 85), "ONLINE", fill=(255, 255, 255))
        d.rectangle([(160, 70), (280, 110)], fill=(220, 50, 50))
        d.text((180, 85), "ALERT", fill=(255, 255, 255))
        img.save(tf, format="PNG")
        tf_path = tf.name

    yield tf_path

    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def empty_image_file():
    """Creates an empty 0-byte file."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def corrupted_image_file():
    """Creates a corrupted non-image file with .png extension."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf.write(b"NOT_A_REAL_IMAGE_DATA_CORRUPTED_STREAM")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


# =========================================================================
# 1. ImageContext & Data Schema Tests
# =========================================================================

def test_image_context_dataclass():
    ctx = ImageContext(
        image_id="image_context_001",
        description="Settings dashboard showing system diagnostics",
        objects=["Header banner", "ONLINE button", "ALERT button"],
        visible_text=["FRIDAY SYSTEM DIAGNOSTICS", "ONLINE", "ALERT"],
        scene="Desktop Application Window",
        actions_or_events=["Toggle Online", "Dismiss Alert"],
        important_details=["Primary theme blue and white", "Status is active"],
        source_model="qwen2.5vl:3b",
        session_id="session_alpha",
        image_name="diagnostics.png"
    )

    d = ctx.to_dict()
    assert d["type"] == "image_context"
    assert d["image_id"] == "image_context_001"
    assert d["source_model"] == "qwen2.5vl:3b"
    assert len(d["visible_text"]) == 3
    assert len(d["objects"]) == 3

    # Reconstitution from dict
    restored = ImageContext.from_dict(d)
    assert restored.image_id == ctx.image_id
    assert restored.visible_text == ctx.visible_text

    # Prompt context serialization
    prompt_ctx = ctx.to_prompt_context()
    assert "[VERIFIED IMAGE CONTEXT: image_context_001]" in prompt_ctx
    assert "FRIDAY SYSTEM DIAGNOSTICS" in prompt_ctx
    assert "ONLINE button" in prompt_ctx
    assert "qwen2.5vl:3b" in prompt_ctx


# =========================================================================
# 2. ImageContextManager & Multi-Image / Session Isolation Tests
# =========================================================================

def test_context_manager_indexing_and_resolution():
    mgr = ImageContextManager()
    sid = "session_test_01"

    # Store first image
    ctx1 = ImageContext(
        image_id="image_context_001",
        description="First screenshot of login page",
        objects=["Username field", "Password field", "Login button"],
        visible_text=["Welcome Back", "Sign In"],
        session_id=sid,
        image_name="login_screen.png"
    )
    mgr.store_context(ctx1)

    # Store second image
    ctx2 = ImageContext(
        image_id="image_context_002",
        description="Second screenshot of user profile",
        objects=["Avatar", "Email address", "Edit Profile button"],
        visible_text=["Tony Stark", "stark@avengers.org"],
        session_id=sid,
        image_name="profile_screen.png"
    )
    mgr.store_context(ctx2)

    # 1. Positional reference: first image
    res_first = mgr.resolve_image_reference("What is in the first image?", sid)
    assert res_first is not None
    assert res_first.image_id == "image_context_001"
    assert "login" in res_first.description.lower()

    # 2. Positional reference: second image
    res_second = mgr.resolve_image_reference("What text is in the second screenshot?", sid)
    assert res_second is not None
    assert res_second.image_id == "image_context_002"
    assert "stark@avengers.org" in res_second.visible_text

    # 3. Filename reference
    res_by_name = mgr.resolve_image_reference("Tell me about login_screen.png", sid)
    assert res_by_name is not None
    assert res_by_name.image_id == "image_context_001"

    # 4. Relative reference: previous / last image
    res_last = mgr.resolve_image_reference("What was on the previous image?", sid)
    assert res_last is not None
    assert res_last.image_id == "image_context_002"


def test_session_isolation_no_leak():
    mgr = ImageContextManager()
    sid_a = "session_alpha"
    sid_b = "session_beta"

    ctx_a = ImageContext(
        image_id="image_context_001",
        description="Confidential Architecture Diagram",
        session_id=sid_a,
        image_name="secret_arch.png"
    )
    mgr.store_context(ctx_a)

    # Session B should have zero contexts
    assert len(mgr.get_all_contexts(sid_b)) == 0
    assert mgr.resolve_image_reference("What was in the image?", sid_b) is None

    # Clearing session A
    mgr.clear_session(sid_a)
    assert len(mgr.get_all_contexts(sid_a)) == 0


# =========================================================================
# 3. Intent Detection Tests (Rule Compliance)
# =========================================================================

def test_vision_intent_rules():
    # Rule: Normal chat without image MUST NOT invoke vision
    assert not ImageContextManager.requires_visual_analysis("describe this image", has_attached_image=False)
    assert not ImageContextManager.requires_visual_analysis("hi", has_attached_image=False)
    assert not ImageContextManager.requires_visual_analysis("open notepad", has_attached_image=False)

    # Rule: Image attached + visual directive -> TRUE
    assert ImageContextManager.requires_visual_analysis("describe this image", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("what's in this image", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("what do you see", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("analyze this image", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("read the text in this image", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("what app is this", has_attached_image=True)
    assert ImageContextManager.requires_visual_analysis("what is this?", has_attached_image=True)

    # Rule: Image attached + casual non-visual message -> FALSE
    assert not ImageContextManager.requires_visual_analysis("hello", has_attached_image=True)
    assert not ImageContextManager.requires_visual_analysis("hi", has_attached_image=True)
    assert not ImageContextManager.requires_visual_analysis("good morning", has_attached_image=True)
    assert not ImageContextManager.requires_visual_analysis("what time is it", has_attached_image=True)
    assert not ImageContextManager.requires_visual_analysis("open notepad", has_attached_image=True)


def test_reanalysis_and_followup_detection():
    # Re-analysis trigger
    assert ImageContextManager.is_reanalysis_request("Analyze the image again and look specifically at the top-right corner.")
    assert ImageContextManager.is_reanalysis_request("look closer at the error dialog")
    assert ImageContextManager.is_reanalysis_request("zoom in on the bottom")
    assert not ImageContextManager.is_reanalysis_request("What is the weather today?")

    # Follow-up triggers
    assert ImageContextManager.is_followup_visual_question("What app was visible in the image?")
    assert ImageContextManager.is_followup_visual_question("What is on the left side?")
    assert ImageContextManager.is_followup_visual_question("Read the text near the top.")
    assert ImageContextManager.is_followup_visual_question("What color is the button?")
    assert ImageContextManager.is_followup_visual_question("Does the screenshot show an error?")
    assert ImageContextManager.is_followup_visual_question("What text did you notice in it?")


# =========================================================================
# 4. Image Validation & Error Handling Tests
# =========================================================================

def test_image_validation_empty_file(empty_image_file):
    client = VisionModelClient()
    b64, err = client.validate_and_encode_image(empty_image_file)
    assert b64 is None
    assert "empty (0 bytes)" in err


def test_image_validation_corrupted_file(corrupted_image_file):
    client = VisionModelClient()
    b64, err = client.validate_and_encode_image(corrupted_image_file)
    assert b64 is None
    assert "Invalid or malformed image data" in err


def test_image_validation_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        tf.write(b"Just text")
        tf_path = tf.name
    try:
        client = VisionModelClient()
        b64, err = client.validate_and_encode_image(tf_path)
        assert b64 is None
        assert "Unsupported image format" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_image_validation_valid(temp_image_file):
    client = VisionModelClient()
    b64, err = client.validate_and_encode_image(temp_image_file)
    assert err is None
    assert b64 is not None
    assert len(b64) > 100


# =========================================================================
# 5. Vision Client Mocked Fault Injection Tests
# =========================================================================

@pytest.mark.asyncio
async def test_ollama_offline_handling(temp_image_file):
    client = VisionModelClient(ollama_host="http://localhost:99999")  # Nonexistent port
    ctx, err = await client.analyze_image_structured(temp_image_file, prompt="Describe")
    assert ctx is None
    assert "Ollama service is offline or unreachable" in err


@pytest.mark.asyncio
async def test_vision_model_unavailable(temp_image_file):
    client = VisionModelClient()
    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value=None):
        ctx, err = await client.analyze_image_structured(temp_image_file, prompt="Describe")
        assert ctx is None
        assert "is not available in Ollama" in err


@pytest.mark.asyncio
async def test_vision_timeout_handling(temp_image_file):
    import httpx
    client = VisionModelClient()
    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
        ctx, err = await client.analyze_image_structured(temp_image_file, prompt="Describe")
        assert ctx is None
        assert "timed out" in err


@pytest.mark.asyncio
async def test_malformed_json_fallback_handling(temp_image_file):
    client = VisionModelClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": "Here is an unformatted description of the image with text and buttons."
    }

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):
        ctx, err = await client.analyze_image_structured(temp_image_file, prompt="Describe")
        assert err == ""
        assert ctx is not None
        assert "Here is an unformatted description" in ctx.description
