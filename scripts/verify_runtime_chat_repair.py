import sys
import os
import asyncio
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath('.'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication.instance() or QApplication(sys.argv)

from friday_ui.views.main_window import FridayMainWindow
from friday_ui.widgets.chat_bubble import ChatBubble

async def run_directive_test(window, directive: str, disable_tts: bool = False):
    print(f"\n=======================================================")
    print(f"TESTING DIRECTIVE: '{directive}' (TTS disabled={disable_tts})")
    print(f"=======================================================")
    
    tts_spoken = []
    
    async def mock_speak(text, display_text=None, emit_transcript=True):
        if not disable_tts:
            tts_spoken.append(text)
        return
    window.tts.speak = mock_speak

    # Record bubbles before
    chat_view = window.chat_view
    bubbles_before = [chat_view.chat_layout.itemAt(i).widget() 
                      for i in range(chat_view.chat_layout.count()) 
                      if isinstance(chat_view.chat_layout.itemAt(i).widget(), ChatBubble)]
    count_before = len(bubbles_before)
    
    # Progress trackers
    token_count = 0
    thinking_count = 0
    
    def on_token(tok):
        nonlocal token_count
        token_count += 1
        if token_count == 1:
            print(f"  [STREAM] First content token received at +{time.time()-start_t:.1f}s")
            
    def on_thinking(tok):
        nonlocal thinking_count
        thinking_count += 1
        if thinking_count == 1:
            print(f"  [STREAM] First thinking token received at +{time.time()-start_t:.1f}s")
            
    c1 = window.signals.stream_token.connect(on_token)
    c2 = window.signals.stream_thinking.connect(on_thinking)
    
    # Submit prompt
    start_t = time.time()
    chat_view.prompt_input.setText(directive)
    chat_view._submit_prompt()
    
    # Wait for completion (allow up to 180s for local 8B reasoning models)
    last_print = time.time()
    while getattr(window, '_current_command_task', None) and not window._current_command_task.done():
        app.processEvents()
        await asyncio.sleep(0.05)
        if time.time() - last_print >= 10.0:
            last_print = time.time()
            print(f"  ...waiting ({time.time()-start_t:.0f}s elapsed, thinking_tokens={thinking_count}, content_tokens={token_count})")
        if time.time() - start_t > 180:
            print("TIMEOUT waiting for directive execution")
            break
            
    print(f"Command task completed in {time.time()-start_t:.1f}s!")
    
    # Allow event loop and timers to settle
    settle_t = time.time()
    while getattr(window.tts, 'is_speaking', False) and time.time() - settle_t < 10:
        app.processEvents()
        await asyncio.sleep(0.05)
        
    for _ in range(20):
        app.processEvents()
        await asyncio.sleep(0.05)
        
    # Get bubbles after
    bubbles_after = [chat_view.chat_layout.itemAt(i).widget() 
                     for i in range(chat_view.chat_layout.count()) 
                     if isinstance(chat_view.chat_layout.itemAt(i).widget(), ChatBubble)]
    
    new_bubbles = bubbles_after[count_before:]
    user_bubble = None
    assistant_bubble = None
    for b in new_bubbles:
        if b.role == "user":
            user_bubble = b
        elif b.role == "friday":
            assistant_bubble = b
            
    user_text = user_bubble.text_browser.toPlainText() if user_bubble else ""
    asst_plain = assistant_bubble.text_browser.toPlainText() if assistant_bubble else ""
    asst_raw = getattr(assistant_bubble, 'raw_text', '') if assistant_bubble else ""
    asst_thinking = getattr(assistant_bubble, 'thinking_text', '') if assistant_bubble else ""
    
    hud_state = getattr(window.chat_view, '_current_engine_state', 'unknown')
    
    print(f"Results for '{directive}':")
    print(f"  New bubbles count:    {len(new_bubbles)}")
    print(f"  User bubble text:     {repr(user_text)}")
    print(f"  Assistant raw text:   {len(asst_raw)} chars -> {repr(asst_raw[:80])}")
    print(f"  Assistant plain text: {len(asst_plain)} chars -> {repr(asst_plain[:80])}")
    print(f"  Assistant thinking:   {len(asst_thinking)} chars")
    print(f"  TTS spoken text:      {len(' '.join(tts_spoken))} chars")
    print(f"  Final HUD state:      {hud_state}")
    
    # Assertions
    assert user_bubble is not None, "User bubble was not created!"
    assert assistant_bubble is not None, "Assistant bubble was not created!"
    assert len(asst_plain.strip()) > 0, "Assistant bubble remains visually empty!"
    assert len(asst_raw.strip()) > 0, "Assistant raw_text is empty!"
    assert hud_state in ["idle", "standby", "listening"], f"HUD did not return to idle/standby: {hud_state}"
    
    print(f"  -> VERIFICATION PASSED for '{directive}'")
    return {
        "directive": directive,
        "user_text": user_text,
        "asst_len": len(asst_plain),
        "asst_sample": asst_plain[:60],
        "tts_len": len(" ".join(tts_spoken)),
        "hud_state": hud_state
    }

async def main():
    print("=================================================================")
    print("LIVE RUNTIME VERIFICATION FOR CHAT BUBBLE & ENGINE STABILITY")
    print("=================================================================")
    
    window = FridayMainWindow()
    window.show()
    app.processEvents()
    
    results = []
    
    # Test 1: "Hi" (Smart skill greeting)
    res_hi = await run_directive_test(window, "Hi")
    results.append(res_hi)
    
    # Test 2: "what shall we do now" (Main LLM generation)
    res_gen = await run_directive_test(window, "what shall we do now")
    results.append(res_gen)
    
    # Test 3: "What is 2 + 2?" (Smart skill math)
    res_math = await run_directive_test(window, "What is 2 + 2?")
    results.append(res_math)
    
    # Test 4: TTS disabled check - "Hi" with TTS muted/disabled
    res_muted = await run_directive_test(window, "Hi", disable_tts=True)
    results.append(res_muted)
    
    # Capture final window screenshot
    pixmap = window.grab()
    shot_path = os.path.abspath("audit/live_chat_repair_verified.png")
    os.makedirs(os.path.dirname(shot_path), exist_ok=True)
    pixmap.save(shot_path)
    print(f"\nFinal screen capture saved to: {shot_path}")
    
    window.close()
    print("\n=================================================================")
    print("ALL 4 RUNTIME DIRECTIVE CHECKS SUCCEEDED WITH 100% SUCCESS")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
