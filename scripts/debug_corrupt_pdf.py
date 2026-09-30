import asyncio
import os
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

async def test():
    corrupt_path = os.path.abspath("scratch/corrupt_injection_test.pdf")
    os.makedirs(os.path.dirname(corrupt_path), exist_ok=True)
    with open(corrupt_path, "wb") as f:
        f.write(b"%PDF-1.4\n%Invalid Corrupted Garbage Bytes 0xDEADBEEF\n%%EOF")

    signals = FridaySignals()
    tts = FridayVoiceEngine(signals)
    brain = FridayBrain(signals, tts)
    cmd = f"what is the title of the pdf at '{corrupt_path}'"
    print(f"Command: {cmd}")
    
    # Check router
    route = await brain.semantic_router.route(cmd)
    print(f"Route: intent={route.intent}, score={route.confidence}, tier={route.tier}")

    res = await brain.execute_smart_skill(cmd)
    print(f"execute_smart_skill Result: {res}")

if __name__ == "__main__":
    asyncio.run(test())
