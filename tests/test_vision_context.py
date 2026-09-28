"""
F.R.I.D.A.Y. 3.0 — Structured Image Context, Multi-Image Isolation & Memory Budget Test Battery
Validates ImageContext schema, omission of raw base64 in prompts, multi-image disambiguation,
session isolation, and FIFO context budgeting.
"""

import pytest
from friday_core.vision.image_context import ImageContext, ImageContextManager


@pytest.fixture
def context_manager():
    return ImageContextManager()


def test_image_context_complete_schema():
    ctx = ImageContext(
        image_id="img_001",
        description="Network diagram",
        objects=["Router", "Firewall", "Switch"],
        visible_text=["192.168.1.1", "WAN", "LAN"],
        scene="Architecture diagram",
        actions_or_events=["Traffic forwarding"],
        important_details=["Firewall is active"],
        source_model="qwen2.5vl:3b",
        session_id="session_test",
        image_name="network.png",
        image_path="/path/to/network.png",
        dimensions=(1920, 1080),
        format="PNG",
        preprocessing={"downscaled": False},
        uncertainty_rating="OBSERVED",
        execution_status="SUCCESS",
        verification_status="VERIFIED"
    )

    data = ctx.to_dict()
    assert data["dimensions"] == [1920, 1080]
    assert data["uncertainty_rating"] == "OBSERVED"
    assert data["verification_status"] == "VERIFIED"

    restored = ImageContext.from_dict(data)
    assert restored.dimensions == (1920, 1080)
    assert restored.image_id == "img_001"


def test_no_raw_base64_in_prompt_context():
    """Verify that to_prompt_context never dumps raw pixel base64 into prompt history."""
    ctx = ImageContext(
        image_id="img_002",
        description="A clear invoice receipt",
        visible_text=["Total: $42.00"],
        raw_analysis='{"description": "A clear invoice receipt"}',
        dimensions=(800, 600),
        format="JPEG"
    )

    prompt_ctx = ctx.to_prompt_context()
    assert "data:image" not in prompt_ctx
    assert "base64" not in prompt_ctx
    assert "Total: $42.00" in prompt_ctx
    assert "Dimensions: 800x600 | Format: JPEG" in prompt_ctx


def test_multi_image_isolation(context_manager):
    """
    MISSION 4: Multiple images attached (Image A, Image B, Image C).
    Verify that queries targeting Image B resolve ONLY Image B evidence.
    """
    sid = "multi_img_session"
    ctx_a = ImageContext(
        image_id="img_A",
        description="Image A: Red triangle",
        objects=["Red triangle"],
        image_name="triangle.png",
        session_id=sid
    )
    ctx_b = ImageContext(
        image_id="img_B",
        description="Image B: Green hexagon",
        objects=["Green hexagon"],
        image_name="hexagon.png",
        session_id=sid
    )
    ctx_c = ImageContext(
        image_id="img_C",
        description="Image C: Blue circle",
        objects=["Blue circle"],
        image_name="circle.png",
        session_id=sid
    )

    context_manager.store_context(ctx_a)
    context_manager.store_context(ctx_b)
    context_manager.store_context(ctx_c)

    # 1. Resolve specifically Image B
    resolved_b1 = context_manager.resolve_image_reference("What shape is in image B?", sid)
    assert resolved_b1 is not None
    assert resolved_b1.image_id == "img_B"
    assert "Green hexagon" in resolved_b1.objects

    resolved_b2 = context_manager.resolve_image_reference("Describe the second image", sid)
    assert resolved_b2 is not None
    assert resolved_b2.image_id == "img_B"

    resolved_b3 = context_manager.resolve_image_reference("What is in hexagon.png?", sid)
    assert resolved_b3 is not None
    assert resolved_b3.image_id == "img_B"

    # Contexts must not cross-contaminate
    assert "Red triangle" not in resolved_b1.objects
    assert "Blue circle" not in resolved_b1.objects


def test_session_isolation(context_manager):
    """Verify that Session A cannot access or resolve Session B images."""
    sid_a = "session_alpha"
    sid_b = "session_beta"

    context_manager.store_context(ImageContext(
        image_id="img_secret",
        description="Confidential blueprints",
        session_id=sid_a
    ))

    # Session B should have zero contexts
    assert len(context_manager.get_all_contexts(sid_b)) == 0
    assert context_manager.resolve_image_reference("blueprints", sid_b) is None
    assert context_manager.get_context("img_secret", sid_b) is None


def test_context_budget_fifo_eviction(context_manager):
    """Verify that exceeding MAX_CONTEXTS_PER_SESSION evicts the oldest context."""
    sid = "budget_session"
    max_limit = context_manager.MAX_CONTEXTS_PER_SESSION

    # Store max_limit + 5 contexts
    for i in range(max_limit + 5):
        context_manager.store_context(ImageContext(
            image_id=f"img_{i:03d}",
            description=f"Snapshot {i}",
            session_id=sid
        ))

    stored = context_manager.get_all_contexts(sid)
    assert len(stored) == max_limit
    # Oldest (0, 1, 2, 3, 4) must have been evicted
    assert stored[0].image_id == "img_005"
    assert stored[-1].image_id == f"img_{max_limit + 4:03d}"
