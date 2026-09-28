import os, sys
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath("."))
from friday_ui.core.engine import FridayBrain, FridaySignals

class TestAgentToolsPlumbing:
    @pytest.mark.asyncio
    async def test_agent_tools_schema_definition(self):
        signals = FridaySignals()
        brain = FridayBrain(signals, None)
        tools = brain.get_agent_tools()
        assert len(tools) >= 3
        tool_names = [t["function"]["name"] for t in tools]
        assert "web_search" in tool_names
        assert "calculate" in tool_names
        assert "system_telemetry" in tool_names

    @pytest.mark.asyncio
    async def test_tool_dispatch_calculate(self):
        signals = FridaySignals()
        brain = FridayBrain(signals, None)
        res = await brain.dispatch_agent_tool("calculate", {"expression": "25 * 4"})
        assert "100" in res

    @pytest.mark.asyncio
    async def test_tool_dispatch_system_telemetry(self):
        signals = FridaySignals()
        brain = FridayBrain(signals, None)
        res = await brain.dispatch_agent_tool("system_telemetry", {})
        assert "CPU:" in res
        assert "RAM:" in res

    @pytest.mark.asyncio
    async def test_preflight_tool_execution_enriches_context(self):
        signals = FridaySignals()
        status_updates = []
        signals.status_updated.connect(lambda s: status_updates.append(s))
        brain = FridayBrain(signals, None)

        brain._tool_capability_cache[brain.model] = "VERIFIED"

        mock_preflight_response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "calculate",
                            "arguments": {"expression": "12 * 12"}
                        }
                    }
                ]
            }
        }

        mock_turn2_response = {
            "message": {
                "role": "assistant",
                "content": "The result is 144.",
                "tool_calls": None
            }
        }

        with patch.object(brain.client, "chat") as mock_chat:
            mock_chat.side_effect = [
                mock_preflight_response,  # First call (native tool decision)
                mock_turn2_response       # Second call (same model final answer with tool result)
            ]
            reply = await brain.query_llm("calculate 12 * 12", stream_to_ui=False, stream_to_speech=False)
            assert "144" in reply
            assert any("calculate" in s for s in status_updates)
