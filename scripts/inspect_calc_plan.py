import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from friday_core.agent.planner import PEOVPlanner
p = PEOVPlanner()
m = p.plan_compound_directive("open calculator and calculate 25 * 4")
if m:
    print(f"Mission: {m.mission_id}, Steps: {len(m.steps)}")
    for s in m.steps:
        print(f"  Step {s.step_id}: tool={s.tool_id}, params={s.params}, deps={s.dependencies}")
else:
    print("No compound mission planned.")
