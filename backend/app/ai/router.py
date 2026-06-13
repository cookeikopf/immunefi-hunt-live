"""API-Endpunkte der KI-Schicht: Chat, Suche, Insights, Index-Verwaltung."""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..modules.auth.deps import get_current_user, get_tenant_db, require_module
from ..modules.auth.models import User
from . import llm
from . import models as _ai_models  # noqa: F401 — registriert AiConversation/AiMessage/KpiSnapshot auf Base.metadata
from .assistant import ask
from .datahub import collect_kpis
from .insights import generate_insights
from .rag.indexer import reindex_all, retriever, vector_store

router = APIRouter(
    prefix="/api/ai", dependencies=[Depends(require_module("ai"))], tags=["KI"]
)


class ChatRequest(BaseModel):
    question: str
    top_k: int | None = None
    conversation_id: int | None = None  # bestehende Unterhaltung fortsetzen


HISTORY_TURNS = 10  # letzte Runden, die in den Prompt einfließen


class SearchRequest(BaseModel):
    query: str
    top_k: int = 6


@router.get("/status")
def ai_status(db: Session = Depends(get_tenant_db)):
    return {
        "llm_available": llm.is_available(),
        "indexed_chunks": vector_store.count(db),
    }


@router.get("/kpis")
def kpis(db: Session = Depends(get_tenant_db)):
    return collect_kpis(db)


@router.post("/chat")
def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    from fastapi import HTTPException

    from .models import AiConversation, AiMessage

    conversation = None
    history: list[dict] = []
    if request.conversation_id is not None:
        conversation = (
            db.query(AiConversation)
            .filter(AiConversation.id == request.conversation_id,
                    AiConversation.user_id == user.id)
            .first()
        )
        if conversation is None:
            raise HTTPException(404, "Unterhaltung nicht gefunden")
        history = [
            {"role": m.role, "content": m.content}
            for m in conversation.messages[-(HISTORY_TURNS * 2):]
        ]

    result = ask(db, request.question, request.top_k, history=history)

    if conversation is None:
        conversation = AiConversation(
            user_id=user.id,
            title=request.question[:80] + ("…" if len(request.question) > 80 else ""),
        )
        db.add(conversation)
        db.flush()
    db.add(AiMessage(conversation_id=conversation.id, role="user", content=request.question))
    db.add(AiMessage(conversation_id=conversation.id, role="assistant", content=result.answer))
    db.commit()

    return {
        "answer": result.answer,
        "sources": [asdict(s) for s in result.sources],
        "conversation_id": conversation.id,
        "ai_available": llm.is_available(),
    }


@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_tenant_db)
):
    from .models import AiConversation

    conversations = (
        db.query(AiConversation)
        .filter(AiConversation.user_id == user.id)
        .order_by(AiConversation.updated_at.desc())
        .limit(30)
        .all()
    )
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in conversations]


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    from fastapi import HTTPException

    from .models import AiConversation

    conversation = (
        db.query(AiConversation)
        .filter(AiConversation.id == conversation_id, AiConversation.user_id == user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(404, "Unterhaltung nicht gefunden")
    return {
        "id": conversation.id,
        "title": conversation.title,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in conversation.messages
        ],
    }


@router.post("/weekly-report")
def weekly_report(db: Session = Depends(get_tenant_db)):
    from .reports import generate_weekly_report

    return generate_weekly_report(db)


@router.post("/search")
def search(request: SearchRequest, db: Session = Depends(get_tenant_db)):
    """Reine RAG-Suche ohne LLM — zeigt, welches Wissen gefunden wird."""
    return {"results": [asdict(c) for c in retriever.retrieve(db, request.query, request.top_k)]}


@router.get("/insights")
def insights(db: Session = Depends(get_tenant_db)):
    return generate_insights(db)


@router.post("/reindex")
def reindex(db: Session = Depends(get_tenant_db)):
    counts = reindex_all(db)
    return {"reindexed": counts, "total_chunks": vector_store.count(db)}
