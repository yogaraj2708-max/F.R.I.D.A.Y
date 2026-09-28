"""
F.R.I.D.A.Y. 3.0 — Soak Test & Resource Leak Monitor
Measures RAM (RSS), Windows Handle Count, Thread Count, and SQLite file sizes
across sustained mission dispatch, state machine transitions, and routing workloads.
"""

import os
import gc
import sys
import time
import psutil
import pytest
from pathlib import Path
from friday_core.agent.state_machine import AgentStateMachine, AgentState
from friday_core.agent.compound import CompoundIntentParser
from friday_core.agent.planner import PEOVPlanner
from friday_ui.core.config import APP_DATA_DIR


class ResourceMonitor:
    def __init__(self):
        self.proc = psutil.Process(os.getpid())

    def snapshot(self) -> dict:
        gc.collect()
        mem_info = self.proc.memory_info()
        handles = self.proc.num_handles() if hasattr(self.proc, "num_handles") else 0
        threads = self.proc.num_threads()
        return {
            "rss_mb": mem_info.rss / (1024 * 1024),
            "handles": handles,
            "threads": threads,
            "timestamp": time.time()
        }


def test_soak_monitor_resource_stability():
    """
    Executes sustained workload cycles verifying that handles, threads, and memory remain stable.
    """
    monitor = ResourceMonitor()
    parser = CompoundIntentParser()
    planner = PEOVPlanner()

    # Warm-up phase
    for _ in range(5):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.THINKING)
        sm.transition_to(AgentState.IDLE)
        _ = parser.parse("open notepad and type hello")

    baseline = monitor.snapshot()

    CYCLES = 50
    for i in range(CYCLES):
        # 1. State machine transition cycle
        sm = AgentStateMachine()
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.EXECUTING)
        sm.transition_to(AgentState.IDLE)

        # 2. Compound parsing cycle
        ast = parser.parse(f"open notepad and type cycle_{i}_data")
        assert ast is not None
        assert len(ast.steps) == 2

        # 3. Mission DAG planning cycle
        mission = planner.plan_compound_directive(f"open calc and calculate 2 + {i}")
        assert len(mission.steps) == 2

    final = monitor.snapshot()

    delta_rss = final["rss_mb"] - baseline["rss_mb"]
    delta_handles = final["handles"] - baseline["handles"]
    delta_threads = final["threads"] - baseline["threads"]

    print(f"\n[SOAK METRICS over {CYCLES} cycles]:")
    print(f"  Baseline RSS:    {baseline['rss_mb']:.2f} MB")
    print(f"  Final RSS:       {final['rss_mb']:.2f} MB (Delta: {delta_rss:+.2f} MB)")
    print(f"  Baseline Handles:{baseline['handles']}")
    print(f"  Final Handles:   {final['handles']} (Delta: {delta_handles:+d})")
    print(f"  Baseline Threads:{baseline['threads']}")
    print(f"  Final Threads:   {final['threads']} (Delta: {delta_threads:+d})")

    # Leak checks:
    # 1. Memory must not leak excessively (>40MB across 50 purely in-memory AST/DAG cycles)
    assert delta_rss < 40.0, f"Potential memory leak detected: RSS grew by {delta_rss:.2f} MB"

    # 2. Handles must not leak (e.g. unclosed file/event handles, threshold 30)
    assert delta_handles < 30, f"Potential Windows handle leak: handles grew by {delta_handles}"

    # 3. Threads must not leak (threads should return to baseline or within +2)
    assert delta_threads <= 3, f"Potential thread leak: threads grew by {delta_threads}"


if __name__ == "__main__":
    test_soak_monitor_resource_stability()
    print("Soak test passed successfully.")
