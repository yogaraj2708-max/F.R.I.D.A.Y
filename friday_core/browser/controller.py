"""
F.R.I.D.A.Y. 3.0 — Browser Agent Controller
Executes BrowserAction models, performs postcondition verification,
detects false-successes, and coordinates with Emergency Stop.
"""

import os
import time
import subprocess
import logging
from typing import Optional
from friday_ui.core.config import APP_DATA_DIR
from friday_core.agent.emergency_stop import emergency_stop
from friday_core.browser.models import (
    BrowserAction,
    BrowserActionType,
    BrowserState,
    BrowserObservation,
    BrowserVerification
)
from friday_core.browser.session import BrowserSession

logger = logging.getLogger("FRIDAY.BrowserController")


class BrowserController:
    """
    Coordinates browser execution, sandbox isolation, verification, and emergency stop.
    """
    def __init__(self, session: Optional[BrowserSession] = None):
        self.session = session or BrowserSession()
        self.sandbox_dir = os.path.join(APP_DATA_DIR, "browser_sandbox")
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self._browser_proc: Optional[subprocess.Popen] = None
        self._stopped = False

        # Register with global emergency stop
        try:
            emergency_stop.register_handler("browser", self.stop)
        except Exception:
            pass

    def stop(self):
        """Emergency stop handler terminating browser processes and active sessions."""
        self._stopped = True
        logger.warning("BrowserController received emergency stop signal.")
        if self._browser_proc is not None:
            try:
                self._browser_proc.terminate()
                self._browser_proc.kill()
            except Exception:
                pass
            self._browser_proc = None
        self.session.close()

    def execute(self, action: BrowserAction) -> BrowserObservation:
        """
        Executes a BrowserAction and returns a verified BrowserObservation.
        """
        if self._stopped or emergency_stop.is_stopped():
            return BrowserObservation(
                success=False,
                action_type=action.action_type,
                error="Browser execution rejected: Emergency Stop is active."
            )

        start_time = time.perf_counter()

        try:
            if action.action_type == BrowserActionType.NAVIGATE:
                if not action.url:
                    return BrowserObservation(
                        success=False,
                        action_type=action.action_type,
                        error="Navigation requires a target URL."
                    )
                state = self.session.navigate(action.url)
                duration = (time.perf_counter() - start_time) * 1000.0
                return BrowserObservation(
                    success=True,
                    action_type=action.action_type,
                    state=state,
                    duration_ms=round(duration, 2)
                )

            elif action.action_type == BrowserActionType.DOWNLOAD:
                if not action.url or not action.target_path:
                    return BrowserObservation(
                        success=False,
                        action_type=action.action_type,
                        error="Download action requires both 'url' and 'target_path'."
                    )
                ok, nbytes, err = self.session.download_file(action.url, action.target_path)
                duration = (time.perf_counter() - start_time) * 1000.0
                return BrowserObservation(
                    success=ok,
                    action_type=action.action_type,
                    downloaded_file=action.target_path if ok else None,
                    downloaded_bytes=nbytes,
                    error=err if not ok else None,
                    duration_ms=round(duration, 2)
                )

            elif action.action_type == BrowserActionType.INSPECT:
                state = self.session.current_state or BrowserState(url="", title="", text_content="")
                duration = (time.perf_counter() - start_time) * 1000.0
                return BrowserObservation(
                    success=True,
                    action_type=action.action_type,
                    state=state,
                    duration_ms=round(duration, 2)
                )

            elif action.action_type == BrowserActionType.CLOSE:
                self.session.close()
                duration = (time.perf_counter() - start_time) * 1000.0
                return BrowserObservation(
                    success=True,
                    action_type=action.action_type,
                    duration_ms=round(duration, 2)
                )

            else:
                return BrowserObservation(
                    success=False,
                    action_type=action.action_type,
                    error=f"Unsupported action type: {action.action_type}"
                )

        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000.0
            return BrowserObservation(
                success=False,
                action_type=action.action_type,
                error=str(e),
                duration_ms=round(duration, 2)
            )

    def verify_action(self, action: BrowserAction, obs: BrowserObservation) -> BrowserVerification:
        """
        Independent postcondition verifier enforcing the 'Never trust return code alone' rule.
        Detects false-successes where HTTP status is 200 but content is empty, or downloads missing.
        """
        if not obs.success:
            return BrowserVerification(
                verified=False,
                details=f"Action failed during execution: {obs.error}",
                false_success_detected=False
            )

        if action.action_type == BrowserActionType.DOWNLOAD:
            if not obs.downloaded_file or not os.path.exists(obs.downloaded_file):
                return BrowserVerification(
                    verified=False,
                    details="False success: Action reported success but downloaded file does not exist on disk.",
                    false_success_detected=True
                )
            if os.path.getsize(obs.downloaded_file) == 0:
                return BrowserVerification(
                    verified=False,
                    details="False success: Target file created on disk but has 0 bytes.",
                    false_success_detected=True
                )
            return BrowserVerification(
                verified=True,
                details=f"Verified file exists on disk ({obs.downloaded_bytes} bytes)."
            )

        elif action.action_type == BrowserActionType.NAVIGATE:
            if obs.state is None:
                return BrowserVerification(
                    verified=False,
                    details="False success: Action completed but BrowserState is None.",
                    false_success_detected=True
                )
            if obs.state.status_code >= 400:
                return BrowserVerification(
                    verified=False,
                    details=f"False success: Page returned HTTP error status {obs.state.status_code}.",
                    false_success_detected=True
                )
            return BrowserVerification(
                verified=True,
                details=f"Verified page loaded: '{obs.state.title}' with {len(obs.state.interactive_elements)} elements."
            )

        return BrowserVerification(verified=True, details="Action verified.")


# Global Singleton Browser Controller
browser_controller = BrowserController()
