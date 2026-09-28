import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.abspath('.'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap

app = QApplication.instance() or QApplication(sys.argv)

from friday_ui.views.main_window import FridayMainWindow
from friday_ui.widgets.chat_bubble import ChatBubble

window = FridayMainWindow()
window.show()

stage_records = []

def record_stage(stage_name, **kwargs):
    entry = {"stage": stage_name, "time": time.time(), **kwargs}
    stage_records.append(entry)
    print(f"[STAGE] {stage_name}: {kwargs}")

# Connect signal listeners
def on_stream_started(role, status):
    record_stage("assistant_bubble_creation_signal", role=role, status=status, status_len=len(status))
window.signals.stream_started.connect(on_stream_started)

thinking_chunks = []
def on_stream_thinking(token):
    thinking_chunks.append(token)
    if len(thinking_chunks) % 25 == 1:
        record_stage("stream_thinking_progress", count=len(thinking_chunks), total_len=sum(len(t) for t in thinking_chunks))
window.signals.stream_thinking.connect(on_stream_thinking)

token_chunks = []
def on_stream_token(token):
    token_chunks.append(token)
    accum = "".join(token_chunks)
    record_stage("stream_token_chunk", chunk_len=len(token), accum_len=len(accum), sample=repr(token[:20]))
window.signals.stream_token.connect(on_stream_token)

def on_stream_finished(text):
    record_stage("finalization_signal", text_len=len(text), sample=repr(text[:50]))
window.signals.stream_finished.connect(on_stream_finished)

# Instrument TTS speak
tts_records = []
orig_speak = window.tts.speak
async def traced_speak(text, display_text=None, emit_transcript=True):
    record_stage("tts_speak_called", text_len=len(text), display_len=len(display_text) if display_text else 0, emit_transcript=emit_transcript, sample=repr(text[:50]))
    tts_records.append(text)
    # Fast mock return to avoid audio device lock during scripted reproduction, while preserving transcript flow
    return
window.tts.speak = traced_speak

async def main_test():
    query = "what shall we do now"
    print(f"\n==========================================")
    print(f"STARTING LIVE REPRODUCTION: '{query}'")
    print(f"==========================================\n")
    
    # Simulate user typing into prompt input and pressing send
    window.chat_view.prompt_input.setText(query)
    record_stage("user_submitted_prompt", query=query, query_len=len(query))
    window.chat_view._submit_prompt()
    
    # Wait for processing and generation to complete
    start_wait = time.time()
    while getattr(window, '_current_command_task', None) and not window._current_command_task.done():
        app.processEvents()
        await asyncio.sleep(0.05)
        if time.time() - start_wait > 90:
            print("TIMEOUT: Command task took > 90s")
            break
            
    print("\nCommand task completed! Waiting for speech and UI animations to settle...")
    settle_start = time.time()
    while getattr(window.tts, 'is_speaking', False) and time.time() - settle_start < 30:
        app.processEvents()
        await asyncio.sleep(0.1)
        
    for _ in range(30):
        app.processEvents()
        await asyncio.sleep(0.05)
        
    # Capture window screenshot
    pixmap = window.grab()
    screenshot_path = os.path.abspath("audit/live_reproduction_screen.png")
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    pixmap.save(screenshot_path)
    print(f"\nScreenshot saved to: {screenshot_path}")
    
    # Forensic analysis of chat view bubbles
    chat_view = window.chat_view
    bubbles = [chat_view.chat_layout.itemAt(i).widget() for i in range(chat_view.chat_layout.count()) if isinstance(chat_view.chat_layout.itemAt(i).widget(), ChatBubble)]
    
    print(f"\n==========================================")
    print(f"CHAT BUBBLE FORENSIC AUDIT ({len(bubbles)} bubbles)")
    print(f"==========================================")
    
    last_assistant_bubble = None
    for idx, b in enumerate(bubbles):
        plain = b.text_browser.toPlainText()
        raw = b.raw_text
        thinking = b.thinking_text
        html = b.text_browser.toHtml()
        is_assistant = b.role == "friday"
        if is_assistant:
            last_assistant_bubble = b
        print(f"\n--- Bubble #{idx} [{b.role.upper()}] ---")
        print(f"  raw_text length: {len(raw)} | sample: {repr(raw[:60])}")
        print(f"  plain text length: {len(plain)} | sample: {repr(plain[:60])}")
        print(f"  thinking length: {len(thinking)} | sample: {repr(thinking[:60])}")
        print(f"  is_streaming: {b.is_streaming}")
        print(f"  text_browser geometry: isVisible={b.text_browser.isVisible()}, size={b.text_browser.width()}x{b.text_browser.height()}")
        print(f"  bubble geometry: isVisible={b.isVisible()}, size={b.width()}x{b.height()}")
        
    tts_text_len = sum(len(t) for t in tts_records)
    chat_text_len = len(last_assistant_bubble.text_browser.toPlainText()) if last_assistant_bubble else 0
    raw_text_len = len(last_assistant_bubble.raw_text) if last_assistant_bubble else 0
    
    print(f"\n==========================================")
    print(f"COMPARISON:")
    print(f"  TTS_TEXT length:  {tts_text_len}")
    print(f"  CHAT_TEXT length: {chat_text_len}")
    print(f"  RAW_TEXT length:  {raw_text_len}")
    print(f"==========================================\n")
    
    window.close()

asyncio.run(main_test())
