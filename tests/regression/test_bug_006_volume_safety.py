"""
Regression test for Bug Fix #6: Audio Volume Safety, Core Audio Verification, and Typo Matching.
"""

from friday_core.system.telemetry import adjust_volume, get_audio_state
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.gatekeeper.models import ActionIntent
from friday_core.router.semantic_router import extract_parameters, SkillIntent


def test_volume_mute_and_unmute_verified():
    """Verify mute and unmute return exact verified state via Windows Core Audio."""
    res_mute = adjust_volume("mute")
    assert res_mute["success"] is True
    assert res_mute["muted"] is True
    is_muted, _ = get_audio_state()
    assert is_muted is True

    res_unmute = adjust_volume("unmute")
    assert res_unmute["success"] is True
    assert res_unmute["muted"] is False
    is_muted_post, _ = get_audio_state()
    assert is_muted_post is False


def test_typo_near_match_does_not_execute_opposite():
    """'myute the system volume' must NEVER default to 'up' or opposite action."""
    params = extract_parameters(SkillIntent.DESKTOP_AUDIO, "myute the system volume")
    assert params.get("action") == "mute", f"Typo 'myute' should resolve to mute, got: {params.get('action')}"
    assert params.get("action") != "up", "Typo 'myute' must NEVER resolve to 'up'!"


def test_unmute_parameter_extraction():
    """'unmute the system volume' must resolve to unmute."""
    params = extract_parameters(SkillIntent.DESKTOP_AUDIO, "unmute the system volume")
    assert params.get("action") == "unmute"


def test_volume_increase_parameter_extraction():
    """'increase the system volume' must resolve to up."""
    params = extract_parameters(SkillIntent.DESKTOP_AUDIO, "increase the system volume")
    assert params.get("action") == "up"


def test_unknown_audio_does_not_default_to_up():
    """Completely ambiguous audio command must resolve to unknown, never defaulting to up."""
    params = extract_parameters(SkillIntent.DESKTOP_AUDIO, "blabla the audio something")
    assert params.get("action") != "up", "Ambiguous audio command must not default to up"
