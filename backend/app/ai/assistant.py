"""Firmen-Assistent: RAG-gestützter Chat über das gesamte Unternehmen.

Das ist der "firmeneigene LLM"-Baustein: Zu jeder Frage werden die
relevantesten Wissens-Chunks (SOPs, Regeln, Dokumente, Kunden-,
Projekt- und Personalkarten) aus dem RAG-Index geholt und zusammen mit
dem aktuellen Unternehmens-Schnappschuss als Kontext an Claude gegeben.
Der Assistent antwortet damit ausschließlich auf Basis der tatsächlichen
Firmendaten — Prozeduren, Regeln, Zahlen, Zuständigkeiten.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.tenancy import current_tenant
from . import llm
from .datahub import company_snapshot_text
from .rag.indexer import retriever
from .rag.retriever import RetrievedChunk

settings = get_settings()

_SYSTEM_TEMPLATE = """Du bist der interne KI-Assistent des Unternehmens "{company}".
Du kennst das Unternehmen über die bereitgestellten Kontextauszüge (Wissensdatenbank,
SOPs, Regeln, Kunden-, Projekt- und Personaldaten) sowie den Kennzahlen-Schnappschuss.

Regeln für deine Antworten:
- Antworte auf Deutsch, präzise und geschäftlich.
- Stütze dich ausschließlich auf den bereitgestellten Kontext. Wenn die Information
  dort nicht enthalten ist, sage das klar, statt zu raten.
- Verweise wo sinnvoll auf die Quelle (z. B. den Titel der SOP oder des Dokuments).
- Bei Fragen zu Prozessen: Gib die Schritte aus der jeweiligen SOP wieder.
- Behandle alle Daten vertraulich; sie verlassen das Unternehmen nicht."""


@dataclass
class AssistantAnswer:
    answer: str
    sources: list[RetrievedChunk]


def _build_context(snapshot: str, chunks: list[RetrievedChunk]) -> str:
    parts = [snapshot, "\nRelevante Auszüge aus den Unternehmensdaten:"]
    if not chunks:
        parts.append("(Keine passenden Einträge im Wissensindex gefunden.)")
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"\n[Quelle {i}: {chunk.title} ({chunk.source})]\n{chunk.content}")
    return "\n".join(parts)


def ask(
    db: Session,
    question: str,
    top_k: int | None = None,
    history: list[dict] | None = None,
) -> AssistantAnswer:
    chunks = retriever.retrieve(db, question, top_k or settings.rag_top_k)
    context = _build_context(company_snapshot_text(db), chunks)
    tenant = current_tenant(db)
    system = _SYSTEM_TEMPLATE.format(company=tenant.name if tenant else settings.company_name)
    user_message = f"Kontext:\n{context}\n\nFrage: {question}"
    answer = llm.complete(system, user_message, history=history)
    return AssistantAnswer(answer=answer, sources=chunks)
