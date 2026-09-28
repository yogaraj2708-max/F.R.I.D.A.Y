"""
F.R.I.D.A.Y. 3.0 — Native Tool Flow & Main Agent Authority Test Battery
Validates that:
1. An attached image with casual text ("Hi") produces ZERO vision tool calls.
2. A visual question ("Describe this image") results in the Main Agent model
   natively emitting an 'analyze_image' tool call.
3. The specialist vision model does NOT become the main conversational model.
4. Tool dispatch cleanly executes and returns verified structured results.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from PIL import Image

from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.vision.image_context import ImageContext


@pytest.fixture
def temp_image():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def brain():
    signals = FridaySignals()
    tts = MagicMock()
    tts.cancel_event = MagicMock()
    tts.cancel_event.is_set.return_value = False
    tts.speak = AsyncMock()
    b = FridayBrain(signals=signals, tts_engine=tts)
    b._tool_capability_cache[b.model] = "VERIFIED"
    return b


@pytest.mark.asyncio
async def test_image_attached_with_greeting_zero_vision_calls(brain, temp_image):
    """
    MISSION 1: Image attached + 'Hi'.
    Mandatory rule: Zero vision calls. Attachment presence must NOT force image analysis.
    """
    mock_client = AsyncMock()
    brain.client = mock_client
    brain.vision_client = MagicMock()
    brain.vision_client.analyze_image_structured = AsyncMock()

    # The prompt as constructed when user attaches image and types "Hi"
    user_prompt = f"[Attached Image: test.png | Path: {temp_image}]\n\nBoss Directive:\nHi"

    resp_conv = MagicMock()
    resp_conv.message = MagicMock()
    resp_conv.message.content = "Hello Boss! How can I assist you today?"
    resp_conv.message.tool_calls = None
    mock_client.chat.return_value = resp_conv

    res = await brain.query_llm(user_prompt, stream_to_ui=False, stream_to_speech=False, save_history=False)
    # Vision client must NOT be called
    brain.vision_client.analyze_image_structured.assert_not_called()
    assert "Hello Boss" in res


@pytest.mark.asyncio
async def test_image_attached_with_visual_question_calls_native_tool(brain, temp_image):
    """
    MISSION 2: Image attached + 'Describe this image'.
    Expected:
    1. Main agent model emits tool call 'analyze_image'.
    2. Engine executes analyze_image via vision specialist.
    3. Structured result is returned to the SAME Main Agent model.
    4. Main Agent produces the final answer.
    """
    mock_client = AsyncMock()
    brain.client = mock_client

    # Turn 1: Main agent decides to call analyze_image
    tc_mock = MagicMock()
    tc_mock.id = "call_vis_001"
    tc_mock.function = MagicMock()
    tc_mock.function.name = "analyze_image"
    tc_mock.function.arguments = {"image_path": temp_image, "question": "Describe this image"}

    first_turn_msg = MagicMock()
    first_turn_msg.message = MagicMock()
    first_turn_msg.message.content = ""
    first_turn_msg.message.tool_calls = [tc_mock]

    # Turn 2: Same main agent synthesizes answer after receiving tool result
    second_turn_msg = MagicMock()
    second_turn_msg.message = MagicMock()
    second_turn_msg.message.content = "Boss, the image is a solid blue square."
    second_turn_msg.message.tool_calls = None

    mock_client.chat.side_effect = [first_turn_msg, second_turn_msg]

    mock_ctx = ImageContext(
        image_id="img_ctx_001",
        description="A solid blue image 100x100 pixels",
        objects=["blue square"],
        source_model="qwen2.5vl:3b",
        dimensions=(100, 100),
        format="PNG"
    )

    with patch.object(brain.vision_client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch.object(brain.vision_client, "analyze_image_structured", return_value=(mock_ctx, "")):

        user_prompt = f"[Attached Image: test.png | Path: {temp_image}]\n\nBoss Directive:\nDescribe this image."
        answer = await brain.query_llm(user_prompt, stream_to_ui=False, stream_to_speech=False, save_history=False)

        # Verified flow assertions:
        # 1. Main model was called twice (tool call turn + synthesis turn)
        assert mock_client.chat.call_count == 2
        # 2. Vision specialist was called once with image_path
        brain.vision_client.analyze_image_structured.assert_called_once()
        # 3. Main agent synthesized the final answer
        assert "solid blue square" in answer


@pytest.mark.asyncio
async def test_dispatch_agent_tool_analyze_image(brain, temp_image):
    """Verifies that dispatch_agent_tool directly validates and executes analyze_image."""
    mock_ctx = ImageContext(
        image_id="img_ctx_002",
        description="UI test diagram",
        visible_text=["Submit", "Cancel"],
        objects=["Button A", "Button B"],
        dimensions=(100, 100),
        format="PNG",
        source_model="qwen2.5vl:3b"
    )

    with patch.object(brain.vision_client, "get_available_vision_model", return_value="qwen2.5vl:3b"), \
         patch.object(brain.vision_client, "analyze_image_structured", return_value=(mock_ctx, "")):

        tool_out = await brain.dispatch_agent_tool("analyze_image", {
            "image_path": temp_image,
            "question": "What buttons are shown?"
        })

        assert "<<<EXTERNAL_IMAGE_DATA_NOT_SYSTEM_INSTRUCTIONS>>>" in tool_out
        assert "img_ctx_002" in tool_out
        assert "Submit" in tool_out
        assert "<<<END_EXTERNAL_IMAGE_DATA>>>" in tool_out
