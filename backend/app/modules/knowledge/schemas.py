from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    title: str
    doc_type: str = "dokument"  # sop | regel | dokument
    category: str | None = None
    content: str
    tags: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    doc_type: str | None = None
    category: str | None = None
    content: str | None = None
    tags: str | None = None


class DocumentOut(DocumentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    created_at: datetime
    updated_at: datetime
