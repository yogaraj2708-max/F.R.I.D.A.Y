import sys
import os
import asyncio
sys.path.insert(0, os.path.abspath('.'))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from friday_ui.core.engine import FridaySignals, FridayVoiceEngine, FridayBrain
from friday_ui.views.chat_view import ChatView
from friday_ui.widgets.chat_bubble import ChatBubble

signals = FridaySignals()
tts = FridayVoiceEngine(signals)
brain = FridayBrain(signals, tts)
chat_view = ChatView()

signals.stream_started.connect(chat_view.start_stream)
signals.stream_token.connect(chat_view.append_token)
signals.stream_thinking.connect(chat_view.append_thinking)
signals.stream_finished.connect(chat_view.finish_stream)

trace = []

def log_event(name, **kwargs):
    evt = {"event": name, **kwargs}
    trace.append(evt)
    print(f"TRACE: {name} | {kwargs}")

signals.stream_started.connect(lambda role, status: log_event("stream_started", role=role, status=status))
signals.stream_token.connect(lambda token: log_event("stream_token", token_len=len(token), sample=repr(token[:20])))
signals.stream_thinking.connect(lambda token: log_event("stream_thinking", token_len=len(token), sample=repr(token[:20])))
signals.stream_finished.connect(lambda text: log_event("stream_finished", text_len=len(text), sample=repr(text[:40])))

async def run_test():
    query = "what shall we do now"
    print(f"=== Testing query: '{query}' ===")
    
    # Check smart skill first
    skill_res = await brain.execute_smart_skill(query)
    print(f"skill_res: {repr(skill_res)}")
    
    if not skill_res:
        # Falls through to query_llm
        print("Calling query_llm...")
        reply = await brain.query_llm(query, stream_to_ui=True, stream_to_speech=False)
        print(f"query_llm returned reply: {repr(reply)}")
    
    # Process Qt events so timers and signals fire
    for _ in range(10):
        app.processEvents()
        await asyncio.sleep(0.05)
        
    # Check ChatView state
    bubbles = [chat_view.chat_layout.itemAt(i).widget() for i in range(chat_view.chat_layout.count()) if isinstance(chat_view.chat_layout.itemAt(i).widget(), ChatBubble)]
    print(f"Found {len(bubbles)} ChatBubbles in ChatView:")
    for idx, b in enumerate(bubbles):
        plain = b.text_browser.toPlainText()
        raw = b.raw_text
        thinking = b.thinking_text
        print(f"  Bubble {idx} [{b.role}]:")
        print(f"    raw_text (len={len(raw)}): {repr(raw[:60])}")
        print(f"    text_browser plain (len={len(plain)}): {repr(plain[:60])}")
        print(f"    thinking_text (len={len(thinking)}): {repr(thinking[:60])}")
        print(f"    text_browser isVisible: {b.text_browser.isVisible()}, height: {b.text_browser.height()}")

asyncio.run(run_test())
