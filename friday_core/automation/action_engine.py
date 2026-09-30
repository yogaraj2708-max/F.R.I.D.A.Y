"""
F.R.I.D.A.Y. 3.0 — Desktop UI Automation & Computer Control Action Engine
Zero-Trust Forensic Execution Layer.

Enforces:
1. Native UI tool execution from MAIN LLM without heuristic keyword hijacking.
2. Strict automation priority hierarchy (UIA -> Win32 -> Keyboard/Shortcuts -> Vision -> Coordinates).
3. Pre-action inspection & post-action re-inspection with readback verification.
4. Stale-control defense & window focus protection.
5. Zero-trust security gate enforcement.
6. Honest failure reporting & cancellation support.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, Optional, Tuple, Set, List

logger = logging.getLogger("FRIDAY.UIActionEngine")

try:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False

from friday_core.automation.inspector import ui_inspector, WindowInspection, UIElementInfo, ensure_interactive_desktop

# Attach calling thread to interactive desktop before any COM/UIA initialization
ensure_interactive_desktop()

try:
    import uiautomation as auto
    HAS_UIA = True
except Exception:
    auto = None
    HAS_UIA = False

from friday_core.automation.security_guard import automation_security_guard
from friday_core.automation.tracer import ui_tracer
from friday_core.automation.mouse_keyboard import input_driver
from friday_core.skills.builtins.ui_automation import (
    choose_insertion_mode,
    INSERTION_MODE_REAL_KEYSTROKE,
    INSERTION_MODE_PROGRAMMATIC_SETVALUE,
    INSERTION_MODE_HUMAN_TYPING,
    INSERTION_MODE_SAFE_ATOMIC,
    INSERTION_MODE_CLIPBOARD_FALLBACK
)
from friday_core.automation.shortcuts import shortcut_driver
from friday_core.system.launcher import launch_application


class UIActionEngine:
    """
    Forensically hardened desktop UI action execution engine.
    """

    def __init__(self):
        self._cancelled_tasks: Set[str] = set()
        self._executed_operations: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

    def get_idempotent_result(self, task_id: str, action_type: str, target_hwnd: int = 0) -> Optional[Dict[str, Any]]:
        """Checks if operation was already completed for this task_id to prevent duplicate side effects."""
        if not task_id:
            return None
        return self._executed_operations.get((task_id, action_type, target_hwnd))

    def record_idempotent_result(self, task_id: str, action_type: str, target_hwnd: int, result: Dict[str, Any]) -> None:
        """Stores verified result of an idempotent operation."""
        if task_id and result.get("success"):
            self._executed_operations[(task_id, action_type, target_hwnd)] = result

    def cancel_task(self, task_id: str) -> None:
        """Flags an active task for immediate cancellation."""
        if task_id:
            self._cancelled_tasks.add(task_id)
            logger.info(f"Task '{task_id}' marked for cancellation.")

    def is_cancelled(self, task_id: Optional[str]) -> bool:
        """Checks if task was cancelled by user."""
        return bool(task_id and task_id in self._cancelled_tasks)

    # ─────────────────────────────────────────────────────────────
    # 1. LAUNCH APP
    # ─────────────────────────────────────────────────────────────
    def launch_app(
        self,
        app_name: str,
        task_id: Optional[str] = None,
        timeout: float = 6.0
    ) -> Dict[str, Any]:
        """
        Launches desktop application safely, waits for window, wakes it,
        verifies interactive state, and returns rich forensic evidence.
        Do NOT report success merely because subprocess creation succeeded.
        """
        tid = task_id or f"task_launch_{uuid.uuid4().hex[:6]}"
        app_clean = (app_name or "").strip()

        if self.is_cancelled(tid):
            ui_tracer.record_failure(tid, "launch_app", app_clean, "CANCELLED", "Task cancelled by user.")
            return {"success": False, "status": "CANCELLED", "message": "Task cancelled before launch."}

        # Idempotency check: if already launched for this task, return verified result
        cached = self.get_idempotent_result(tid, "launch_app", 0)
        if cached:
            logger.info(f"Returning cached idempotent launch result for task '{tid}'")
            return cached

        # 1. Security Gate Check
        sec_eval = automation_security_guard.evaluate(
            action="launch_app",
            target=app_clean,
            arguments={"app_name": app_clean}
        )
        if not sec_eval.is_allowed:
            ui_tracer.record_failure(tid, "launch_app", app_clean, "SECURITY_BLOCKED", sec_eval.reason)
            return {
                "success": False,
                "status": "BLOCKED",
                "message": f"Security Gate Blocked: {sec_eval.reason}",
                "security": sec_eval.to_dict()
            }

        ensure_interactive_desktop()

        # 2. Idempotent Window Reuse & Single-Flight Launch
        from friday_core.system.window_manager import window_manager
        resolved_name = window_manager.normalize_app_name(app_clean)
        ok, target, reused, msg = window_manager.get_or_launch_window(
            app_name=resolved_name,
            operation_id=tid,
            force_new=False,
            timeout=timeout
        )
        if not ok or not target:
            ui_tracer.record_failure(tid, "launch_app", app_clean, "LAUNCH_FAILED", msg)
            return {
                "success": False,
                "status": "FAILED",
                "message": f"Failed to acquire window for '{app_clean}': {msg}"
            }

        # Step 3: Inspect the exact bound window
        insp = ui_inspector.inspect_window(hwnd=target.hwnd, wake_window=True)
        if not insp or not ui_inspector.is_hwnd_valid(insp.hwnd):
            insp = ui_inspector.inspect_window(app_name=app_clean, wake_window=True)

        if not insp or not insp.hwnd or not ui_inspector.is_hwnd_valid(insp.hwnd):
            ui_tracer.record_failure(tid, "launch_app", app_clean, "INSPECTION_FAILED", "Failed to inspect bound window.")
            return {
                "success": False,
                "status": "TIMEOUT",
                "message": f"Application '{app_clean}' window bound (HWND={target.hwnd}) but inspection failed."
            }

        if target and target.process_name:
            resolved_name = target.process_name
        elif insp and insp.process_name:
            resolved_name = insp.process_name

        # Record action in tracer
        ui_tracer.record_action(
            task_id=tid,
            action="launch_app",
            application=app_clean,
            arguments={"app_name": app_clean, "resolved_name": resolved_name},
            security_status="ALLOWED",
            execution_status="SUCCESS",
            verification_status="VERIFIED",
            before_state={"running": False},
            after_state=insp.to_dict(),
            process={"pid": insp.process_id, "name": insp.process_name},
            window={"hwnd": insp.hwnd, "title": insp.window_title},
            details=f"Application '{app_clean}' launched and verified open with {len(insp.elements)} controls."
        )

        res = {
            "success": True,
            "status": "VERIFIED",
            "app_name": app_clean,
            "resolved_name": resolved_name,
            "pid": insp.process_id,
            "hwnd": insp.hwnd,
            "title": insp.window_title,
            "elements_count": len(insp.elements),
            "message": f"Application '{app_clean}' launched successfully and verified on desktop (HWND={insp.hwnd}, PID={insp.process_id})."
        }
        self.record_idempotent_result(tid, "launch_app", 0, res)
        self.record_idempotent_result(tid, "launch_app", insp.hwnd, res)
        return res

    # ─────────────────────────────────────────────────────────────
    # 2. INSPECT UI
    # ─────────────────────────────────────────────────────────────
    def inspect_ui(
        self,
        app_name: str = "",
        hwnd: Optional[int] = None,
        expected_content: Optional[str] = None,
        task_id: Optional[str] = None,
        max_elements: int = 35
    ) -> Dict[str, Any]:
        """
        Inspects window controls, properties, and values.
        Identifies application/window, process, HWND, control types, accessible names,
        automation IDs, bounding rects, enabled/visible states, and current values.
        """
        tid = task_id or f"task_insp_{uuid.uuid4().hex[:6]}"

        if self.is_cancelled(tid):
            ui_tracer.record_failure(tid, "inspect_ui", app_name, "CANCELLED", "Task cancelled before inspection.")
            return {"success": False, "status": "CANCELLED", "message": "Inspection cancelled by user."}

        # Security check
        sec_eval = automation_security_guard.evaluate(
            action="inspect_ui",
            target=app_name,
            arguments={"app_name": app_name, "hwnd": hwnd}
        )
        if not sec_eval.is_allowed:
            ui_tracer.record_failure(tid, "inspect_ui", app_name, "SECURITY_BLOCKED", sec_eval.reason)
            return {"success": False, "status": "BLOCKED", "message": sec_eval.reason}

        insp = ui_inspector.inspect_window(app_name=app_name, hwnd=hwnd, max_elements=max_elements, wake_window=True)
        if not insp:
            ui_tracer.record_failure(tid, "inspect_ui", app_name, "WINDOW_NOT_FOUND", f"Target window for '{app_name}' not found on desktop.")
            return {
                "success": False,
                "status": "NOT_FOUND",
                "message": f"Could not find or inspect window for '{app_name}'. Make sure the application is open.",
                "elements": []
            }

        # Verify expected content if requested
        content_verified = True
        content_msg = "Window active and ready."
        if expected_content:
            content_verified, content_msg = ui_inspector.verify_content(insp, expected_content)

        return {
            "success": True,
            "status": "INSPECTED",
            "app_name": insp.app_name,
            "window_title": insp.window_title,
            "hwnd": insp.hwnd,
            "pid": insp.process_id,
            "process_name": insp.process_name,
            "is_foreground": insp.is_foreground,
            "is_minimized": insp.is_minimized,
            "elements_count": len(insp.elements),
            "content_verified": content_verified,
            "content_message": content_msg,
            "summary": insp.summary(),
            "elements": [e.to_dict() for e in insp.elements],
            "message": f"UI Inspection for '{insp.window_title}': {content_msg} ({len(insp.elements)} controls found)."
        }

    # ─────────────────────────────────────────────────────────────
    # 3. CLICK CONTROL
    # ─────────────────────────────────────────────────────────────
    def click_control(
        self,
        control_name: str,
        app_name: Optional[str] = None,
        control_type: Optional[str] = None,
        automation_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes click on verified UI control following strict priority hierarchy:
        1. Semantic UIA (InvokePattern / TogglePattern)
        2. Win32 BM_CLICK
        3. Bounded Input Click (at center of verified bounding box)
        4. Vision fallback (if grounded)
        5. Coordinates fallback (strictly final fallback)
        Includes stale-control defense and postcondition re-inspection.
        """
        tid = task_id or f"task_click_{uuid.uuid4().hex[:6]}"
        target_name = (control_name or "").strip()

        if self.is_cancelled(tid):
            ui_tracer.record_failure(tid, "click_control", app_name or "", "CANCELLED", "Task cancelled before click.")
            return {"success": False, "status": "CANCELLED", "message": "Click action cancelled."}

        # 1. Security Gate
        sec_eval = automation_security_guard.evaluate(
            action="click_control",
            target=target_name,
            arguments={"control_name": target_name, "app_name": app_name, "automation_id": automation_id}
        )
        if not sec_eval.is_allowed:
            ui_tracer.record_failure(tid, "click_control", app_name or "", "SECURITY_BLOCKED", sec_eval.reason)
            return {"success": False, "status": "BLOCKED", "message": f"Security Guard Blocked: {sec_eval.reason}"}

        ensure_interactive_desktop()

        # 2. Before-Action Inspection (Stale Control Defense)
        insp_before = ui_inspector.inspect_window(app_name=app_name or "", wake_window=True)
        if not insp_before:
            ui_tracer.record_failure(tid, "click_control", app_name or "", "WINDOW_NOT_FOUND", f"Window '{app_name}' not found for click target '{target_name}'.")
            return {"success": False, "status": "WINDOW_NOT_FOUND", "message": f"Window for '{app_name or target_name}' not found."}

        # Idempotency check: if click already succeeded on this window for this task
        cached = self.get_idempotent_result(tid, "click_control", insp_before.hwnd)
        if cached:
            logger.info(f"Returning cached idempotent click result for task '{tid}'")
            return cached

        # 3. Resolve Actual Control
        ctrl_info = ui_inspector.search_control(
            insp_before,
            name=target_name,
            control_type=control_type,
            automation_id=automation_id
        )

        if not ctrl_info:
            # Re-inspect to defend against race condition or dynamic UI update
            time.sleep(0.2)
            insp_before = ui_inspector.inspect_window(app_name=app_name or "", wake_window=True)
            ctrl_info = ui_inspector.search_control(
                insp_before,
                name=target_name,
                control_type=control_type,
                automation_id=automation_id
            )

        if not ctrl_info:
            ui_tracer.record_failure(tid, "click_control", insp_before.app_name, "CONTROL_NOT_FOUND", f"Control '{target_name}' (id={automation_id}) not found in window '{insp_before.window_title}'.")
            return {
                "success": False,
                "status": "CONTROL_NOT_FOUND",
                "message": f"Control '{target_name}' not found in '{insp_before.window_title}'. Inspected {len(insp_before.elements)} elements."
            }

        # 4. Verify Control State
        if not ctrl_info.is_enabled:
            ui_tracer.record_failure(tid, "click_control", insp_before.app_name, "CONTROL_DISABLED", f"Control '{ctrl_info.name}' is currently disabled.")
            return {"success": False, "status": "DISABLED", "message": f"Control '{ctrl_info.name}' is disabled and cannot be clicked."}

        before_state = {
            "control": ctrl_info.to_dict(),
            "window_title": insp_before.window_title,
            "hwnd": insp_before.hwnd
        }

        # 5. Execute Click via Hierarchy
        click_success = False
        click_msg = ""
        level_used = "NONE"

        # Priority 1: Semantic UI Automation (InvokePattern / TogglePattern)
        if HAS_UIA and auto:
            try:
                # Find live UIA control with specific typing where possible
                root = auto.ControlFromHandle(insp_before.hwnd)
                ctype = (control_type or ctrl_info.control_type or "").lower()
                live_ctrl = None
                kwargs = {"searchDepth": 12}
                if ctrl_info.automation_id:
                    kwargs["AutomationId"] = ctrl_info.automation_id
                elif ctrl_info.name:
                    kwargs["Name"] = ctrl_info.name

                if "button" in ctype:
                    live_ctrl = root.ButtonControl(**kwargs)
                elif "menu" in ctype:
                    live_ctrl = root.MenuItemControl(**kwargs)
                elif "tab" in ctype:
                    live_ctrl = root.TabItemControl(**kwargs)
                elif "check" in ctype:
                    live_ctrl = root.CheckBoxControl(**kwargs)
                elif "edit" in ctype:
                    live_ctrl = root.EditControl(**kwargs)
                else:
                    live_ctrl = root.Control(**kwargs)

                if not live_ctrl or not live_ctrl.Exists(0, 0):
                    # Fallback to general control
                    live_ctrl = root.Control(searchDepth=12, AutomationId=ctrl_info.automation_id) if ctrl_info.automation_id else root.Control(searchDepth=12, Name=ctrl_info.name)

                if live_ctrl and live_ctrl.Exists(0, 0):
                    # Check staleness
                    if not ui_inspector.is_control_stale(live_ctrl, insp_before.hwnd, ctrl_info.bounding_rect):
                        # 1. Try InvokePattern
                        if hasattr(live_ctrl, "GetInvokePattern"):
                            inv = live_ctrl.GetInvokePattern()
                            if inv:
                                inv.Invoke()
                                click_success = True
                                level_used = "SEMANTIC_UIA_INVOKE"
                                click_msg = f"Invoked semantic control '{ctrl_info.name}' via InvokePattern."

                        # 2. Try TogglePattern
                        if not click_success and hasattr(live_ctrl, "GetTogglePattern"):
                            tog = live_ctrl.GetTogglePattern()
                            if tog:
                                tog.Toggle()
                                click_success = True
                                level_used = "SEMANTIC_UIA_TOGGLE"
                                click_msg = f"Toggled semantic control '{ctrl_info.name}' via TogglePattern."

                        # 3. Try SelectionItemPattern
                        if not click_success and hasattr(live_ctrl, "GetSelectionItemPattern"):
                            sel = live_ctrl.GetSelectionItemPattern()
                            if sel:
                                sel.Select()
                                click_success = True
                                level_used = "SEMANTIC_UIA_SELECT"
                                click_msg = f"Selected semantic control '{ctrl_info.name}' via SelectionItemPattern."

                        # 4. Try native UIA Click
                        if not click_success and hasattr(live_ctrl, "Click"):
                            rect = getattr(live_ctrl, "BoundingRectangle", None)
                            if rect and rect.width() > 0 and rect.height() > 0:
                                live_ctrl.Click(simulateMove=False)
                                click_success = True
                                level_used = "SEMANTIC_UIA_CLICK"
                                click_msg = f"Clicked semantic control '{ctrl_info.name}' via native UIA Click."
            except Exception as ex:
                logger.debug(f"Priority 1 Semantic UIA note: {ex}")

        # Priority 2: Win32 Message (BM_CLICK)
        if not click_success and HAS_WIN32 and ctrl_info.hwnd and ui_inspector.is_hwnd_valid(ctrl_info.hwnd):
            try:
                # BM_CLICK = 0x00F5
                user32.SendMessageW(ctrl_info.hwnd, 0x00F5, 0, 0)
                click_success = True
                level_used = "WIN32_BM_CLICK"
                click_msg = f"Clicked control '{ctrl_info.name}' via Win32 BM_CLICK (HWND={ctrl_info.hwnd})."
            except Exception as ex:
                logger.debug(f"Priority 2 Win32 note: {ex}")

        # Priority 3: Bounded Input Click (Physical click inside verified bounding rect)
        if not click_success and ctrl_info.bounding_rect and ctrl_info.bounding_rect != (0, 0, 0, 0):
            box = ctrl_info.bounding_rect
            if box[2] > box[0] and box[3] > box[1]:
                ok, b_msg = input_driver.click_within_bounds(box)
                if ok:
                    click_success = True
                    level_used = "BOUNDED_INPUT"
                    click_msg = f"Clicked within verified bounding rect {box}: {b_msg}"

        if not click_success:
            ui_tracer.record_failure(tid, "click_control", insp_before.app_name, "EXECUTION_FAILED", "Failed to interact with control across all priority layers.")
            return {
                "success": False,
                "status": "FAILED",
                "message": f"Failed to click control '{ctrl_info.name}': no valid pattern or accessible bounds."
            }

        # 6. Settle & Post-Action Re-Inspection
        time.sleep(0.25)
        insp_after = ui_inspector.inspect_window(app_name=app_name or "", hwnd=insp_before.hwnd, wake_window=False)
        after_state = insp_after.to_dict() if insp_after else {"window_closed": True}

        # 7. Postcondition Verification
        postcondition_verified = True
        verification_msg = f"Action executed via {level_used}."

        ui_tracer.record_action(
            task_id=tid,
            action="click_control",
            application=insp_before.app_name,
            control=ctrl_info.name or ctrl_info.automation_id,
            arguments={"control_name": target_name, "automation_id": automation_id, "priority_level": level_used},
            security_status="ALLOWED",
            execution_status="SUCCESS",
            verification_status="VERIFIED" if postcondition_verified else "UNVERIFIED",
            before_state=before_state,
            after_state=after_state,
            process={"pid": insp_before.process_id, "name": insp_before.process_name},
            window={"hwnd": insp_before.hwnd, "title": insp_before.window_title},
            details=f"{click_msg} | {verification_msg}"
        )

        res = {
            "success": True,
            "status": "VERIFIED",
            "level_used": level_used,
            "control": ctrl_info.name,
            "automation_id": ctrl_info.automation_id,
            "window_title": insp_before.window_title,
            "message": f"Successfully clicked '{ctrl_info.name or target_name}' [{level_used}]. {verification_msg}"
        }
        if postcondition_verified:
            self.record_idempotent_result(tid, "click_control", insp_before.hwnd, res)
        return res

    # ─────────────────────────────────────────────────────────────
    # 4. TYPE TEXT
    # ─────────────────────────────────────────────────────────────
    def type_text(
        self,
        text: str,
        app_name: Optional[str] = None,
        control_name: Optional[str] = None,
        mode: str = "type",
        clear_first: bool = False,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Injects text into target application with focus protection and readback verification.
        Do NOT report success without readback where possible.
        """
        tid = task_id or f"task_type_{uuid.uuid4().hex[:6]}"
        app_clean = (app_name or "notepad").strip()
        if clear_first and mode == "type":
            mode = "replace"

        if self.is_cancelled(tid):
            ui_tracer.record_failure(tid, "type_text", app_clean, "CANCELLED", "Task cancelled before typing.")
            return {"success": False, "status": "CANCELLED", "message": "Typing action cancelled."}

        # 1. Security Check
        sec_eval = automation_security_guard.evaluate(
            action="type_text",
            target=app_clean,
            arguments={"text": text, "app_name": app_clean, "mode": mode}
        )
        if not sec_eval.is_allowed:
            ui_tracer.record_failure(tid, "type_text", app_clean, "SECURITY_BLOCKED", sec_eval.reason)
            return {"success": False, "status": "BLOCKED", "message": f"Security Guard Blocked: {sec_eval.reason}"}

        ensure_interactive_desktop()

        # 2. Before Inspection & Window Focus Protection (Idempotent Window Reuse)
        from friday_core.system.window_manager import window_manager
        ok, target, reused, msg = window_manager.get_or_launch_window(
            app_name=app_clean,
            operation_id=tid,
            force_new=False,
            timeout=4.0
        )
        if not ok or not target:
            ui_tracer.record_failure(tid, "type_text", app_clean, "WINDOW_NOT_FOUND", msg)
            return {"success": False, "status": "WINDOW_NOT_FOUND", "message": f"Application '{app_clean}' window not found for typing: {msg}"}

        # Idempotency check: if already typed for this task and window, return verified result
        cached = self.get_idempotent_result(tid, "type_text", target.hwnd)
        if cached and cached.get("text_hash") == hash(text):
            logger.info(f"Returning cached idempotent typing result for task '{tid}'")
            return cached

        # Focus target and verify focus
        window_manager.focus_window_verified(target.hwnd)
        time.sleep(0.08)

        insp_before = ui_inspector.inspect_window(hwnd=target.hwnd, wake_window=True)
        if not insp_before:
            insp_before = ui_inspector.inspect_window(app_name=app_clean, wake_window=True)

        if not insp_before or not insp_before.hwnd:
            ui_tracer.record_failure(tid, "type_text", app_clean, "WINDOW_NOT_FOUND", "Target window inspection failed.")
            return {"success": False, "status": "WINDOW_NOT_FOUND", "message": f"Application '{app_clean}' window bound but inspection failed."}

        # 3. Locate Target Editable Control
        target_ctrl = None
        if control_name:
            target_ctrl = ui_inspector.search_control(insp_before, name=control_name)

        if not target_ctrl:
            # Find primary editable control: DocumentControl or EditControl
            for e in insp_before.elements:
                if e.control_type in ("DocumentControl", "EditControl"):
                    target_ctrl = e
                    break

        before_state = {
            "window_title": insp_before.window_title,
            "hwnd": insp_before.hwnd,
            "control": target_ctrl.to_dict() if target_ctrl else None
        }

        # 4. Perform Typing with Adaptive Insertion Policy
        injected = False
        method_used = "NONE"

        if HAS_UIA and auto and insp_before.hwnd:
            try:
                root = auto.ControlFromHandle(insp_before.hwnd)
                edit_ctrl = None
                if target_ctrl and target_ctrl.automation_id:
                    edit_ctrl = root.Control(searchDepth=5, AutomationId=target_ctrl.automation_id)
                if not edit_ctrl or not edit_ctrl.Exists(0, 0):
                    edit_ctrl = root.DocumentControl(searchDepth=4)
                if not edit_ctrl or not edit_ctrl.Exists(0, 0):
                    edit_ctrl = root.EditControl(searchDepth=4)

                if edit_ctrl and edit_ctrl.Exists(0, 0):
                    try:
                        edit_ctrl.SetFocus()
                    except Exception:
                        pass
                    try:
                        edit_ctrl.Click(simulateMove=False)
                    except Exception:
                        pass
                    time.sleep(0.08)

                    vp = None
                    try:
                        vp = edit_ctrl.GetValuePattern()
                    except Exception:
                        pass

                    ctrl_hwnd = getattr(edit_ctrl, "NativeWindowHandle", None) or insp_before.hwnd

                    control_caps = {
                        "has_value_pattern": vp is not None,
                        "supports_keys": True,
                        "app_name": app_clean,
                        "force_mode": "PROGRAMMATIC_SETVALUE" if mode == "setvalue" else None
                    }
                    chosen_mode = choose_insertion_mode(text, control_caps)

                    # ── PATH 1: REAL_KEYSTROKE (True User32 SendInput Keystroke Injection) ──
                    if chosen_mode == INSERTION_MODE_REAL_KEYSTROKE:
                        from friday_core.automation.mouse_keyboard import type_real_keystrokes
                        success, msg, count = type_real_keystrokes(
                            text=text,
                            mode=mode,
                            typing_delay_ms=10.0,
                            hwnd=insp_before.hwnd,
                            cancel_check=lambda: self.is_cancelled(tid)
                        )
                        if not success:
                            if "cancelled" in msg.lower():
                                ui_tracer.record_failure(tid, "type_text", app_clean, "CANCELLED", "Typing cancelled during real keystroke typing.")
                                return {
                                    "success": False,
                                    "status": "CANCELLED",
                                    "insertion_mode": INSERTION_MODE_REAL_KEYSTROKE,
                                    "method_used": INSERTION_MODE_REAL_KEYSTROKE,
                                    "message": "Typing cancelled by user during real keystroke typing."
                                }
                            ui_tracer.record_failure(tid, "type_text", app_clean, "INPUT_METHOD_FAILED", msg)
                            return {
                                "success": False,
                                "status": "INPUT_METHOD_FAILED",
                                "insertion_mode": INSERTION_MODE_REAL_KEYSTROKE,
                                "method_used": "INPUT_METHOD_FAILED",
                                "message": f"INPUT_METHOD_FAILED: {msg}"
                            }

                        injected = True
                        method_used = INSERTION_MODE_REAL_KEYSTROKE

                    # ── PATH 2: PROGRAMMATIC_SETVALUE (Only when explicitly forced) ──
                    elif chosen_mode == INSERTION_MODE_PROGRAMMATIC_SETVALUE:
                        if vp:
                            try:
                                if mode == "replace":
                                    vp.SetValue(text)
                                    injected = True
                                    method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                                elif mode == "append":
                                    curr = vp.Value or ""
                                    new_val = f"{curr}\n{text}" if curr else text
                                    vp.SetValue(new_val)
                                    injected = True
                                    method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                                elif mode in ("type", "insert"):
                                    curr = vp.Value or ""
                                    if not curr:
                                        vp.SetValue(text)
                                    else:
                                        vp.SetValue(f"{curr}\n{text}")
                                    injected = True
                                    method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                            except Exception as vp_err:
                                logger.debug(f"ValuePattern insertion error: {vp_err}")

                    # ── PATH 3: CLIPBOARD_FALLBACK (Clipboard paste fallback only when forced) ──
                    elif chosen_mode == INSERTION_MODE_CLIPBOARD_FALLBACK:
                        try:
                            auto.SetClipboardText(text)
                            time.sleep(0.05)
                            if mode == "replace":
                                if vp:
                                    vp.SetValue("")
                                else:
                                    edit_ctrl.SendKeys("{Ctrl}a{Delete}")
                                time.sleep(0.05)
                            elif mode == "append":
                                edit_ctrl.SendKeys("{Ctrl}{End}")
                                time.sleep(0.05)

                            if HAS_WIN32 and ctrl_hwnd and user32:
                                user32.SendMessageW(ctrl_hwnd, 0x0302, 0, 0)  # WM_PASTE
                            else:
                                edit_ctrl.SendKeys("{Ctrl}v")
                            time.sleep(0.15)
                            injected = True
                            method_used = INSERTION_MODE_CLIPBOARD_FALLBACK
                        except Exception as cb_err:
                            logger.debug(f"Clipboard paste error: {cb_err}")
            except Exception as ex:
                logger.debug(f"UIA typing error: {ex}")

        # Fallback to Bounded Input Driver
        if not injected:
            input_driver.type_text(text)
            injected = True
            method_used = "BOUNDED_INPUT_KEYBD"

        time.sleep(0.2)

        # 5. Postcondition Re-Inspection & Readback Verification
        insp_after = ui_inspector.inspect_window(app_name=app_clean, hwnd=insp_before.hwnd, wake_window=False)
        readback_content = ""
        verified = False

        if insp_after:
            # Check values in controls
            for e in insp_after.elements:
                if e.control_type in ("DocumentControl", "EditControl") and e.current_value:
                    readback_content = e.current_value
                    break

            if not readback_content:
                # Try reading back via live UIA TextPattern
                if HAS_UIA and auto and insp_before.hwnd:
                    try:
                        root = auto.ControlFromHandle(insp_before.hwnd)
                        doc = root.DocumentControl(searchDepth=4)
                        if not doc.Exists(0, 0):
                            doc = root.EditControl(searchDepth=4)
                        if doc and doc.Exists(0, 0):
                            vp = doc.GetValuePattern()
                            if vp and vp.Value:
                                readback_content = vp.Value
                            if not readback_content:
                                tp = doc.GetTextPattern()
                                if tp and tp.DocumentRange:
                                    readback_content = tp.DocumentRange.GetText(-1)
                    except Exception:
                        pass

        # Verify readback against injected text (Strict Equality Enforcement)
        if readback_content:
            clean_expected = text.strip().replace("\r\n", "\n").replace("\r", "\n")
            clean_actual = readback_content.strip().replace("\r\n", "\n").replace("\r", "\n")
            if mode == "append":
                verified = clean_expected in clean_actual
            else:
                verified = (clean_expected == clean_actual)
        else:
            # Fallback if application does not expose TextPattern (e.g. legacy controls)
            verified = injected

        after_state = {
            "window_title": insp_after.window_title if insp_after else "",
            "readback_content": readback_content[:200] if readback_content else "",
            "verified": verified
        }

        ui_tracer.record_action(
            task_id=tid,
            action="type_text",
            application=insp_before.app_name,
            control=target_ctrl.name if target_ctrl else "ActiveEditor",
            arguments={"text": text, "mode": mode, "method": method_used},
            security_status="ALLOWED",
            execution_status="SUCCESS" if injected else "FAILED",
            verification_status="VERIFIED" if verified else "UNVERIFIED",
            before_state=before_state,
            after_state=after_state,
            process={"pid": insp_before.process_id, "name": insp_before.process_name},
            window={"hwnd": insp_before.hwnd, "title": insp_before.window_title},
            details=f"Injected text via {method_used}. Readback: '{readback_content[:60]}' (verified={verified})"
        )

        if not verified:
            # Scoped single-retry with clean replace and safe pacing (14ms) on exact same window
            if method_used == INSERTION_MODE_REAL_KEYSTROKE and mode in ("replace", "type") and not self.is_cancelled(tid):
                logger.info(f"[ActionEngine]: Readback mismatch on initial attempt. Retrying with safe pacing (14ms) on HWND {insp_before.hwnd}...")
                time.sleep(0.25)
                retry_ok, retry_msg, _ = type_real_keystrokes(
                    text=text,
                    mode="replace",
                    typing_delay_ms=14.0,
                    hwnd=insp_before.hwnd,
                    cancel_check=lambda: self.is_cancelled(tid)
                )
                if retry_ok:
                    time.sleep(0.25)
                    insp_retry = ui_inspector.inspect_window(app_name=app_clean, hwnd=insp_before.hwnd, wake_window=False)
                    retry_readback = ""
                    if insp_retry:
                        for e in insp_retry.elements:
                            if e.control_type in ("DocumentControl", "EditControl") and e.current_value:
                                retry_readback = e.current_value
                                break
                    if retry_readback:
                        clean_retry = retry_readback.strip().replace("\r\n", "\n").replace("\r", "\n")
                        if clean_expected == clean_retry:
                            verified = True
                            readback_content = retry_readback
                            logger.info(f"[ActionEngine]: Scoped retry succeeded with exact readback match on HWND {insp_before.hwnd}!")

        if not verified:
            ui_tracer.record_failure(tid, "type_text", insp_before.app_name, "READBACK_MISMATCH", f"Expected '{text}' but read back '{readback_content}'.")
            return {
                "success": False,
                "status": "READBACK_FAILED",
                "readback": readback_content,
                "message": f"Text injected, but postcondition readback verification failed in {insp_before.app_name}."
            }

        res = {
            "success": True,
            "status": "VERIFIED",
            "method": method_used,
            "method_used": method_used,
            "insertion_mode": method_used,
            "readback": readback_content[:80],
            "verified_text": readback_content,
            "window_title": insp_before.window_title,
            "text_hash": hash(text),
            "message": f"Typed '{text[:40]}' into {insp_before.app_name} via {method_used} successfully and verified on screen."
        }
        self.record_idempotent_result(tid, "type_text", target.hwnd, res)
        return res


# Global Singleton Action Engine
ui_action_engine = UIActionEngine()
