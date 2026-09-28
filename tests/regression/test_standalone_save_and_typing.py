import os
import re
import pytest
from unittest.mock import MagicMock, patch

from friday_ui.core.engine import FridayBrain
from friday_core.skills.registry import skill_registry


@pytest.mark.asyncio
async def test_standalone_typing_fast_path():
    """Verifies that standalone typing commands execute through the elevated fast-path with correct mode."""
    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()

    # Test 1: Standard type
    with patch.object(skill_registry, "execute_skill") as mock_exec:
        mock_exec.return_value = MagicMock(success=True, data={}, error=None)
        res = await engine.execute_smart_skill("type Hello World into notepad")
        assert res is not None
        assert "Typed 'Hello World' into Notepad" in res
        mock_exec.assert_called_once()
        call_params = mock_exec.call_args[1]["params"]
        assert call_params["text"] == "Hello World"
        assert call_params["app_name"] == "notepad"
        assert call_params["mode"] == "type"

    # Test 2: Append mode
    with patch.object(skill_registry, "execute_skill") as mock_exec:
        mock_exec.return_value = MagicMock(success=True, data={}, error=None)
        res = await engine.execute_smart_skill("append additional notes at the end")
        assert res is not None
        call_params = mock_exec.call_args[1]["params"]
        assert call_params["mode"] == "append"

    # Test 3: Replace mode
    with patch.object(skill_registry, "execute_skill") as mock_exec:
        mock_exec.return_value = MagicMock(success=True, data={}, error=None)
        res = await engine.execute_smart_skill("replace content with New Text")
        assert res is not None
        call_params = mock_exec.call_args[1]["params"]
        assert call_params["mode"] == "replace"


@pytest.mark.asyncio
async def test_standalone_save_fast_path():
    """Verifies that standalone file save commands cleanly extract filenames and execute SaveFileSkill."""
    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()

    test_cases = [
        ("save as output_data.txt", "output_data.txt"),
        ("please save the file as 'report.md'", "report.md"),
        ("can you save this document as final_version.py", "final_version.py"),
        ("save backup_notes.txt", "backup_notes.txt")
    ]

    for cmd, expected_filename in test_cases:
        with patch.object(skill_registry, "execute_skill") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=True,
                data={"saved_path": f"C:\\Users\\Admin\\Desktop\\{expected_filename}"},
                error=None
            )
            res = await engine.execute_smart_skill(cmd)
            assert res is not None, f"Command '{cmd}' failed to match fast-path"
            assert expected_filename in res, f"Expected '{expected_filename}' in response '{res}'"
            mock_exec.assert_called_once()
            call_params = mock_exec.call_args[1]["params"]
            assert call_params["filename"] == expected_filename, (
                f"Extracted '{call_params['filename']}' instead of '{expected_filename}'"
            )


@pytest.mark.asyncio
async def test_elevated_close_app_polite_prefixes():
    """Verifies that polite prefixes ('please close', 'can you close', 'could you quit') are matched in fast-path."""
    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()

    polite_commands = [
        ("please close notepad", "notepad"),
        ("can you close the calculator app", "calculator"),
        ("could you quit notepad", "notepad"),
        ("close word window", "word")
    ]

    from friday_core.gatekeeper.gatekeeper import gatekeeper

    for cmd, expected_app in polite_commands:
        with patch.object(gatekeeper, "execute_action") as mock_gate:
            mock_gate.return_value = MagicMock(success=True, message=f"Application '{expected_app}' terminated")
            res = await engine.execute_smart_skill(cmd)
            assert res is not None, f"Command '{cmd}' failed to match close_app fast-path"
            assert "terminated" in res.lower()
            mock_gate.assert_called_once()
            intent = mock_gate.call_args[0][0]
            assert intent.action == "close_app"
            assert intent.target.lower() == expected_app
