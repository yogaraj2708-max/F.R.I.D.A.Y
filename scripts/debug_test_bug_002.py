import asyncio
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

async def run():
    print("[*] Initializing FridayBrain...")
    signals = FridaySignals()
    tts = FridayVoiceEngine(signals)
    brain = FridayBrain(signals, tts)
    
    print("[*] Testing Step 1: open calculator and calculate 25 * 4...")
    res_calc = await brain.execute_smart_skill("open calculator and calculate 25 * 4")
    print(f"Result Calc: {res_calc}")

    print("[*] Testing Step 2: open file explorer and navigate to Downloads...")
    res_nav = await brain.execute_smart_skill("open file explorer and navigate to Downloads")
    print(f"Result Nav: {res_nav}")

    print("[*] Testing Step 3: open note pad and type FRIDAY IS TESTING CONTEXT...")
    res_notepad = await brain.execute_smart_skill("open note pad and type FRIDAY IS TESTING CONTEXT")
    print(f"Result Notepad: {res_notepad}")

if __name__ == "__main__":
    asyncio.run(run())
