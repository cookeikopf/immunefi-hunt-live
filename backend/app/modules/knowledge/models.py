"""Wissensmodul: Dokumente, Prozeduren (SOPs) und Unternehmensregeln.

Dieses Modul ist die wichtigste Quelle für das firmeneigene KI-Wissen:
Alles, was hier abgelegt wird, fließt automatisch in den RAG-Index ein.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    # sop = Standardarbeitsanweisung, regel = Unternehmensregel,
    # dokument = sonstiges Wissen (Handbücher, Protokolle, FAQs …)
    doc_type: Mapped[str] = mapped_column(String(20), default="dokument", index=True)
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(300))  # kommagetrennt
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
