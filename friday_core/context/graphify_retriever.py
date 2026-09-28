"""
F.R.I.D.A.Y. 3.0 — Graphify Index-Driven Context Retriever
Transforms Graphify from a monolithic prompt attachment into a targeted structural index.
Retrieves only relevant nodes, call relationships, and source code windows within context budgets.
Zero HTML dumps; zero raw JSON dumps; strictly bounded code context.
"""

import os
import json
import logging
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path
from friday_core.context.budget import context_budget_manager, ContextBudgetManager

logger = logging.getLogger("FRIDAY.GraphifyRetriever")

GRAPHIFY_ARTIFACT_NAMES = {
    ".graphify_analysis.json",
    ".graphify_labels.json",
    "graph.html",
    "graph.json",
    "GRAPH_REPORT.md",
    "manifest.json",
    ".graphify_root",
}


def is_graphify_artifact(filepath: str) -> bool:
    """Detects whether a file belongs to the Graphify knowledge graph outputs."""
    if not filepath:
        return False
    fname = os.path.basename(filepath)
    if fname in GRAPHIFY_ARTIFACT_NAMES:
        return True
    norm_path = filepath.replace("\\", "/")
    if "graphify-out" in norm_path:
        return True
    return False


class GraphifyIndexRetriever:
    """
    In-memory index loader for graphify-out/graph.json.
    Provides targeted lookup of classes, functions, entrypoints, and callers/callees.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self.graph_path = os.path.join(self.workspace_root, "graphify-out", "graph.json")
        self._is_loaded = False
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._symbol_index: Dict[str, List[str]] = {}  # symbol_name_lower -> [node_ids]
        self._file_index: Dict[str, List[str]] = {}    # source_file -> [node_ids]
        self._callers: Dict[str, Set[str]] = {}        # target_node_id -> {source_node_ids}
        self._callees: Dict[str, Set[str]] = {}        # source_node_id -> {target_node_ids}
        self._communities: Dict[str, List[str]] = {}

    def ensure_loaded(self) -> bool:
        """Loads and indexes graph.json if available."""
        if self._is_loaded:
            return True
        if not os.path.exists(self.graph_path):
            logger.debug("Graphify graph.json not found at: %s", self.graph_path)
            return False

        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = data.get("nodes", [])
            links = data.get("links", data.get("edges", []))

            for n in nodes:
                nid = n.get("id", "")
                if not nid:
                    continue
                self._nodes[nid] = n

                label = n.get("label", "").lower()
                if label:
                    self._symbol_index.setdefault(label, []).append(nid)

                src = n.get("source_file", "")
                if src:
                    self._file_index.setdefault(src, []).append(nid)

                comm = n.get("community_name", "")
                if comm:
                    self._communities.setdefault(comm, []).append(nid)

            for link in links:
                src_id = link.get("source")
                tgt_id = link.get("target")
                rel = link.get("relation", "")
                if rel in ["calls", "imports", "depends_on", "implements"]:
                    if src_id and tgt_id:
                        self._callees.setdefault(src_id, set()).add(tgt_id)
                        self._callers.setdefault(tgt_id, set()).add(src_id)

            self._is_loaded = True
            logger.info("Graphify index loaded: %d nodes, %d relationships indexed.", len(self._nodes), len(links))
            return True
        except Exception as e:
            logger.warning("Failed to load Graphify graph.json: %s", e)
            return False

    def retrieve_bounded_context(
        self,
        query: str,
        max_tokens: Optional[int] = None,
        include_html: bool = False
    ) -> Tuple[str, List[str], List[str]]:
        """
        Retrieves targeted architectural symbols and source excerpts matching the query.
        Returns: (formatted_context_markdown, retrieved_files, retrieved_symbols)
        """
        budget = max_tokens or context_budget_manager.available_context
        retrieved_files: List[str] = []
        retrieved_symbols: List[str] = []

        if not self.ensure_loaded():
            fallback_msg = (
                "[KNOWLEDGE GRAPH INDEX]\n"
                "Note: Workspace graph index is not compiled. Referencing direct project files."
            )
            return fallback_msg, [], []

        # Identify key search terms from query
        query_lower = query.lower()
        terms = re.findall(r"[a-zA-Z0-9_\-\.]{3,}", query_lower)

        # Brain / Architecture core keywords if user asks "this is your brain" or general query
        if any(w in query_lower for w in ["brain", "architecture", "system", "overview", "core"]):
            terms.extend(["fridaybrain", "fridaymainwindow", "query_llm", "semanticrouter", "settings"])

        matched_node_ids: Set[str] = set()
        for term in terms:
            for symbol, nids in self._symbol_index.items():
                if term in symbol:
                    matched_node_ids.update(nids[:5])

        # Prioritize key architectural categories
        entrypoints: List[str] = []
        callers: List[str] = []
        callees: List[str] = []
        adapters: List[str] = []
        tools: List[str] = []

        for nid in list(matched_node_ids)[:30]:
            node = self._nodes.get(nid, {})
            label = node.get("label", nid)
            src_file = node.get("source_file", "")

            if "run_" in src_file or "app.py" in src_file or "main_window" in src_file:
                entrypoints.append(label)
            elif "engine" in src_file or "brain" in label.lower():
                adapters.append(label)
            elif "skill" in src_file or "tool" in label.lower():
                tools.append(label)

            for caller_id in list(self._callers.get(nid, set()))[:2]:
                cnode = self._nodes.get(caller_id)
                if cnode:
                    callers.append(f"{cnode.get('label')} -> {label}")
            for callee_id in list(self._callees.get(nid, set()))[:2]:
                cnode = self._nodes.get(callee_id)
                if cnode:
                    callees.append(f"{label} -> {cnode.get('label')}")

        # Assemble high-level symbol hierarchy
        lines: List[str] = [
            "### [F.R.I.D.A.Y. Architectural Index — Targeted Subsystem Retrieval]",
            f"**Query Focus:** `{query[:60]}`",
        ]

        if entrypoints:
            lines.append(f"- **Primary Entrypoints:** {', '.join(entrypoints[:4])}")
            retrieved_symbols.extend(entrypoints[:4])
        if adapters:
            lines.append(f"- **Neural / Model Adapters:** {', '.join(adapters[:4])}")
            retrieved_symbols.extend(adapters[:4])
        if tools:
            lines.append(f"- **Callable Tools & Skills:** {', '.join(tools[:4])}")
            retrieved_symbols.extend(tools[:4])

        if callers:
            lines.append("\n**Key Call Chains:**")
            for c in callers[:4]:
                lines.append(f"- `{c}`")

        # Now extract targeted source code windows (real source files, NOT JSON dumps)
        lines.append("\n**Targeted Source Excerpts:**")
        char_budget = int(budget * 3.5)
        current_chars = sum(len(l) for l in lines)

        # Select top relevant source files from matched nodes
        target_files: List[Tuple[str, str, int]] = []  # (source_file, label, start_line)
        for nid in matched_node_ids:
            node = self._nodes.get(nid, {})
            sf = node.get("source_file", "")
            loc = node.get("source_location", "")
            lbl = node.get("label", "")
            if sf and os.path.exists(os.path.join(self.workspace_root, sf)):
                line_no = 1
                if loc.startswith("L"):
                    try:
                        line_no = int(loc[1:])
                    except Exception:
                        line_no = 1
                target_files.append((sf, lbl, line_no))

        # Deduplicate files while preserving line targets
        seen_files: Set[str] = set()
        for sf, lbl, line_no in target_files:
            if sf in seen_files:
                continue
            seen_files.add(sf)
            retrieved_files.append(sf)

            excerpt = self._read_targeted_window(sf, line_no, window_size=35)
            if excerpt:
                snippet_block = f"\n```python\n# {sf} (around line {line_no} — {lbl})\n{excerpt}\n```"
                if current_chars + len(snippet_block) < char_budget:
                    lines.append(snippet_block)
                    current_chars += len(snippet_block)
                else:
                    lines.append(f"\n# Additional relevant file: {sf} (omitted to preserve token budget)")
                    break

            if len(seen_files) >= 4:
                break

        final_context = "\n".join(lines)
        return final_context, retrieved_files, retrieved_symbols

    def _read_targeted_window(self, rel_path: str, center_line: int, window_size: int = 35) -> str:
        """Reads a bounded window of lines around the target definition in the real source file."""
        abs_path = os.path.join(self.workspace_root, rel_path)
        if not os.path.exists(abs_path):
            return ""

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()

            total = len(all_lines)
            if total == 0:
                return ""

            start = max(0, center_line - 10)
            end = min(total, start + window_size)
            selected = all_lines[start:end]
            return "".join(selected).strip()
        except Exception as e:
            logger.debug("Failed to read window from %s: %s", rel_path, e)
            return ""


# Global singleton retriever instance
graphify_retriever = GraphifyIndexRetriever()
