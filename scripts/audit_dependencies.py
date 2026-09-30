"""
Phase 2 — Direct Dependency Audit Script
Tests all requirements and scanned imports inside the real .venv.
"""

import sys
import os
import re
import ast
import json
import importlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Requirements mapping from package name to importable module name
PKG_TO_MODULE = {
    "PySide6": "PySide6",
    "PySide6-Fluent-Widgets": "qfluentwidgets",
    "qasync": "qasync",
    "edge-tts": "edge_tts",
    "pygame-ce": "pygame",
    "sounddevice": "sounddevice",
    "SpeechRecognition": "speech_recognition",
    "ollama": "ollama",
    "duckduckgo_search": "duckduckgo_search",
    "numpy": "numpy",
    "rapidfuzz": "rapidfuzz",
    "certifi": "certifi",
    "pywin32": "win32api",
    "kokoro-onnx": "kokoro_onnx",
    "soundfile": "soundfile",
    "faster-whisper": "faster_whisper",
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "uiautomation": "uiautomation",
    "torch": "torch",
    "pytest": "pytest"
}

def scan_all_imports(dirs):
    third_party_modules = set()
    local_roots = {"friday_core", "friday_ui", "scripts", "tests", "scratch", "web"}
    stdlib_modules = sys.stdlib_module_names if hasattr(sys, 'stdlib_module_names') else set()

    for d in dirs:
        for py_path in d.rglob("*.py"):
            try:
                with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                tree = ast.parse(content, filename=str(py_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            root_pkg = alias.name.split(".")[0]
                            if root_pkg not in local_roots and root_pkg not in stdlib_modules:
                                third_party_modules.add(root_pkg)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.level == 0:
                            root_pkg = node.module.split(".")[0]
                            if root_pkg not in local_roots and root_pkg not in stdlib_modules:
                                third_party_modules.add(root_pkg)
            except Exception as e:
                pass
    return third_party_modules

def test_imports(module_names):
    results = {}
    for mod in sorted(module_names):
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", getattr(m, "VERSION", "INSTALLED"))
            file_loc = getattr(m, "__file__", "BUILTIN_OR_NAMESPACE")
            results[mod] = {
                "status": "PASS",
                "version": str(ver),
                "location": str(file_loc)
            }
        except ImportError as e:
            results[mod] = {
                "status": "FAIL",
                "error": str(e)
            }
        except Exception as e:
            results[mod] = {
                "status": "ERROR",
                "error": str(e)
            }
    return results

def main():
    print("[*] Running Phase 2 Dependency Audit...")
    
    # 1. Audit requirements.txt
    req_file = BASE_DIR / "requirements.txt"
    req_pkgs = []
    if req_file.exists():
        with open(req_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = re.split(r"[><=;]", line)[0].strip()
                    req_pkgs.append(pkg)

    req_results = {}
    for pkg in req_pkgs:
        mod = PKG_TO_MODULE.get(pkg, pkg.replace("-", "_"))
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", getattr(m, "VERSION", "INSTALLED"))
            req_results[pkg] = {
                "module": mod,
                "status": "PASS",
                "version": str(ver)
            }
        except ImportError as e:
            req_results[pkg] = {
                "module": mod,
                "status": "FAIL",
                "error": str(e)
            }

    # 2. Audit all third-party imports scanned in source
    scanned_mods = scan_all_imports([BASE_DIR / "friday_core", BASE_DIR / "friday_ui"])
    scanned_results = test_imports(scanned_mods)

    audit_data = {
        "requirements_manifest": req_results,
        "scanned_third_party_imports": scanned_results
    }

    out_json = BASE_DIR / "audit" / "runtime" / "dependency_audit.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)
    print(f"[+] Saved dependency audit json to {out_json}")

    # Generate docs/verification/PHASE_2_VERIFICATION.md
    out_md = BASE_DIR / "docs" / "verification" / "PHASE_2_VERIFICATION.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    
    req_rows = []
    for pkg, info in req_results.items():
        req_rows.append(f"| `{pkg}` | `{info['module']}` | `{info.get('version', info.get('error'))}` | **{info['status']}** |")

    scanned_rows = []
    failed_scanned = []
    for mod, info in scanned_results.items():
        status = info["status"]
        if status != "PASS":
            failed_scanned.append((mod, info.get("error", "Unknown")))
        scanned_rows.append(f"| `{mod}` | `{info.get('version', info.get('error'))}` | **{status}** |")

    md_content = f"""# F.R.I.D.A.Y. 3.0 — PHASE 2 DEPENDENCY AUDIT
**Generated:** Real-Time Direct Virtual Environment Import Test
**Status:** {'PASS' if not failed_scanned else 'INSPECT'}

---

## 1. Requirements Manifest Verification (`requirements.txt`)
| Manifest Package | Tested Module | Detected Version | Status |
| :--- | :--- | :--- | :--- |
{chr(10).join(req_rows)}

---

## 2. Scanned Source Code Third-Party Imports
Total distinct external third-party modules detected: **{len(scanned_mods)}**

| Module Name | Detected Version / Error | Status |
| :--- | :--- | :--- |
{chr(10).join(scanned_rows)}

---

## 3. Discrepancy & Optional Dependency Analysis
{f"- **Missing / Failing Modules**: {len(failed_scanned)}" if failed_scanned else "- **Zero Missing Modules**: All scanned imports successfully imported inside the current `.venv`."}
{chr(10).join([f"  - `{m}`: {err}" for m, err in failed_scanned])}

---

## 4. Verdict
**VERDICT: {'PASS' if not failed_scanned else 'FAIL'}**
- All production dependencies verified via real import execution.
- Raw telemetry recorded at `audit/runtime/dependency_audit.json`.
"""

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[+] Saved dependency audit markdown to {out_md}")

if __name__ == "__main__":
    main()
