from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    """Document metadata returned to the frontend."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: str


class DocumentUploadResponse(BaseModel):
    """Response body returned after a document is uploaded and indexed."""

    success: bool = True
    document: DocumentSummary


class DocumentListResponse(BaseModel):
    """Response body returned when listing uploaded documents."""

    success: bool = True
    documents: list[DocumentSummary]


class DocumentDeleteResponse(BaseModel):
    """Response body returned after deleting a document."""

    success: bool = True
    document_id: str
    message: str


class DocumentAskRequest(BaseModel):
    """Request body for document-scoped question answering."""

    question: str = Field(..., min_length=1, max_length=4000)
    model: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=5, ge=1, le=10)


class DocumentChunkReference(BaseModel):
    """Chunk snippet used as evidence for a document answer."""

    chunk_index: int
    content: str
    score: float


class DocumentAskResponse(BaseModel):
    """Response body returned by document question answering."""

    success: bool = True
    document_id: str
    answer: str
    model: str
    chunks: list[DocumentChunkReference]
