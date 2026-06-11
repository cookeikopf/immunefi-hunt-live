"""API-Endpunkte der KI-Schicht: Chat, Suche, Insights, Index-Verwaltung."""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from . import llm
from .assistant import ask
from .datahub import collect_kpis
from .insights import generate_insights
from .rag.indexer import reindex_all, retriever, vector_store

router = APIRouter(prefix="/api/ai", tags=["KI"])


class ChatRequest(BaseModel):
    question: str
    top_k: int | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 6


@router.get("/status")
def ai_status(db: Session = Depends(get_db)):
    return {
        "llm_available": llm.is_available(),
        "indexed_chunks": vector_store.count(db),
    }


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    return collect_kpis(db)


@router.post("/chat")
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    result = ask(db, request.question, request.top_k)
    return {
        "answer": result.answer,
        "sources": [asdict(s) for s in result.sources],
        "ai_available": llm.is_available(),
    }


@router.post("/search")
def search(request: SearchRequest, db: Session = Depends(get_db)):
    """Reine RAG-Suche ohne LLM — zeigt, welches Wissen gefunden wird."""
    return {"results": [asdict(c) for c in retriever.retrieve(db, request.query, request.top_k)]}


@router.get("/insights")
def insights(db: Session = Depends(get_db)):
    return generate_insights(db)


@router.post("/reindex")
def reindex(db: Session = Depends(get_db)):
    counts = reindex_all(db)
    return {"reindexed": counts, "total_chunks": vector_store.count(db)}
