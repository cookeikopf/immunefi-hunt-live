from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.tenancy import tenant_get
from ..auth.deps import get_tenant_db, require_module
from .models import KnowledgeDocument
from .schemas import DocumentCreate, DocumentOut, DocumentUpdate

router = APIRouter(prefix="/api/knowledge", dependencies=[Depends(require_module("knowledge"))], tags=["Wissen"])

ALLOWED_TYPES = {"sop", "regel", "dokument"}


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(doc_type: str | None = None, db: Session = Depends(get_tenant_db)):
    query = db.query(KnowledgeDocument)
    if doc_type:
        query = query.filter(KnowledgeDocument.doc_type == doc_type)
    return query.order_by(KnowledgeDocument.updated_at.desc()).all()


@router.post("/documents", response_model=DocumentOut, status_code=201)
def create_document(data: DocumentCreate, db: Session = Depends(get_tenant_db)):
    if data.doc_type not in ALLOWED_TYPES:
        raise HTTPException(422, f"doc_type muss eines von {sorted(ALLOWED_TYPES)} sein")
    doc = KnowledgeDocument(**data.model_dump())
    db.add(doc)
    db.commit()
    events.publish("knowledge.document.created", {"tenant_id": db.info.get("tenant_id"), "id": doc.id})
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_tenant_db)):
    doc = tenant_get(db, KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    return doc


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: int, data: DocumentUpdate, db: Session = Depends(get_tenant_db)):
    doc = tenant_get(db, KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    changes = data.model_dump(exclude_unset=True)
    if changes:
        for field, value in changes.items():
            setattr(doc, field, value)
        doc.version += 1
    db.commit()
    events.publish("knowledge.document.updated", {"tenant_id": db.info.get("tenant_id"), "id": doc.id})
    return doc


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_tenant_db)):
    doc = tenant_get(db, KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    db.delete(doc)
    db.commit()
    events.publish("knowledge.document.deleted", {"tenant_id": db.info.get("tenant_id"), "id": doc_id})
