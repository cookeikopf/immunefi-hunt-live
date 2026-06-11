"""SQLite-gestützter Vektorspeicher für RAG-Chunks.

Die Chunks liegen in derselben Datenbank wie die Geschäftsdaten —
für KMU-Größenordnungen (bis einige zehntausend Chunks) ist eine
Brute-Force-Cosinus-Suche völlig ausreichend und ohne Zusatzdienste
(keine Vektordatenbank nötig) betreibbar.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.database import Base
from ...core.tenancy import TenantMixin
from .embeddings import Embedder, cosine


class RagChunk(TenantMixin, Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)      # z. B. "knowledge", "crm"
    source_id: Mapped[str] = mapped_column(String(50), index=True)   # ID im Quellmodul
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def embedding(self) -> list[float]:
        return json.loads(self.embedding_json)


class VectorStore:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def add(self, db: Session, source: str, source_id: str, title: str, chunks: list[str]) -> int:
        for chunk in chunks:
            db.add(
                RagChunk(
                    source=source,
                    source_id=source_id,
                    title=title,
                    content=chunk,
                    embedding_json=json.dumps(self.embedder.embed(chunk)),
                )
            )
        db.commit()
        return len(chunks)

    def remove(self, db: Session, source: str, source_id: str) -> int:
        query = db.query(RagChunk).filter(
            RagChunk.source == source, RagChunk.source_id == source_id
        )
        # Expliziter Tenant-Filter zusätzlich zur zentralen Loader-Criteria —
        # Bulk-Deletes dürfen nie über Mandantengrenzen hinweg löschen.
        tenant_id = db.info.get("tenant_id")
        if tenant_id is not None:
            query = query.filter(RagChunk.tenant_id == tenant_id)
        deleted = query.delete()
        db.commit()
        return deleted

    def replace(self, db: Session, source: str, source_id: str, title: str, chunks: list[str]) -> int:
        self.remove(db, source, source_id)
        return self.add(db, source, source_id, title, chunks)

    def similarity_search(
        self, db: Session, query: str, top_k: int = 6
    ) -> list[tuple[RagChunk, float]]:
        query_vec = self.embedder.embed(query)
        chunk_query = db.query(RagChunk)
        tenant_id = db.info.get("tenant_id")
        if tenant_id is not None:  # Defense-in-Depth zusätzlich zur Loader-Criteria
            chunk_query = chunk_query.filter(RagChunk.tenant_id == tenant_id)
        scored = [
            (chunk, cosine(query_vec, chunk.embedding))
            for chunk in chunk_query.all()
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def count(self, db: Session) -> int:
        return db.query(RagChunk).count()
