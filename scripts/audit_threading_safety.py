"""
Phase 3 — Refined Threading & Event Loop Safety Forensic Scanner
Focuses strictly on true blocking I/O and CPU operations:
time.sleep, Thread.join, subprocess, HTTP, and synchronous skill execution.
"""

import sys
import os
import re
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent

PATTERNS = {
    "time_sleep": r"\btime\.sleep\s*\(",
    "thread_join": r"\b[a-zA-Z0-9_]+(?<!os\.path)\.join\s*\(",
    "subprocess": r"\bsubprocess\.(?:run|Popen|check_output|call)\s*\(",
    "urllib_request": r"\burllib\.request\.(?:urlopen|Request)\s*\(",
    "requests_http": r"\brequests\.(?:get|post|put|delete|request)\s*\(",
    "sync_skill_exec": r"\bskill_registry\.execute_skill\s*\(",
    "uia_wait": r"\b(?:WaitForExist|WaitDisappear|Exists)\s*\(",
    "sync_executor_mission": r"\bself\.executor\.execute_mission\s*\("
}

def scan_files():
    targets = [BASE_DIR / "friday_ui", BASE_DIR / "friday_core"]
    findings = {k: [] for k in PATTERNS}

    for t in targets:
        for py_path in t.rglob("*.py"):
            rel_path = str(py_path.relative_to(BASE_DIR)).replace("\\", "/")
            try:
                with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for line_idx, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    # Skip string.join like "".join or " ".join or '\n'.join
                    for tag, pat in PATTERNS.items():
                        if re.search(pat, line):
                            if tag == "thread_join" and any(q in line for q in ['"".join', '" ".join', "'\\n'.join", '"\\n".join', "os.path.join"]):
                                continue
                            findings[tag].append({
                                "file": rel_path,
                                "line": line_idx,
                                "code": stripped[:120]
                            })
            except Exception as e:
                pass
    return findings

def main():
    print("[*] Running Refined Threading & Event Loop Safety Scan...")
    findings = scan_files()
    
    for tag, items in findings.items():
        print(f"\n=== Pattern: {tag} ({len(items)} matches) ===")
        # Separate into friday_ui vs friday_core
        ui_matches = [i for i in items if i["file"].startswith("friday_ui")]
        core_matches = [i for i in items if not i["file"].startswith("friday_ui")]
        print(f"  friday_ui (High GUI Risk): {len(ui_matches)}")
        print(f"  friday_core (Worker / Backend): {len(core_matches)}")
        for m in ui_matches[:10]:
            print(f"    [UI] {m['file']}:{m['line']} -> {m['code']}")
            
    out_json = BASE_DIR / "audit" / "runtime" / "phase3_refined_blocking.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    print(f"\n[+] Saved refined findings to {out_json}")

if __name__ == "__main__":
    main()
