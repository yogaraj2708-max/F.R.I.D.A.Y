"""
REGRESSION TEST: BUG-013 (CPU Telemetry Intent Mismatch)
Root Cause: telemetry.py lacked CPU/process enumeration; semantic router collapsed
all telemetry queries into battery + RAM.
Fix Verification:
1. 'what is using the most CPU right now?' returns top CPU process (name, PID, cpu %) and overall CPU %.
2. Must NOT return battery / RAM status.
3. Telemetry API returns verifiable process metrics.
"""

import pytest
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.system.telemetry import get_top_cpu_processes, get_cpu_info


def test_telemetry_get_top_cpu_processes_runtime():
    """Verify live system process enumeration returns real running processes."""
    top_procs = get_top_cpu_processes(limit=5)
    assert isinstance(top_procs, list)
    assert len(top_procs) > 0

    leader = top_procs[0]
    assert "name" in leader
    assert "pid" in leader
    assert "cpu_percent" in leader
    assert isinstance(leader["pid"], int)
    assert leader["pid"] > 0
    assert leader["name"] != "Unknown"


def test_telemetry_get_cpu_info_runtime():
    """Verify system CPU info returns valid percentage, core count, and frequency."""
    cpu_info = get_cpu_info()
    assert isinstance(cpu_info, dict)
    assert "percent" in cpu_info
    assert "cores" in cpu_info
    assert cpu_info["cores"] >= 1
    assert 0.0 <= cpu_info["percent"] <= 100.0


@pytest.mark.asyncio
async def test_top_cpu_intent_routing_and_response():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    queries = [
        "what is using the most CPU right now?",
        "which app is using the most cpu",
        "top cpu process"
    ]

    for q in queries:
        response = await brain.execute_smart_skill(q)
        assert response is not None
        # Must report CPU process telemetry
        assert "CPU" in response or "cpu" in response
        assert "PID" in response
        assert "%" in response
        # Must NOT be a battery or RAM response
        assert "Battery is holding" not in response
        assert "System memory load" not in response
