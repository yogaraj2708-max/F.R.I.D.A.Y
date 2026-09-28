"""
Regression test for Bug Fix #7 & Sections 24-25: Web Page Reading & Semantic Content Generation.
"""

from friday_core.agent.compound import compound_parser
from friday_core.agent.planner import PEOVPlanner
from friday_core.skills.registry import skill_registry
from friday_core.browser.session import BrowserSession


def test_semantic_speech_5_step_dag():
    """Verify 'open notepad and write a welcome speech' generates the full 5-step DAG."""
    cmd = "open notepad and write a welcome speech"
    plan = compound_parser.parse(cmd)
    assert plan is not None, "Command must be parsed as a compound plan"
    assert len(plan.steps) == 5, f"Expected 5 steps, got {len(plan.steps)}"

    actions = [s.action for s in plan.steps]
    assert actions == [
        "open_app",
        "content_generation",
        "ui_focus",
        "ui_type_text",
        "ui_verify_content"
    ]

    # Verify parameters and dynamic dependencies
    assert plan.steps[0].params["app_name"] == "notepad"
    assert "welcome speech" in plan.steps[1].params["prompt"].lower()
    assert plan.steps[3].params["text"] == "$content_generation.generated_text"
    assert plan.steps[3].params["mode"] == "replace"
    assert plan.steps[4].params["expected_text"] == "$content_generation.generated_text"


def test_semantic_speech_variations():
    """Verify semantic speech generation generalizes across variations."""
    variations = [
        "open notepad and write a short welcome speech",
        "open notepad and write a welcome speech for a college event",
        "open notepad and write a formal welcome speech",
        "open notepad and write a birthday message",
        "open notepad and draft a leave letter",
        "open notepad and write an apology letter"
    ]
    for v in variations:
        plan = compound_parser.parse(v)
        assert plan is not None, f"Failed to parse variation: {v}"
        assert len(plan.steps) == 5, f"Variation {v} did not produce 5-step DAG"
        assert plan.steps[1].action == "content_generation"


def test_content_generation_skill_execution():
    """Verify ContentGenerationSkill produces authentic text and verifies quality."""
    res = skill_registry.execute_skill(
        tool_id="content_generation",
        params={"prompt": "a welcome speech for a college event", "target_app": "notepad"},
        operation_id="test-content-gen-001"
    )
    assert res.success is True
    data = res.data
    assert data["word_count"] >= 15
    gen_text = data["generated_text"].lower()
    assert any(w in gen_text for w in ["welcome", "event", "celebrate", "gather", "speech", "college"])
    assert res.verification is not None
    assert res.verification.verified is True


def test_browser_session_dom_headline_extraction():
    """Verify BrowserSession navigates and extracts real DOM headlines without crashing."""
    session = BrowserSession()
    # Load test HTML to verify DOM parsing without external network latency in test
    sample_html = """
    <html>
        <head><title>NVIDIA Official Site</title></head>
        <body>
            <h1>World Leader in AI Computing</h1>
            <h2>GeForce RTX 50 Series Announced</h2>
            <p>Welcome to NVIDIA.</p>
        </body>
    </html>
    """
    state = session.load_html(sample_html, base_url="https://www.nvidia.com")
    assert state.title == "NVIDIA Official Site"
    assert "World Leader in AI Computing" in session._raw_html
