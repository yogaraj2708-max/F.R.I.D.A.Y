import os, sys
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from friday_ui.core.engine import FridayBrain, FridaySignals

async def main():
    print("=================================================================")
    print("VERIFYING LIVE AGENT TOOL PLUMBING FIX")
    print("=================================================================")
    
    signals = FridaySignals()
    signals.status_updated.connect(lambda s: print(f"  [SIGNAL: status_updated] {s}"))
    signals.stream_token.connect(lambda tok: print(tok, end="", flush=True))
    
    tts_mock = type("MockTTS", (), {
        "speak": lambda *args: None,
        "clean_text_for_speech": lambda self, t: t,
        "cancel_event": asyncio.Event(),
        "is_speaking": False
    })()
    
    brain = FridayBrain(signals, tts_mock)
    
    query = "who is jensen huang search web and tell"
    print(f"\nDirective: '{query}'")
    print("-----------------------------------------------------------------")
    reply = await brain.query_llm(query, stream_to_ui=True, stream_to_speech=False)
    print("\n-----------------------------------------------------------------")
    print("Final return value length:", len(reply))
    print("Verification complete!")

if __name__ == "__main__":
    asyncio.run(main())
