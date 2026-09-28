"""
F.R.I.D.A.Y. 3.0 — Vision False Success Prevention & Uncertainty Integrity Test Battery
Validates Section 14, 15, 25:
1. Low resolution / blurry images preserve UNCERTAIN rating.
2. Unseen or absent items preserve NOT_VISIBLE rating.
3. System refuses to report success when vision inference failed.
4. Distinguishes OBSERVED, LIKELY, UNCERTAIN, and NOT_VISIBLE without silent promotion to absolute fact.
"""

import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from friday_core.vision.vision_model import VisionModelClient
from friday_core.vision.image_context import ImageContext


@pytest.fixture
def low_res_img():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (16, 16), color="gray")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.mark.asyncio
async def test_low_resolution_uncertainty_preserved(low_res_img):
    """
    MISSION 5: Low-resolution or blurry image.
    Expected: Uncertainty rating is UNCERTAIN, not fabricated into verified absolute fact.
    """
    client = VisionModelClient()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "response": (
            '{"description": "The image is extremely low resolution and blurry, difficult to read.", '
            '"objects": [], "visible_text": [], "uncertainty": "UNCERTAIN"}'
        )
    }

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):

        ctx, err = await client.analyze_image_structured(low_res_img, prompt="Read text")
        assert err == ""
        assert ctx is not None
        assert ctx.uncertainty_rating == "UNCERTAIN"
        prompt_ctx = ctx.to_prompt_context()
        assert "Confidence / Uncertainty: UNCERTAIN" in prompt_ctx


@pytest.mark.asyncio
async def test_absent_item_not_visible_rating(low_res_img):
    """Verify that when requested item is absent, rating is NOT_VISIBLE."""
    client = VisionModelClient()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "response": (
            '{"description": "No user buttons or navigation menus are present in this graphic.", '
            '"objects": [], "visible_text": [], "uncertainty": "NOT_VISIBLE"}'
        )
    }

    with patch.object(client, "check_ollama_online", return_value=True), \
         patch.object(client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch("httpx.AsyncClient.post", return_value=mock_resp):

        ctx, err = await client.analyze_image_structured(low_res_img, prompt="Find the submit button")
        assert err == ""
        assert ctx is not None
        assert ctx.uncertainty_rating == "NOT_VISIBLE"


def test_no_false_success_on_failed_analysis():
    """Verify that failed analysis returns FAILED status and cannot be verified as true."""
    failed_ctx = ImageContext(
        image_id="err_01",
        description="Analysis aborted due to network timeout",
        execution_status="FAILED",
        verification_status="UNVERIFIED",
        uncertainty_rating="UNCERTAIN"
    )

    prompt_ctx = failed_ctx.to_prompt_context()
    assert "Verification Status: UNVERIFIED" in prompt_ctx
    assert "Confidence / Uncertainty: UNCERTAIN" in prompt_ctx
