"""
F.R.I.D.A.Y. 3.0 — Structured Document Agent Data Models
Defines schemas for DocumentMap, structural elements, edit operations, and verification results.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class DocEditOperation(str, Enum):
    READ = "read"
    SUMMARIZE = "summarize"
    ANSWER_QUESTION = "answer_question"
    FILL = "fill"
    REPLACE = "replace"
    APPEND = "append"
    INSERT = "insert"
    DELETE = "delete"
    EDIT = "edit"
    FORMAT = "format"
    GENERATE_CONTENT = "generate_content"
    SAVE_AS = "save_as"


class DocumentHeading(BaseModel):
    index: int
    level: int
    text: str
    paragraph_index: int


class DocumentParagraph(BaseModel):
    index: int
    text: str
    style: str = "Normal"
    heading_level: Optional[int] = None
    is_list_item: bool = False
    item_number: Optional[str] = None  # e.g., "12", "13", "12.", "12)", etc.
    char_count: int = 0


class DocumentCell(BaseModel):
    table_index: int
    row: int
    col: int
    text: str
    header_name: Optional[str] = None


class DocumentTable(BaseModel):
    index: int
    rows: int
    cols: int
    headers: List[str] = Field(default_factory=list)
    cells: List[DocumentCell] = Field(default_factory=list)
    preview_markdown: str = ""


class DocumentSection(BaseModel):
    index: int
    title: str
    start_paragraph: int
    end_paragraph: int


class DocumentMap(BaseModel):
    file_path: str
    file_name: str
    headings: List[DocumentHeading] = Field(default_factory=list)
    paragraphs: List[DocumentParagraph] = Field(default_factory=list)
    tables: List[DocumentTable] = Field(default_factory=list)
    sections: List[DocumentSection] = Field(default_factory=list)
    total_paragraphs: int = 0
    total_tables: int = 0
    total_words: int = 0
    estimated_tokens: int = 0

    def summary_metadata(self) -> str:
        """Compact structural summary for LLM context or status reporting (< 150 tokens)."""
        heading_titles = [f"H{h.level}: '{h.text}'" for h in self.headings[:8]]
        headings_preview = ", ".join(heading_titles) if heading_titles else "None"
        return (
            f"DOCX Structure for '{self.file_name}':\n"
            f"- Total Paragraphs: {self.total_paragraphs}\n"
            f"- Total Tables: {self.total_tables}\n"
            f"- Total Words: {self.total_words} (~{self.estimated_tokens} tokens)\n"
            f"- Key Headings: {headings_preview}"
        )

    @property
    def item_index_map(self) -> Dict[str, List[DocumentParagraph]]:
        mapping: Dict[str, List[DocumentParagraph]] = {}
        for p in self.paragraphs:
            if p.item_number:
                mapping.setdefault(p.item_number, []).append(p)
        return mapping


class RelevantRegion(BaseModel):
    target_query: str
    region_type: str = "paragraph"  # "paragraph", "table", "section", "ambiguous"
    paragraph_indices: List[int] = Field(default_factory=list)
    table_cell_targets: List[Dict[str, int]] = Field(default_factory=list)  # [{"table": 0, "row": 1, "col": 2}]
    context_text: str = ""
    context_token_estimate: int = 0
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    matched_labels: List[str] = Field(default_factory=list)  # e.g., ["Item 12", "Item 13"]

    @property
    def matched_paragraphs(self) -> List[int]:
        return self.paragraph_indices


class DocEditRequest(BaseModel):
    file_path: str
    target: str
    operation: DocEditOperation = DocEditOperation.EDIT
    content: Optional[str] = None
    output_path: Optional[str] = None


class DocEditResult(BaseModel):
    success: bool
    message: str
    file_path: str
    operation: str
    target_region: Optional[str] = None
    modified_content: Optional[str] = None
    tokens_used: int = 0
    verification: Dict[str, Any] = Field(default_factory=dict)
