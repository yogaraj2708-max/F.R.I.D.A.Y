"""
Architecture Reconstruction & Call Site Inspector for Phase 1
Scans friday_ui and friday_core to map the complete execution pipeline.
"""

import sys
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def find_patterns():
    engine_file = BASE_DIR / "friday_ui" / "core" / "engine.py"
    with open(engine_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print("--- skill_registry.execute_skill call sites in engine.py ---")
    for i, line in enumerate(lines, 1):
        if "skill_registry.execute_skill" in line:
            print(f"Line {i}: {line.strip()}")

    print("\n--- Thread / Worker creation in friday_ui ---")
    ui_dir = BASE_DIR / "friday_ui"
    for py_file in ui_dir.rglob("*.py"):
        rel = py_file.relative_to(BASE_DIR)
        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if any(w in line for w in ["QThread", "threading.Thread", "asyncio.to_thread", "ThreadPoolExecutor"]):
                    if not line.strip().startswith("#"):
                        print(f"{rel}:{i} -> {line.strip()}")

    print("\n--- Registered Skills in friday_core/skills ---")
    from friday_core.skills.registry import skill_registry
    for name, skill in sorted(skill_registry._skills.items()):
        print(f"Skill: {name} | Class: {skill.__class__.__name__} | Preconditions: {getattr(skill, 'preconditions', [])}")

    print("\n--- Agent Tool Bridge Tools ---")
    from friday_core.skills.agent_bridge import agent_tool_bridge
    for t in agent_tool_bridge.get_tool_schemas():
        fn = t.get("function", {})
        print(f"Agent Tool: {fn.get('name')} | Description: {fn.get('description')[:50]}...")

if __name__ == "__main__":
    find_patterns()
