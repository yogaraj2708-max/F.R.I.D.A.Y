"""
F.R.I.D.A.Y. 3.0 — Structured Document Parser & Relevant-Region Detector
Performs deep structural decomposition of DOCX files into a DocumentMap,
locates targeted regions (e.g., "from 12 to 13"), and enforces strict token budgeting.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

import docx
from docx.document import Document as DocxDocumentType

from friday_core.document.models import (
    DocumentMap,
    DocumentHeading,
    DocumentParagraph,
    DocumentTable,
    DocumentCell,
    DocumentSection,
    RelevantRegion
)

logger = logging.getLogger("FRIDAY.DocumentParser")


class DocxStructuralParser:
    """
    Deconstructs DOCX documents into structural components:
    paragraphs, headings, tables, cells, list items, and sections.
    """

    @classmethod
    def parse(cls, file_path: str) -> DocumentMap:
        """Parses a physical DOCX file into a structured DocumentMap."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DOCX file not found at: {file_path}")

        doc = docx.Document(file_path)
        file_name = os.path.basename(file_path)

        headings: List[DocumentHeading] = []
        paragraphs: List[DocumentParagraph] = []
        tables: List[DocumentTable] = []
        sections: List[DocumentSection] = []

        total_words = 0
        current_section_title = "Document Start"
        current_section_start = 0

        # 1. Parse Paragraphs & Headings
        for p_idx, p in enumerate(doc.paragraphs):
            text = (p.text or "").strip()
            style_name = p.style.name if p.style else "Normal"
            heading_level = None

            # Detect heading styles
            h_match = re.match(r"^Heading\s*(\d+)$", style_name, re.IGNORECASE)
            if h_match:
                heading_level = int(h_match.group(1))
            elif style_name.lower().startswith("heading"):
                heading_level = 1

            # Detect list item and numbering
            is_list = "list" in style_name.lower() or p.style.name.startswith("List")
            item_number = cls._extract_item_number(text)
            if item_number:
                is_list = True

            p_words = len(text.split()) if text else 0
            total_words += p_words

            doc_p = DocumentParagraph(
                index=p_idx,
                text=text,
                style=style_name,
                heading_level=heading_level,
                is_list_item=is_list,
                item_number=item_number,
                char_count=len(text)
            )
            paragraphs.append(doc_p)

            if heading_level is not None and text:
                headings.append(DocumentHeading(
                    index=len(headings),
                    level=heading_level,
                    text=text,
                    paragraph_index=p_idx
                ))
                # Close previous section
                if p_idx > current_section_start:
                    sections.append(DocumentSection(
                        index=len(sections),
                        title=current_section_title,
                        start_paragraph=current_section_start,
                        end_paragraph=p_idx - 1
                    ))
                current_section_title = text
                current_section_start = p_idx

        # Close final section
        if len(paragraphs) > current_section_start:
            sections.append(DocumentSection(
                index=len(sections),
                title=current_section_title,
                start_paragraph=current_section_start,
                end_paragraph=len(paragraphs) - 1
            ))

        # 2. Parse Tables
        for t_idx, t in enumerate(doc.tables):
            num_rows = len(t.rows)
            num_cols = len(t.columns) if num_rows > 0 else 0
            headers: List[str] = []
            cells: List[DocumentCell] = []
            md_lines: List[str] = []

            for r_idx, row in enumerate(t.rows):
                row_texts = [cell.text.strip() for cell in row.cells]
                if r_idx == 0:
                    headers = row_texts
                    md_lines.append("| " + " | ".join(headers) + " |")
                    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                else:
                    md_lines.append("| " + " | ".join(row_texts) + " |")

                for c_idx, cell in enumerate(row.cells):
                    header_name = headers[c_idx] if c_idx < len(headers) else None
                    cell_text = cell.text.strip()
                    total_words += len(cell_text.split()) if cell_text else 0
                    cells.append(DocumentCell(
                        table_index=t_idx,
                        row=r_idx,
                        col=c_idx,
                        text=cell_text,
                        header_name=header_name
                    ))

            tables.append(DocumentTable(
                index=t_idx,
                rows=num_rows,
                cols=num_cols,
                headers=headers,
                cells=cells,
                preview_markdown="\n".join(md_lines)
            ))

        estimated_tokens = int(total_words * 1.33)

        return DocumentMap(
            file_path=os.path.abspath(file_path),
            file_name=file_name,
            headings=headings,
            paragraphs=paragraphs,
            tables=tables,
            sections=sections,
            total_paragraphs=len(paragraphs),
            total_tables=len(tables),
            total_words=total_words,
            estimated_tokens=estimated_tokens
        )

    @staticmethod
    def _extract_item_number(text: str) -> Optional[str]:
        """Extracts numbered labels such as '12.', '12)', 'Item 12:', 'Section 12', '#12'."""
        if not text:
            return None
        # Pattern 1: Leading numbers "12." or "12)" or "12 - " or "12:"
        lead_match = re.match(r"^(\d{1,4})(?:[\.\)\:\-]\s*|\s+)", text)
        if lead_match:
            return lead_match.group(1)
        # Pattern 2: Keyword prefix "Item 12", "Section 12", "Clause 12", "Question 12"
        kw_match = re.match(r"^(?:item|section|clause|question|point|field|row|step|no\.?|#)\s*(\d{1,4})\b", text, re.IGNORECASE)
        if kw_match:
            return kw_match.group(1)
        return None

    @classmethod
    def find_relevant_region(cls, doc_map: DocumentMap, query: str) -> RelevantRegion:
        """
        Identifies the exact region relevant to the user query without sending the whole document.
        Supports range queries (e.g. 'fill this from 12 to 13') and single target queries.
        Enforces a hard context budget <= 1000 tokens.
        """
        clean_query = query.lower().strip()

        # Check for range: "from X to Y", "X to Y", "between X and Y"
        range_match = re.search(r"\b(?:from\s+)?(\d{1,4})\s+(?:to|through|-)\s+(\d{1,4})\b", clean_query)
        if range_match:
            start_num = range_match.group(1)
            end_num = range_match.group(2)
            return cls._locate_range_region(doc_map, query, start_num, end_num)

        # Check for single item: "item X", "section X", "number X", "paragraph X"
        single_match = re.search(r"\b(?:item|section|clause|question|point|field|row|step|number|no\.?|#)?\s*(\d{1,4})\b", clean_query)
        if single_match and single_match.group(1):
            num = single_match.group(1)
            return cls._locate_range_region(doc_map, query, num, num)

        # Check for table cell query: "table X row Y col Z", "in table"
        table_match = re.search(r"\btable\s*(\d+)?\b", clean_query)
        if table_match and doc_map.tables:
            t_idx = int(table_match.group(1)) - 1 if table_match.group(1) else 0
            if 0 <= t_idx < len(doc_map.tables):
                t = doc_map.tables[t_idx]
                return RelevantRegion(
                    target_query=query,
                    region_type="table",
                    table_cell_targets=[{"table": t_idx, "row": r, "col": c} for r in range(t.rows) for c in range(t.cols)],
                    context_text=t.preview_markdown[:3000],
                    context_token_estimate=min(800, int(len(t.preview_markdown) / 3.5)),
                    matched_labels=[f"Table {t_idx + 1}"]
                )

        # Check for heading search
        for h in doc_map.headings:
            if h.text.lower() in clean_query or any(w in h.text.lower() for w in clean_query.split() if len(w) > 4):
                # Extract this heading's section
                return cls._extract_section_around_paragraph(doc_map, query, h.paragraph_index, label=f"Heading '{h.text}'")

        # Fallback: ambiguous or undetermined
        return RelevantRegion(
            target_query=query,
            region_type="ambiguous",
            is_ambiguous=True,
            ambiguity_reason=f"Could not identify a specific target region in '{doc_map.file_name}' matching '{query}'.",
            context_text=doc_map.summary_metadata(),
            context_token_estimate=120
        )

    @classmethod
    def _locate_range_region(cls, doc_map: DocumentMap, query: str, start_num: str, end_num: str) -> RelevantRegion:
        """Locates numbered paragraph items or table rows matching range [start_num, end_num]."""
        start_val = int(start_num)
        end_val = int(end_num)
        if start_val > end_val:
            start_val, end_val = end_val, start_val

        target_nums = {str(i) for i in range(start_val, end_val + 1)}

        # 1. Search Paragraphs
        matched_p_indices: List[int] = []
        matched_labels: List[str] = []

        for p in doc_map.paragraphs:
            if p.item_number in target_nums:
                matched_p_indices.append(p.index)
                matched_labels.append(f"Item {p.item_number}")
            elif any(re.search(rf"\b{re.escape(n)}[\.\)\:\-\s]", p.text) for n in target_nums):
                matched_p_indices.append(p.index)
                matched_labels.append(f"Paragraph {p.index} (matches {target_nums})")

        # 2. Search Tables
        matched_table_cells: List[Dict[str, int]] = []
        for t in doc_map.tables:
            for cell in t.cells:
                cell_item = cls._extract_item_number(cell.text)
                if (cell_item and cell_item in target_nums) or any(cell.text.strip() == n for n in target_nums):
                    matched_table_cells.append({"table": cell.table_index, "row": cell.row, "col": cell.col})
                    matched_labels.append(f"Table {cell.table_index+1} R{cell.row}C{cell.col}")

        # Check Ambiguity: Found in both paragraphs AND tables?
        if matched_p_indices and matched_table_cells:
            return RelevantRegion(
                target_query=query,
                region_type="ambiguous",
                is_ambiguous=True,
                ambiguity_reason=(
                    f"Found references to '{start_num} to {end_num}' in both paragraph items "
                    f"and table cells in '{doc_map.file_name}'. Please clarify which element to update."
                ),
                matched_labels=matched_labels
            )

        # Check Ambiguity: Does any single target item number match multiple distinct paragraphs across sections?
        item_to_pids: Dict[str, List[int]] = {}
        for p_idx in matched_p_indices:
            p = doc_map.paragraphs[p_idx]
            k = p.item_number or str(p_idx)
            item_to_pids.setdefault(k, []).append(p_idx)

        multi_matches = {k: v for k, v in item_to_pids.items() if len(v) > 1}
        if multi_matches:
            return RelevantRegion(
                target_query=query,
                region_type="ambiguous",
                is_ambiguous=True,
                ambiguity_reason=(
                    f"Target item(s) {list(multi_matches.keys())} appear in multiple sections of '{doc_map.file_name}'. "
                    f"Please clarify which specific section or heading to target."
                ),
                matched_labels=matched_labels
            )

        # Matched in Paragraphs
        if matched_p_indices:
            start_idx = max(0, min(matched_p_indices) - 1)  # Include 1 preceding paragraph for context
            end_idx = min(len(doc_map.paragraphs) - 1, max(matched_p_indices) + 1)  # Include 1 succeeding paragraph

            context_lines = []
            for idx in range(start_idx, end_idx + 1):
                p = doc_map.paragraphs[idx]
                tag = f"[P{p.index}]"
                if p.index in matched_p_indices:
                    tag += " (TARGET)"
                context_lines.append(f"{tag}: {p.text}")

            context_text = "\n".join(context_lines)
            # Enforce hard context budget <= 3500 chars (~900 tokens)
            if len(context_text) > 3500:
                context_text = context_text[:3500] + "\n...[context bounded]"

            token_est = int(len(context_text) / 3.5)
            return RelevantRegion(
                target_query=query,
                region_type="paragraph",
                paragraph_indices=matched_p_indices,
                context_text=context_text,
                context_token_estimate=token_est,
                matched_labels=matched_labels,
                is_ambiguous=False
            )

        # Matched in Table Cells
        if matched_table_cells:
            t_idx = matched_table_cells[0]["table"]
            table = doc_map.tables[t_idx]
            return RelevantRegion(
                target_query=query,
                region_type="table",
                table_cell_targets=matched_table_cells,
                context_text=f"Table {t_idx + 1} Preview:\n{table.preview_markdown[:3000]}",
                context_token_estimate=min(800, int(len(table.preview_markdown) / 3.5)),
                matched_labels=matched_labels,
                is_ambiguous=False
            )

        # Neither found
        return RelevantRegion(
            target_query=query,
            region_type="ambiguous",
            is_ambiguous=True,
            ambiguity_reason=f"Could not locate items or fields '{start_num} to {end_num}' in '{doc_map.file_name}'.",
            matched_labels=[]
        )

    @classmethod
    def _extract_section_around_paragraph(cls, doc_map: DocumentMap, query: str, p_idx: int, label: str) -> RelevantRegion:
        """Extracts context surrounding a specific paragraph index."""
        start_idx = max(0, p_idx - 1)
        end_idx = min(len(doc_map.paragraphs) - 1, p_idx + 4)
        lines = [f"[P{doc_map.paragraphs[i].index}]: {doc_map.paragraphs[i].text}" for i in range(start_idx, end_idx + 1)]
        context = "\n".join(lines)[:3000]
        return RelevantRegion(
            target_query=query,
            region_type="section",
            paragraph_indices=[p_idx],
            context_text=context,
            context_token_estimate=int(len(context) / 3.5),
            matched_labels=[label],
            is_ambiguous=False
        )
