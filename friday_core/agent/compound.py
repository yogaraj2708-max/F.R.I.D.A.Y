"""
F.R.I.D.A.Y. 3.0 — Generalized Compound Intent Parser
Decomposes multi-clause compound instructions into structured, verifiable action sequences.
Supports:
  - open <app> and/then type <text>
  - open <app>, type <text>, and save it as <file>
  - open <app>, type <text>, press enter, type <text>, save as <file>
  - open <app> and write/draft <generative topic> (5-step DAG: launch, generate, focus, type, verify)
  - open <app> and calculate <expr>
  - open <app> and search for <query>
  - open <app> and navigate to <path>
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field


@dataclass
class CompoundStep:
    action: str
    target: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompoundPlan:
    goal: str
    steps: List[CompoundStep]


class CompoundIntentParser:
    """
    Generalized grammatical parser for multi-stage Windows desktop directives.
    Zero hardcoded command strings.
    """
    def __init__(self):
        # Action verb regex patterns
        self._open_verbs = r"(?:open|launch|start|run|pull\s+up|bring\s+up)"
        self._type_verbs = r"(?:type|write|enter|input|paste|insert|put)"
        self._press_verbs = r"(?:press|hit|tap)"
        self._calc_verbs = r"(?:calculate|compute|solve)"
        self._search_verbs = r"(?:search\s+for|search|look\s+up|google|find)"
        self._nav_verbs = r"(?:navigate\s+to|go\s+to|explore|browse\s+to)"
        self._save_verbs = r"(?:save\s+it\s+as|save\s+as|save\s+to|save)"

        # Generative content indicators (Sections 24 & 25)
        self._generative_topic_pattern = re.compile(
            r"^(?:a\s+|an\s+|the\s+)?(?:short\s+|formal\s+|casual\s+|brief\s+|official\s+|quick\s+|college\s+|working\s+|simple\s+)?"
            r"(?:welcome\s+speech|speech|birthday\s+message|message|apology\s+letter|leave\s+letter|letter|summary|"
            r"project\s+introduction|introduction|meeting\s+summary|essay|poem|note|memo|report|email|draft|"
            r"(?:c|c\+\+|python|java|javascript|rust|go|html|css|bash|powershell|sql)?\s*(?:program|code|script|app|calculator|function))\b",
            re.IGNORECASE
        )

    def is_generative_writing(self, text: str) -> bool:
        """Determines if the text specifies content generation rather than literal typing."""
        clean = text.strip().lower()
        if self._generative_topic_pattern.search(clean):
            return True
        if any(clean.startswith(p) for p in [
            "speech about", "letter to", "summary of", "message for", "introduction to",
            "program to", "code to", "code for", "script to", "script for", "calculator"
        ]):
            return True
        if any(p in clean for p in ["program", "code", "script", "calculator"]):
            return True
        return False

    def parse(self, text: str) -> Optional[CompoundPlan]:
        if not text:
            return None

        clean = text.strip()
        # Remove polite conversational prefixes
        clean = re.sub(
            r"^(?:hey\s+|hi\s+|hello\s+|friday\s+|jarvis\s+|please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|would\s+you\s+(?:please\s+)?)+",
            "",
            clean,
            flags=re.IGNORECASE
        ).strip()

        # -----------------------------------------------------------------
        # REVERSED SYNTAX: "write/draft/compose/code <topic> and put it in <app>"
        # Handles commands like:
        #   "write a c program to make a working calculator and put it in my note pad"
        #   "write a summary of Harry Potter and put it in my notepad"
        #   "draft a welcome speech and put it in notepad"
        #   "compose an email and put it in word"
        # -----------------------------------------------------------------
        reversed_match = re.match(
            r"^(?:write|draft|compose|code|create|generate)\s+(.+?)\s+(?:and\s+)?(?:put|place|paste|insert|type)\s+(?:it\s+|that\s+)?(?:in|into|on)\s+(?:my\s+)?(.+)$",
            clean,
            re.IGNORECASE
        )
        if reversed_match:
            topic = reversed_match.group(1).strip()
            raw_app = reversed_match.group(2).strip()
            if re.search(r"\b(?:notepad|note\s*pad|notes)\b", raw_app, re.IGNORECASE):
                app_name = "Notepad"
            elif re.search(r"\b(?:ms\s+|microsoft\s+)?word\b", raw_app, re.IGNORECASE):
                app_name = "Word"
            else:
                app_name = raw_app
            if self.is_generative_writing(topic):
                steps = [
                    CompoundStep(action="open_app", target=app_name, params={"app_name": app_name}),
                    CompoundStep(action="content_generation", target=topic, params={"prompt": topic, "target_app": app_name}),
                    CompoundStep(action="ui_focus", target=app_name, params={"app_name": app_name}),
                    CompoundStep(action="ui_type_text", target=app_name, params={
                        "app_name": app_name,
                        "text": "$content_generation.generated_text",
                        "mode": "replace"
                    }),
                    CompoundStep(action="ui_verify_content", target=app_name, params={
                        "app_name": app_name,
                        "expected_text": "$content_generation.generated_text",
                        "min_length": 15
                    })
                ]
                return CompoundPlan(goal=text, steps=steps)

        # Check if the command starts with an open/launch verb
        open_match = re.match(rf"^{self._open_verbs}\s+(.+?)(?:,\s*|\s+and\s+|\s+then\s+)(.+)$", clean, re.IGNORECASE)
        if not open_match:
            return None

        raw_app = open_match.group(1).strip()
        remainder = open_match.group(2).strip()

        # Ensure app name does not consume action verbs (e.g. "open notepad and type...")
        # Check if remainder starts with a valid secondary action
        app_name = raw_app

        # Special case: Word operations (paste, draft, write) should be delegated to engine Word automation handler
        if app_name.lower() in ("word", "ms word", "microsoft word", "winword"):
            return None

        # -------------------------------------------------------------
        # SPECIAL CASE: Semantic Content Generation (Sections 24 & 25)
        # e.g., "open notepad and write a welcome speech [for a college event]"
        # -------------------------------------------------------------
        write_gen_match = re.match(r"^(?:write|draft|compose)\s+(.+)$", remainder, re.IGNORECASE)
        if write_gen_match and self.is_generative_writing(write_gen_match.group(1).strip()):
            topic = write_gen_match.group(1).strip()
            # Construct 5-Step Dependent DAG:
            # STEP 1: APP_LAUNCH
            # STEP 2: CONTENT_GENERATION
            # STEP 3: UI_FOCUS
            # STEP 4: TYPE_GENERATED_CONTENT
            # STEP 5: VERIFY_UI_CONTENT
            steps = [
                CompoundStep(action="open_app", target=app_name, params={"app_name": app_name}),
                CompoundStep(action="content_generation", target=topic, params={"prompt": topic, "target_app": app_name}),
                CompoundStep(action="ui_focus", target=app_name, params={"app_name": app_name}),
                CompoundStep(action="ui_type_text", target=app_name, params={
                    "app_name": app_name,
                    "text": "$content_generation.generated_text",
                    "mode": "replace"
                }),
                CompoundStep(action="ui_verify_content", target=app_name, params={
                    "app_name": app_name,
                    "expected_text": "$content_generation.generated_text",
                    "min_length": 15
                })
            ]
            return CompoundPlan(goal=text, steps=steps)

        # -------------------------------------------------------------
        # GENERAL CASE: Multi-Clause Sequential Execution
        # Split remainder by clause delimiters:
        # e.g. "type first line, then press enter and type second line"
        # e.g. "type hello friday, then save it as test.txt"
        # e.g. "type line one, press enter, type line two, save as lines.txt"
        # -------------------------------------------------------------
        # Split delimiters: comma, semicolon, "then", "and then", or "and <action_verb>"
        delimiter_pattern = re.compile(
            r"(?:[,;]\s*(?:then\s+|and\s+)?|\s+then\s+|\s+and\s+(?=(?:type|write|enter|press|hit|save|calculate|search|navigate|go\b)))",
            re.IGNORECASE
        )
        raw_clauses = [c.strip() for c in delimiter_pattern.split(remainder) if c.strip()]
        if not raw_clauses:
            return None

        steps: List[CompoundStep] = [
            CompoundStep(action="open_app", target=app_name, params={"app_name": app_name})
        ]

        has_typed_before = False
        typed_contents = []

        for clause in raw_clauses:
            c = clause.strip()
            # Check for SAVE: "save it as test.txt", "save as lines.txt", "save the current text as friday.txt", "save test.txt"
            save_m = re.search(
                r"\bsave\s+(?:(?:the\s+|this\s+|my\s+)?(?:current\s+)?(?:text|file|document|it|this)?\s+)?as\s+['\"]?([a-zA-Z0-9_\-\.\/\\]+)['\"]?|\bsave\s+['\"]?([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)['\"]?",
                c,
                re.IGNORECASE
            )
            if save_m:
                fname = (save_m.group(1) or save_m.group(2) or "").strip().strip('"\'')
                save_params = {"app_name": app_name, "filename": fname}
                if typed_contents:
                    save_params["content"] = "\n".join(typed_contents)
                steps.append(CompoundStep(
                    action="save_file",
                    target=app_name,
                    params=save_params
                ))
                continue

            # Check for KEY PRESS: "press enter", "hit enter", "press tab"
            press_m = re.match(rf"^{self._press_verbs}\s+(.+)$", c, re.IGNORECASE)
            if press_m:
                raw_k = press_m.group(1).strip().lower()
                steps.append(CompoundStep(
                    action="ui_key_press",
                    target=app_name,
                    params={"app_name": app_name, "key": raw_k}
                ))
                continue

            # Check for TYPE / WRITE: "type first line", "type second line", "type hello friday"
            type_m = re.match(rf"^{self._type_verbs}\s+(.+)$", c, re.IGNORECASE)
            if type_m:
                text_to_type = type_m.group(1).strip()
                if c.lower().startswith("paste") and text_to_type.lower() in ("this", "that", "it", "content", "clipboard"):
                    continue
                typed_contents.append(text_to_type)
                # First typing operation clears/replaces existing buffer; subsequent appends
                mode = "append" if has_typed_before else "replace"
                steps.append(CompoundStep(
                    action="ui_type_text",
                    target=app_name,
                    params={"app_name": app_name, "text": text_to_type, "mode": mode}
                ))
                has_typed_before = True
                continue

            # Check for CALCULATE: "calculate 125 * 8", "compute 25 + 37"
            calc_m = re.match(rf"^{self._calc_verbs}\s+(.+)$", c, re.IGNORECASE)
            if calc_m:
                expr = calc_m.group(1).strip()
                steps.append(CompoundStep(
                    action="calculate",
                    target=expr,
                    params={"expression": expr}
                ))
                continue

            # Check for SEARCH: "search for <query>", "search <query>"
            search_m = re.match(rf"^{self._search_verbs}\s+(.+)$", c, re.IGNORECASE)
            if search_m:
                q = search_m.group(1).strip()
                steps.append(CompoundStep(
                    action="app_search",
                    target=app_name,
                    params={"app_name": app_name, "query": q}
                ))
                continue

            # Check for NAVIGATE: "go to Downloads", "navigate to <path>"
            nav_m = re.match(rf"^{self._nav_verbs}\s+(.+)$", c, re.IGNORECASE)
            if nav_m:
                p = nav_m.group(1).strip()
                steps.append(CompoundStep(
                    action="app_navigate",
                    target=app_name,
                    params={"app_name": app_name, "path": p}
                ))
                continue

        # If only open_app was parsed, this wasn't a valid multi-clause command
        if len(steps) <= 1:
            return None

        return CompoundPlan(goal=text, steps=steps)


compound_parser = CompoundIntentParser()
