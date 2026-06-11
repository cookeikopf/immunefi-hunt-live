from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.database import get_db
from .models import KnowledgeDocument
from .schemas import DocumentCreate, DocumentOut, DocumentUpdate

router = APIRouter(prefix="/api/knowledge", tags=["Wissen"])

ALLOWED_TYPES = {"sop", "regel", "dokument"}


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(doc_type: str | None = None, db: Session = Depends(get_db)):
    query = db.query(KnowledgeDocument)
    if doc_type:
        query = query.filter(KnowledgeDocument.doc_type == doc_type)
    return query.order_by(KnowledgeDocument.updated_at.desc()).all()


@router.post("/documents", response_model=DocumentOut, status_code=201)
def create_document(data: DocumentCreate, db: Session = Depends(get_db)):
    if data.doc_type not in ALLOWED_TYPES:
        raise HTTPException(422, f"doc_type muss eines von {sorted(ALLOWED_TYPES)} sein")
    doc = KnowledgeDocument(**data.model_dump())
    db.add(doc)
    db.commit()
    events.publish("knowledge.document.created", {"id": doc.id})
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    return doc


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: int, data: DocumentUpdate, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    changes = data.model_dump(exclude_unset=True)
    if changes:
        for field, value in changes.items():
            setattr(doc, field, value)
        doc.version += 1
    db.commit()
    events.publish("knowledge.document.updated", {"id": doc.id})
    return doc


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    db.delete(doc)
    db.commit()
    events.publish("knowledge.document.deleted", {"id": doc_id})
