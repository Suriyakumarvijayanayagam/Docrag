from typing import List, Optional, Union

from pydantic import BaseModel


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int
    unit_type: str
    unit_count: int
    structured_fact_count: int
    figure_count: int


class DocumentSummary(BaseModel):
    """A document already in the tenant, as recovered from storage."""
    doc_id: str
    filename: str
    chunk_count: int
    structured_fact_count: int
    figure_count: int


class QuestionRequest(BaseModel):
    user_id: str
    project_id: str
    question: str


class SourceRef(BaseModel):
    file: Optional[str]
    locator: Optional[Union[int, str]]
    relevance: Union[float, str]
    # the cited passage, used to highlight it in the source document
    snippet: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    sources: List[SourceRef]
    confidence: str  # "high" | "medium" | "low" | "none"


class DiagramRequest(BaseModel):
    user_id: str
    project_id: str
    request: str  # e.g. "block diagram of the power subsystem"


class DiagramResponse(BaseModel):
    mermaid: str = ""
    existing_figure_path: Optional[str] = None
    existing_figure_caption: Optional[str] = None
    source: str = "generated"


class ProjectStatus(BaseModel):
    user_id: str
    project_id: str
    document_count: int
    memory_entry_count: int
