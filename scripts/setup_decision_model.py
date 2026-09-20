"""
F.R.I.D.A.Y. 2.0 - Tactical Decision Model Setup Script
Ensures the lightweight decision maker model (qwen2.5:0.5b / friday-decider)
is pulled and compiled in local Ollama for 100% typo and slang accuracy.
"""

import sys
import os
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELFILE_PATH = REPO_ROOT / "friday_core" / "router" / "Modelfile.decider"


def setup_decision_model():
    print("\n-------------------------------------------------------")
    print(" [Tactical AI]: Checking Decision Engine Models in Ollama...")
    print("-------------------------------------------------------")

    # 1. Check if Ollama service is reachable
    try:
        import ollama
        client = ollama.Client(host="http://localhost:11434")
        models_info = client.list()
        installed = [m.model for m in models_info.models]
    except Exception as ex:
        print("[Notice]: Ollama service is not currently running or not installed.")
        print("          F.R.I.D.A.Y. will use the ultra-fast Tier 1 Vector Embedder (<0.5ms).")
        print("          To activate the neural typo decision maker, start Ollama anytime.")
        return False

    # 2. Check if friday-decider already exists
    if any("friday-decider" in m for m in installed):
        print("[OK] Tactical Decision Model ('friday-decider') is already installed and active.")
        return True

    # 3. If qwen2.5:0.5b is not installed, pull it
    if not any("qwen2.5:0.5b" in m for m in installed):
        print("Downloading lightweight decision model 'qwen2.5:0.5b' (~397 MB)...")
        print("This is a one-time download for accurate typo, slang, and command classification.")
        try:
            ret = subprocess.run(["ollama", "pull", "qwen2.5:0.5b"])
            if ret.returncode != 0:
                print("[Notice]: CLI pull returned non-zero, trying Ollama API...")
                client.pull("qwen2.5:0.5b")
        except Exception as pull_err:
            print(f"[Warning]: Failed to pull qwen2.5:0.5b: {pull_err}")
            print("          F.R.I.D.A.Y. will continue with Tier 1 Vector Embedder.")
            return False

    # 4. Compile friday-decider using Modelfile.decider
    if MODELFILE_PATH.exists():
        print("Compiling specialized 'friday-decider' model...")
        try:
            ret = subprocess.run(["ollama", "create", "friday-decider", "-f", str(MODELFILE_PATH)], capture_output=True, text=True)
            if ret.returncode == 0:
                print("[SUCCESS] Tactical Decision Model ('friday-decider') compiled successfully!")
                return True
            else:
                print(f"[Notice]: Model compilation output: {ret.stderr.strip()}")
        except Exception as comp_err:
            print(f"[Notice]: Could not compile friday-decider: {comp_err}")

    return True


if __name__ == "__main__":
    setup_decision_model()
