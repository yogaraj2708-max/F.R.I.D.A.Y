"""
F.R.I.D.A.Y. 3.0 — Agent Tool Bridge & Verification Layer
Connects the MAIN LLM directly to registered tools with OpenAPI schemas,
risk gating, and verifiable provenance tracking.
Python = Execution + Safety + Verification only.
MAIN LLM = Sole Tool-Selection Authority.
"""

import os
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from friday_core.skills.registry import skill_registry
from friday_core.skills.base import RiskLevel, BaseSkill, SkillResult

logger = logging.getLogger("FRIDAY.AgentBridge")


class AgentToolBridge:
    """
    Exposes registered tools to the MAIN LLM and enforces
    risk gating, execution dispatch, and provenance verification.
    """

    def __init__(self):
        self._capability_cache: Dict[str, bool] = {}

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Compiles provider-native OpenAPI tool schemas directly from SkillRegistry
        and core verified system capabilities.
        """
        tools: List[Dict[str, Any]] = []

        # 1. Core Verified Web & System Capabilities
        core_tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Searches the live web using DuckDuckGo for up-to-date facts, breaking news, people, companies, or specifications.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The concise search query string to look up on the web"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Evaluates a mathematical expression safely using python math engine.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "The mathematical expression to evaluate (e.g. 'sqrt(144)', '25 * 4')"
                            }
                        },
                        "required": ["expression"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "system_telemetry",
                    "description": "Retrieves live hardware telemetry including CPU load, RAM usage, battery percentage, and disk capacity.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_document",
                    "description": "Reads and analyzes the structured contents of an attached PDF, DOCX, text, JSON, CSV, or code document with targeted relevance retrieval and bounded context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The relative or absolute path of the document to inspect"
                            },
                            "focus": {
                                "type": "string",
                                "description": "Optional specific topic, heading, item, row condition, or symbol to locate in the document"
                            },
                            "page": {
                                "type": "integer",
                                "description": "Optional specific 1-based page number to read (for multi-page PDF)"
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "Optional character limit for extracted excerpt (default 3500)"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_document",
                    "description": "Surgically edits a specific targeted region in a DOCX, text, markdown, or code document with independent postcondition reopen verification.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The path of the document to edit"
                            },
                            "target": {
                                "type": "string",
                                "description": "The exact paragraph, heading, section, table cell, or text to modify"
                            },
                            "operation": {
                                "type": "string",
                                "enum": ["replace", "fill", "append", "delete"],
                                "description": "The surgical operation: 'replace', 'fill', 'append', or 'delete'"
                            },
                            "content": {
                                "type": "string",
                                "description": "The new content or text to insert or replace with (required for replace, fill, append)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Optional destination path if not modifying in place"
                            }
                        },
                        "required": ["file_path", "target", "operation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_image",
                    "description": "Performs neural visual inspection on an image or screenshot using the dedicated vision specialist model.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "image_path": {
                                "type": "string",
                                "description": "Path to the image file to inspect"
                            },
                            "question": {
                                "type": "string",
                                "description": "Specific question about what is shown in the image"
                            }
                        },
                        "required": ["image_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "launch_app",
                    "description": "Launches a Windows desktop application strictly matching the user request (e.g. 'notepad', 'calculator', 'chrome', 'edge'). NEVER launch unrequested applications.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {
                                "type": "string",
                                "description": "The exact name or path of the desktop application requested by the user"
                            }
                        },
                        "required": ["app_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Types or inserts text (including multiline text, C/C++ code, scripts, and formatted documents) into the target desktop application window specified by the user (such as 'notepad'). Supports braces, quotes, newlines, and symbols with verified UI insertion and screen readback.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The exact text or multiline source code to insert into the application"
                            },
                            "app_name": {
                                "type": "string",
                                "description": "Name of the target application requested by the user (e.g. 'notepad'). Must strictly match user intent."
                            },
                            "control_name": {
                                "type": "string",
                                "description": "Optional specific name or title of the editable control"
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["type", "replace", "append"],
                                "description": "Typing mode: 'replace' clears existing text and sets full content, 'append' adds to end, 'type' inserts at current position"
                            }
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Fetches current weather and forecast for any city or location worldwide.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city or region to query weather for (e.g. 'Tokyo', 'London', 'San Francisco')"
                            }
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "system_time_date",
                    "description": "Retrieves the current accurate system date, time, and timezone on this host.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query_type": {
                                "type": "string",
                                "enum": ["time", "date", "both"],
                                "description": "Whether to retrieve current time, date, or both"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "description": "Fetches and extracts clean readable text and headings from a specific webpage URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The HTTP or HTTPS URL of the webpage to fetch"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "inspect_ui",
                    "description": "Inspects and verifies the visible text and state of an application window on Windows desktop.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {
                                "type": "string",
                                "description": "Target window or application name (e.g. 'notepad', 'calculator')"
                            },
                            "expected_content": {
                                "type": "string",
                                "description": "Optional text string expected to be present in the window"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "click_control",
                    "description": "Focuses or clicks a specific UI button or control in an application window.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "control_name": {
                                "type": "string",
                                "description": "Name or title of the control to click or focus"
                            },
                            "app_name": {
                                "type": "string",
                                "description": "Optional target application name or window title"
                            },
                            "control_type": {
                                "type": "string",
                                "description": "Optional control type (e.g. 'button', 'menuitem', 'tabitem', 'checkbox')"
                            },
                            "automation_id": {
                                "type": "string",
                                "description": "Optional specific UI automation ID of the control"
                            }
                        },
                        "required": ["control_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "timer",
                    "description": "Sets or manages a countdown timer with duration in seconds.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "seconds": {
                                "type": "integer",
                                "description": "Duration of timer in seconds"
                            },
                            "label": {
                                "type": "string",
                                "description": "Descriptive label for the timer"
                            }
                        },
                        "required": ["seconds"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "deep_research",
                    "description": "Conducts autonomous multi-query deep web research on a complex topic and synthesizes a comprehensive report.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "The specific research topic or question to deeply investigate"
                            }
                        },
                        "required": ["topic"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_knowledge_base",
                    "description": "Searches the local knowledge base, indexed documents, or project notes using hybrid semantic retrieval and BM25 lexical search.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query string to locate within indexed documents and knowledge base"
                            },
                            "domain": {
                                "type": "string",
                                "enum": ["PROJECT", "PERSONAL", "TECHNICAL", "RESEARCH"],
                                "description": "Optional specific knowledge domain to filter by (default searches all)"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Maximum number of relevant chunks to retrieve (default 3, max 5)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        tools.extend(core_tools)

        # 2. Add Pluggable Skills from SkillRegistry
        excluded_skills = {
            "web_search", "calculate", "system_telemetry", "read_document",
            "edit_document", "analyze_image", "launch_app", "type_text",
            "inspect_ui", "click_control", "timer", "weather", "system_time_date",
            "web_fetch", "deep_research", "query_knowledge_base",
            "ui_type_text", "app_launcher", "word_drafter", "ui_key_press",
            "ui_focus", "ui_verify_content"
        }
        for s in skill_registry._skills.values():
            if s.tool_id in excluded_skills:
                continue

            properties = {}
            required = []
            if s.input_schema and hasattr(s.input_schema, "model_json_schema"):
                try:
                    js = s.input_schema.model_json_schema()
                    properties = js.get("properties", {})
                    required = js.get("required", [])
                except Exception as ex:
                    logger.debug("Failed extracting schema for %s: %s", s.tool_id, ex)

            tools.append({
                "type": "function",
                "function": {
                    "name": s.tool_id,
                    "description": s.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })

        return tools

    def risk_gate(self, tool_name: str, arguments: Dict[str, Any], user_query: Optional[str] = None) -> Tuple[bool, str]:
        """
        Section 20: Python still decides whether the action is ALLOWED to execute.
        Enforces path fencing, process protection, SSRF guards, and authoritative application selection.
        """
        # Block protected system actions
        prohibited_commands = [
            "rmdir /s /q c:\\", "format c:", "del /f /s /q c:\\windows",
            "shutdown /s", "drop database", "sudo rm -rf"
        ]
        arg_str = json.dumps(arguments).lower()
        if any(cmd in arg_str for cmd in prohibited_commands):
            return False, "Command contains prohibited destructive system directive."

        # Authoritative Application Selection Guard
        if tool_name in ["launch_app", "type_text"] and user_query:
            app_arg = str(arguments.get("app_name", "") or arguments.get("application", "") or arguments.get("name", "")).lower().strip()
            if app_arg:
                import re
                from friday_core.system.window_manager import window_manager
                target_norm = window_manager.normalize_app_name(app_arg)
                uq = user_query.lower()
                known_apps = ["notepad", "word", "vscode", "calculator", "chrome", "edge", "terminal", "cmd", "explorer"]
                user_apps = []
                for a in known_apps:
                    if a == "notepad":
                        if re.search(r"\b(?:notepad|note\s*pad|notes)\b", uq):
                            user_apps.append("notepad")
                    elif a == "word":
                        if re.search(r"\b(?:ms\s+|microsoft\s+)?word\b", uq):
                            user_apps.append("word")
                    elif a == "vscode":
                        if re.search(r"\b(?:vs\s*code|visual\s+studio\s+code|vscode|(?:in|open|launch)\s+code)\b", uq):
                            user_apps.append("vscode")
                    elif a == "calculator":
                        if re.search(r"\b(?:calc|calculator)\b", uq):
                            is_calc_subject = bool(re.search(r"\b(?:make|create|write|build|code|program|script|develop|implement)\s+.*?\b(?:calc|calculator)\b", uq))
                            is_calc_app_requested = bool(re.search(r"\b(?:open|launch|run|start)\s+(?:the\s+)?(?:calc|calculator)\b|\b(?:in|into)\s+(?:the\s+|my\s+)?(?:calc|calculator)\b", uq))
                            if not is_calc_subject or is_calc_app_requested:
                                user_apps.append("calculator")
                    else:
                        if re.search(rf"\b{a}\b", uq):
                            user_apps.append(a)

                if user_apps and target_norm:
                    canonical_user_apps = [window_manager.normalize_app_name(ua) for ua in user_apps]
                    if target_norm not in canonical_user_apps:
                        return False, f"Target application '{app_arg}' was not requested by user. Explicit user target: {', '.join(user_apps)}. Authoritative Application Selection requires strict adherence to user intent."

        # Path fencing for file/document tools
        if tool_name in ["read_document", "read_file", "edit_document"]:
            file_path = str(arguments.get("file_path", "")).strip()
            clean_fp = file_path.lower()
            if ".." in clean_fp or clean_fp.startswith("\\\\") or clean_fp.startswith("//"):
                return False, "Access blocked: directory traversal and UNC network shares are prohibited by security policy."
            from friday_core.document.file_detector import is_sensitive_path
            if is_sensitive_path(clean_fp):
                return False, "Access to sensitive system configuration files is blocked by path guard."

        # SSRF Protection for Web & Research Tools
        if tool_name in ["web_fetch", "web_search", "deep_research"]:
            target_url = str(arguments.get("url", "") or arguments.get("topic", "") or arguments.get("query", "")).strip()
            if "://" in target_url:
                from urllib.parse import urlparse
                parsed = urlparse(target_url)
                scheme = parsed.scheme.lower()
                if scheme not in ("http", "https"):
                    return False, f"Access blocked: Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted."
                host = (parsed.hostname or "").lower()
                import ipaddress
                if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254") or host.endswith(".local") or host.endswith(".internal"):
                    return False, f"Access blocked: Destination '{host}' targets private/internal infrastructure (SSRF Guard)."
                try:
                    ip_obj = ipaddress.ip_address(host)
                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                        return False, f"Access blocked: IP '{host}' is private/reserved (SSRF Guard)."
                except ValueError:
                    pass

        # Execution protection for app launching
        if tool_name == "launch_app":
            app = str(arguments.get("app_name", "")).lower().strip()
            dangerous_tokens = ["cmd.exe /c", "powershell -enc", "powershell.exe -enc", "wscript", "cscript", "certutil", "regsvr32", "mshta"]
            if any(tok in app for tok in dangerous_tokens):
                return False, "Execution blocked: Arbitrary shell script or script-interpreter injection detected."

        # Process protection (e.g. killing system processes)
        if tool_name in ["kill_process", "close_process"]:
            target = arguments.get("process_name", "").lower()
            if target in ["csrss.exe", "winlogon.exe", "lsass.exe", "explorer.exe", "svchost.exe"]:
                return False, f"Target process '{target}' is protected by platform guard."

        # Pluggable skill authorization
        skill = skill_registry.get(tool_name)
        if skill:
            auth = skill.authorize()
            if not auth.authorized:
                return False, auth.reason

        return True, "AUTHORIZED"

    def verify_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        raw_output: Any,
        trace_id: str,
        tool_call_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Section 19: Attaches verifiable provenance and truth verification to tool results.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        out_str = str(raw_output) if raw_output is not None else ""

        is_error = "error" in out_str.lower() or "failed" in out_str.lower() or not out_str
        is_blocked = "blocked by security policy" in out_str.lower()
        if is_blocked:
            exec_status = "BLOCKED"
            verif_status = "BLOCKED"
        elif is_error:
            exec_status = "FAILED"
            verif_status = "REJECTED"
        else:
            exec_status = "SUCCESS"
            verif_status = "VERIFIED"

        provenance = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id or f"call_{uuid.uuid4().hex[:8]}",
            "execution_status": exec_status,
            "verification_status": verif_status,
            "trace_id": trace_id,
            "executed_at": now_iso,
        }

        # Specialized provenance fields
        if tool_name in ["web_search", "web_fetch", "deep_research"]:
            import re
            source_urls = re.findall(r"https?://[^\s)\]]+", out_str)
            provenance["source_urls"] = source_urls[:5]

        if tool_name in ["type_text", "launch_app", "inspect_ui", "click_control"]:
            provenance["target_app"] = arguments.get("app_name") or arguments.get("control_name", "")
            provenance["action"] = tool_name
            provenance["verified_state"] = "CONFIRMED_ON_DESKTOP" if exec_status == "SUCCESS" else "FAILED"
        elif tool_name == "read_document":
            provenance["source_file"] = arguments.get("file_path", "")
            provenance["extracted_chars"] = len(out_str)
        elif tool_name == "edit_document":
            provenance["source_file"] = arguments.get("file_path", "")
            provenance["target"] = arguments.get("target", "")
            provenance["operation"] = arguments.get("operation", "")
            if isinstance(raw_output, dict):
                provenance["before_hash"] = raw_output.get("before_hash", "")
                provenance["after_hash"] = raw_output.get("after_hash", "")
                provenance["verification_details"] = raw_output.get("verification", {})
        elif tool_name == "analyze_image":
            provenance["image_file"] = arguments.get("image_path", "")
            provenance["question"] = arguments.get("question", "")
            if isinstance(raw_output, dict):
                provenance["image_id"] = raw_output.get("image_id", "")
                provenance["vision_model"] = raw_output.get("source_model", "") or raw_output.get("vision_model", "")
                provenance["uncertainty_rating"] = raw_output.get("uncertainty_rating", "OBSERVED")
                provenance["dimensions"] = raw_output.get("dimensions", (0, 0))
            elif hasattr(raw_output, "image_id"):
                provenance["image_id"] = getattr(raw_output, "image_id", "")
                provenance["vision_model"] = getattr(raw_output, "source_model", "")
                provenance["uncertainty_rating"] = getattr(raw_output, "uncertainty_rating", "OBSERVED")
                provenance["dimensions"] = getattr(raw_output, "dimensions", (0, 0))
            else:
                import re
                img_id_match = re.search(r"\[VERIFIED IMAGE CONTEXT:\s*([^\]]+)\]", out_str)
                if img_id_match:
                    provenance["image_id"] = img_id_match.group(1).strip()
                v_model_match = re.search(r"Analyzed by Specialist Model:\s*([^\n\r]+)", out_str)
                if v_model_match:
                    provenance["vision_model"] = v_model_match.group(1).strip()
                unc_match = re.search(r"Confidence / Uncertainty:\s*([^\n\r]+)", out_str)
                if unc_match:
                    provenance["uncertainty_rating"] = unc_match.group(1).strip()
                dim_match = re.search(r"Dimensions:\s*([0-9]+x[0-9]+)", out_str)
                if dim_match:
                    provenance["dimensions"] = dim_match.group(1).strip()

        formatted_result = (
            f"[VERIFIED TOOL PROVENANCE | tool: {tool_name} | status: {exec_status} | verification: {verif_status} | trace: {trace_id}]\n"
            f"{out_str}"
        )

        bundle = {
            "provenance": provenance,
            "formatted_result": formatted_result,
            "status": exec_status,
            "verification_status": verif_status,
            "raw_output": raw_output
        }
        bundle.update(provenance)
        return bundle


agent_tool_bridge = AgentToolBridge()
