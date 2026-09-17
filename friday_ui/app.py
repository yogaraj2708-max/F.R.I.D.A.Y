"""
F.R.I.D.A.Y. 2.0 - Application Entry Point (qasync + PySide6)
"""

import sys
import os
import asyncio
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from qfluentwidgets import setTheme, Theme
import qasync

# Ensure Windows SSL certificate authority bundle is explicitly registered
try:
    import certifi
    ca_bundle = certifi.where()
    if os.path.exists(ca_bundle):
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
except Exception as ex:
    import logging
    logging.getLogger("FRIDAY.App").warning("Certifi bundle registration warning: %s", ex)

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from friday_core.settings import settings
from friday_ui.views.main_window import FridayMainWindow
from friday_ui.widgets.command_bar import FloatingCommandBar

def get_app_icon() -> QIcon:
    """Returns the high-resolution Stark Arc Reactor icon asset or falls back to programmatic icon."""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    ico_path = os.path.join(assets_dir, "friday_icon.ico")
    if os.path.exists(ico_path):
        return QIcon(ico_path)
    png_path = os.path.join(assets_dir, "friday_icon.png")
    if os.path.exists(png_path):
        return QIcon(png_path)
    return create_stark_icon()

def create_stark_icon(size: int = 64) -> QIcon:
    """Generates a high-resolution glowing cyan Stark Arc Reactor QIcon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    center = size / 2.0
    # Outer cyan ring
    pen = QPen(QColor(0, 240, 255, 230), size * 0.08)
    painter.setPen(pen)
    painter.drawEllipse(int(center - size * 0.4), int(center - size * 0.4), int(size * 0.8), int(size * 0.8))

    # Inner high-intensity ring
    pen = QPen(QColor(0, 255, 255, 255), size * 0.06)
    painter.setPen(pen)
    painter.drawEllipse(int(center - size * 0.25), int(center - size * 0.25), int(size * 0.5), int(size * 0.5))

    # Center glowing energy node
    painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(int(center - size * 0.12), int(center - size * 0.12), int(size * 0.24), int(size * 0.24))

    painter.end()
    return QIcon(pixmap)

def main():
    # Explicit Windows AppUserModelID to group under custom identity and display taskbar icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StarkIndustries.FRIDAY.Assistant.2.0")
        except Exception:
            pass

    # Enable DPI awareness
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    app.setApplicationName("F.R.I.D.A.Y. 2.0")
    app.setOrganizationName("Stark Industries")
    app.setQuitOnLastWindowClosed(True)   # Cleanly terminate process when user closes window

    stark_icon = get_app_icon()
    app.setWindowIcon(stark_icon)

    # Set qasync event loop as the primary asyncio event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize Main Window and Floating Command Bar
    window = FridayMainWindow()
    window.setWindowIcon(stark_icon)
    window.showMaximized()

    # First-run Onboarding & Operator Call-Sign Calibration
    if not settings.get("onboarding_completed", False):
        try:
            from friday_ui.widgets.onboarding_dialog import OnboardingDialog
            onboarding = OnboardingDialog(window)
            onboarding.setWindowIcon(stark_icon)
            onboarding.exec()
            # Refresh models & persona on window
            if hasattr(window, "brain") and hasattr(window.brain, "reload_persona"):
                window.brain.reload_persona()
            if hasattr(window, "chat_view") and hasattr(window.chat_view, "refresh_models"):
                window.chat_view.refresh_models()
        except Exception as ex:
            import logging
            logging.getLogger("FRIDAY.App").warning("Onboarding dialog launch skipped: %s", ex)

    # Clean any stale hotkey registration from previous crashes
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(None, 9119)
        except Exception:
            pass

    command_bar = FloatingCommandBar()
    command_bar.setWindowIcon(stark_icon)
    command_bar.setWindowTitle("F.R.I.D.A.Y. 2.0 Command Bar")
    window.command_bar = command_bar
    app.aboutToQuit.connect(command_bar.unregister_hotkey)

    # Automatically ensure desktop shortcut exists
    try:
        from scripts.create_desktop_shortcut import create_desktop_shortcut
        import threading
        threading.Thread(target=create_desktop_shortcut, daemon=True).start()
    except Exception:
        pass

    # Bridge Floating Command Bar <-> Engine
    window.command_bar = command_bar
    window.signals.state_changed.connect(command_bar.set_state)
    command_bar.voice_toggle_requested.connect(window.toggle_voice_loop)
    command_bar.stop_requested.connect(window.handle_stop_requested)

    async def handle_bar_command(command: str):
        command_bar.set_state("thinking")
        window.stop_current_task()
        window.chat_view.add_message("user", command)
        skill_res = await window.brain.execute_smart_skill(command)
        if skill_res:
            if skill_res != "__STREAMED__":
                command_bar.show_response(skill_res)
                command_bar.set_state("idle")
                await window.tts.speak(skill_res)
            else:
                command_bar.set_state("idle")
        else:
            kb_results = window.vector_store.query(command, top_k=1)
            kb_context = ""
            if kb_results and kb_results[0]["score"] > 0.12:
                kb_context = f"\n[Relevant Local Knowledge: {kb_results[0]['content'][:300]}]"
            prompt_text = command + kb_context if kb_context else command
            reply = await window.brain.query_llm(prompt_text, stream_to_ui=True, stream_to_speech=True)
            command_bar.show_response(reply)
            command_bar.set_state("idle")

    command_bar.command_submitted.connect(lambda cmd: loop.create_task(handle_bar_command(cmd)))

    # System Tray Integration
    tray_icon = QSystemTrayIcon(stark_icon, window)
    tray_icon.setToolTip("F.R.I.D.A.Y. 2.0 - Tactical AI Assistant")
    tray_menu = QMenu()

    show_action = tray_menu.addAction("Show F.R.I.D.A.Y.")
    show_action.triggered.connect(window.showMaximized)

    bar_action = tray_menu.addAction("Toggle Command Bar (Ctrl+Space)")
    bar_action.triggered.connect(command_bar.toggle_visibility)

    hide_action = tray_menu.addAction("Minimize to Tray")
    hide_action.triggered.connect(window.hide)

    tray_menu.addSeparator()

    # Panic Switch toggle from system tray
    def toggle_panic():
        curr = settings.get("observe_only", False)
        settings.set("observe_only", not curr)
        status = "ENABLED (Observe Only)" if not curr else "DISARMED (Normal)"
        tray_icon.showMessage("F.R.I.D.A.Y. Security", f"Panic Mode: {status}", QSystemTrayIcon.Information, 2000)

    panic_action = tray_menu.addAction("🛡️ Toggle Panic Switch (Observe Only)")
    panic_action.triggered.connect(toggle_panic)

    tray_menu.addSeparator()

    exit_action = tray_menu.addAction("Terminate Systems")
    exit_action.triggered.connect(app.quit)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.activated.connect(lambda reason: window.showMaximized() if reason == QSystemTrayIcon.Trigger else None)
    tray_icon.show()

    # Initial Welcome Voice Greeting & Voice Loop Start
    async def startup():
        await asyncio.sleep(0.8)
        user_name = settings.get("user_name", "Operator")
        user_title = settings.get("user_title", "Boss")
        call_sign = user_title if user_title and str(user_title).lower() != "none" else user_name
        window.chat_view.add_message(
            "friday",
            f"Systems initialized, {call_sign}. F.R.I.D.A.Y. 2.0 is online and standing by, {user_name}. "
            "Neural intelligence cores are calibrated."
        )
        if settings.get("auto_start_voice_loop", True):
            if not window.voice_loop.running:
                window.toggle_voice_loop()

    # Safely schedule startup greeting after qasync loop has started running
    QTimer.singleShot(350, lambda: loop.create_task(startup()))

    # Run loop
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
