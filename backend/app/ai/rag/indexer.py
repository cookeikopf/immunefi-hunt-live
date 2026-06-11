"""RAG-Indexer: hält den Vektorspeicher synchron mit den Geschäftsdaten.

Zwei Wege halten den Index aktuell:
1. Event-getrieben: Der Indexer abonniert die Domänen-Ereignisse aller
   Module und reindexiert betroffene Objekte sofort.
2. Voll-Reindex: ``reindex_all`` baut den kompletten Index neu auf
   (z. B. nach Datenimporten), erreichbar über POST /api/ai/reindex.

Indexiert werden nicht nur Wissensdokumente, sondern auch strukturierte
Geschäftsdaten (Kunden, Projekte, Mitarbeiterprofile) als Textkarten —
so kennt der Firmen-Assistent das gesamte Unternehmen.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from ...core import events
from ...core.config import get_settings
from ...core.database import SessionLocal
from ...modules.crm.models import Customer
from ...modules.hr.models import Employee
from ...modules.knowledge.models import KnowledgeDocument
from ...modules.projects.models import Project
from .chunking import chunk_text
from .embeddings import HashingEmbedder
from .retriever import HybridRetriever
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

settings = get_settings()

embedder = HashingEmbedder(dim=settings.embedding_dim)
vector_store = VectorStore(embedder)
retriever = HybridRetriever(vector_store)


# ---- Text-Repräsentationen strukturierter Daten ----

def _customer_card(c: Customer) -> str:
    parts = [f"Kunde: {c.name} (Status: {c.status})"]
    if c.industry:
        parts.append(f"Branche: {c.industry}")
    if c.email or c.phone:
        parts.append(f"Kontakt: {c.email or ''} {c.phone or ''}".strip())
    if c.notes:
        parts.append(f"Notizen: {c.notes}")
    for i in c.interactions[-5:]:
        parts.append(f"Interaktion ({i.kind}, {i.created_at.date()}): {i.summary}")
    return "\n".join(parts)


def _project_card(p: Project) -> str:
    parts = [f"Projekt: {p.name} (Status: {p.status})"]
    if p.description:
        parts.append(p.description)
    if p.budget:
        parts.append(f"Budget: {p.budget:.2f} EUR")
    if p.deadline:
        parts.append(f"Deadline: {p.deadline.isoformat()}")
    open_tasks = [t for t in p.tasks if t.status != "erledigt"]
    if open_tasks:
        parts.append("Offene Aufgaben: " + "; ".join(t.title for t in open_tasks[:10]))
    return "\n".join(parts)


def _employee_card(e: Employee) -> str:
    parts = [f"Mitarbeiter: {e.first_name} {e.last_name}"]
    if e.role:
        parts.append(f"Rolle: {e.role}")
    if e.department:
        parts.append(f"Abteilung: {e.department}")
    parts.append(f"Wochenstunden: {e.weekly_hours}, Urlaubstage/Jahr: {e.vacation_days_per_year}")
    return "\n".join(parts)


# ---- Indexierung ----

def index_document(db: Session, doc: KnowledgeDocument) -> int:
    text = f"{doc.title}\n\n{doc.content}"
    chunks = chunk_text(text, settings.rag_chunk_size, settings.rag_chunk_overlap)
    return vector_store.replace(db, "knowledge", str(doc.id), doc.title, chunks)


def reindex_all(db: Session) -> dict[str, int]:
    """Baut den RAG-Index des aktuellen Mandanten neu auf."""
    from .vectorstore import RagChunk

    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise RuntimeError("reindex_all benötigt eine mandanten-gebundene Session")
    db.query(RagChunk).filter(RagChunk.tenant_id == tenant_id).delete()
    db.commit()

    counts = {"knowledge": 0, "crm": 0, "projects": 0, "hr": 0}
    for doc in db.query(KnowledgeDocument).all():
        counts["knowledge"] += index_document(db, doc)
    for customer in db.query(Customer).all():
        counts["crm"] += vector_store.add(
            db, "crm", str(customer.id), f"Kunde: {customer.name}",
            chunk_text(_customer_card(customer), settings.rag_chunk_size, settings.rag_chunk_overlap),
        )
    for project in db.query(Project).all():
        counts["projects"] += vector_store.add(
            db, "projects", str(project.id), f"Projekt: {project.name}",
            chunk_text(_project_card(project), settings.rag_chunk_size, settings.rag_chunk_overlap),
        )
    for employee in db.query(Employee).all():
        counts["hr"] += vector_store.add(
            db, "hr", str(employee.id), f"Mitarbeiter: {employee.first_name} {employee.last_name}",
            chunk_text(_employee_card(employee), settings.rag_chunk_size, settings.rag_chunk_overlap),
        )
    return counts


# ---- Event-Handler: Index automatisch aktuell halten ----

_SOURCE_LOADERS = {
    "knowledge.document": (KnowledgeDocument, "knowledge", lambda o: f"{o.title}\n\n{o.content}", lambda o: o.title),
    "crm.customer": (Customer, "crm", _customer_card, lambda o: f"Kunde: {o.name}"),
    "projects.project": (Project, "projects", _project_card, lambda o: f"Projekt: {o.name}"),
    "hr.employee": (Employee, "hr", _employee_card, lambda o: f"Mitarbeiter: {o.first_name} {o.last_name}"),
}


def _on_event(event: str, payload: dict[str, Any]) -> None:
    # Ereignisformat: "<modul>.<objekt>.<aktion>"
    prefix, _, action = event.rpartition(".")
    spec = _SOURCE_LOADERS.get(prefix)
    if spec is None or "id" not in payload:
        return
    if payload.get("tenant_id") is None:
        logger.warning("Event %s ohne tenant_id — Indexierung übersprungen", event)
        return
    model, source, to_text, to_title = spec
    db = SessionLocal()
    db.info["tenant_id"] = payload["tenant_id"]
    try:
        if action == "deleted":
            vector_store.remove(db, source, str(payload["id"]))
            return
        obj = db.query(model).filter(model.id == payload["id"]).first()
        if obj is None:
            return
        chunks = chunk_text(to_text(obj), settings.rag_chunk_size, settings.rag_chunk_overlap)
        vector_store.replace(db, source, str(payload["id"]), to_title(obj), chunks)
        logger.info("RAG-Index aktualisiert: %s #%s (%d Chunks)", source, payload["id"], len(chunks))
    finally:
        db.close()


def register_event_handlers() -> None:
    events.subscribe("*", _on_event)
