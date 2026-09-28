"""
F.R.I.D.A.Y. 3.0 — System Health Proactive Monitor
Monitors host hardware telemetry (battery, disk, memory, CPU) and triggers
proactive warnings when resource limits or critical thresholds are crossed.
"""

import time
import shutil
import psutil
import logging
from typing import Dict, Any, Optional
from friday_core.scheduler.models import TaskPriority
from friday_core.scheduler.notifier import windows_notifier, WindowsNotifier

logger = logging.getLogger("FRIDAY.SystemMonitor")


class SystemHealthMonitor:
    """
    Proactive background telemetry watcher for hardware metrics and alarms.
    """
    def __init__(self, notifier: Optional[WindowsNotifier] = None):
        self.notifier = notifier or windows_notifier
        self._last_alert_times: Dict[str, float] = {}
        self.alert_cooldown_seconds = 300.0  # 5 minutes between identical alerts

    def _can_alert(self, key: str) -> bool:
        now = time.time()
        last = self._last_alert_times.get(key, 0.0)
        if now - last > self.alert_cooldown_seconds:
            self._last_alert_times[key] = now
            return True
        return False

    def check_health(self) -> Dict[str, Any]:
        """
        Samples hardware telemetry, checks threshold boundaries, and triggers alerts.
        """
        metrics = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_free_gb": round(shutil.disk_usage("/").free / (1024 ** 3), 2),
            "battery_percent": None,
            "battery_plugged": None
        }

        # Check Battery
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                metrics["battery_percent"] = battery.percent
                metrics["battery_plugged"] = battery.power_plugged

                if battery.percent < 20 and not battery.power_plugged:
                    if self._can_alert("battery_low"):
                        self.notifier.notify(
                            title="Battery Critically Low",
                            body=f"Remaining power is {battery.percent}%. Please connect your charger.",
                            urgency=TaskPriority.CRITICAL,
                            action_button="Enable Power Saver"
                        )
        except Exception as e:
            logger.debug(f"Battery telemetry check: {e}")

        # Check Disk Space
        if metrics["disk_free_gb"] < 10.0:
            if self._can_alert("disk_low"):
                self.notifier.notify(
                    title="Low Storage Warning",
                    body=f"System drive has only {metrics['disk_free_gb']} GB free.",
                    urgency=TaskPriority.HIGH,
                    action_button="Launch Disk Cleanup"
                )

        # Check Memory Usage
        if metrics["memory_percent"] > 90.0:
            if self._can_alert("memory_high"):
                self.notifier.notify(
                    title="High Memory Usage",
                    body=f"RAM consumption reached {metrics['memory_percent']}%.",
                    urgency=TaskPriority.HIGH
                )

        return metrics
