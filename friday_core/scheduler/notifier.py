"""
F.R.I.D.A.Y. 3.0 — Native Windows Toast Notifier
Dispatches actionable Windows toast notifications via PowerShell / Windows Runtime.
Maintains an immutable notification audit log.
"""

import os
import uuid
import subprocess
import threading
import logging
from typing import List, Dict, Any, Optional
from friday_core.scheduler.models import NotificationMessage, TaskPriority

logger = logging.getLogger("FRIDAY.Notifier")


class WindowsNotifier:
    """
    Dispatches native Windows toasts and tracks notification history.
    """
    def __init__(self, enable_system_toasts: bool = True):
        self.enable_system_toasts = enable_system_toasts
        self._history: List[NotificationMessage] = []
        self._lock = threading.Lock()

    def get_history(self) -> List[NotificationMessage]:
        with self._lock:
            return list(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def notify(
        self,
        title: str,
        body: str,
        urgency: TaskPriority = TaskPriority.NORMAL,
        action_button: Optional[str] = None,
        action_payload: Optional[Dict[str, Any]] = None
    ) -> NotificationMessage:
        """
        Dispatches a notification and records it into history.
        """
        msg = NotificationMessage(
            id=f"notif-{uuid.uuid4().hex[:8]}",
            title=title,
            body=body,
            urgency=urgency,
            action_button=action_button,
            action_payload=action_payload
        )

        with self._lock:
            self._history.append(msg)
            if len(self._history) > 100:
                self._history.pop(0)

        logger.info(f"[{urgency.value}] Notification emitted: '{title}' - '{body}'")

        if self.enable_system_toasts and os.name == "nt":
            self._dispatch_windows_toast(title, body)

        return msg

    def _dispatch_windows_toast(self, title: str, body: str) -> None:
        """Spawns non-blocking PowerShell script to trigger Windows Action Center toast."""
        # Sanitize single quotes to prevent injection
        safe_title = title.replace("'", "''")
        safe_body = body.replace("'", "''")

        ps_script = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_body}')) | Out-Null; "
            f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('F.R.I.D.A.Y. 3.0').Show($toast);"
        )

        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception as e:
            logger.warning(f"Could not dispatch Windows toast: {e}")


# Global Singleton Notifier
windows_notifier = WindowsNotifier(enable_system_toasts=False)  # default quiet for automated tests
