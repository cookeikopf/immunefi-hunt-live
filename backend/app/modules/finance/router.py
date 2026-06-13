from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.tenancy import tenant_get
from ..auth.deps import get_tenant_db, require_module
from .models import Expense, Invoice
from .schemas import ExpenseCreate, ExpenseOut, InvoiceCreate, InvoiceOut, InvoiceUpdate

router = APIRouter(prefix="/api/finance", dependencies=[Depends(require_module("finance"))], tags=["Finanzen"])


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(status: str | None = None, db: Session = Depends(get_tenant_db)):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    return query.order_by(Invoice.issue_date.desc()).all()


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_tenant_db)):
    if db.query(Invoice).filter(Invoice.number == data.number).first():
        raise HTTPException(409, "Rechnungsnummer existiert bereits")
    invoice = Invoice(**data.model_dump())
    db.add(invoice)
    db.commit()
    events.publish("finance.invoice.created", {"tenant_id": db.info.get("tenant_id"), "id": invoice.id})
    return invoice


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: int, data: InvoiceUpdate, db: Session = Depends(get_tenant_db)):
    invoice = tenant_get(db, Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "Rechnung nicht gefunden")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    db.commit()
    events.publish("finance.invoice.updated", {"tenant_id": db.info.get("tenant_id"), "id": invoice.id})
    return invoice


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(db: Session = Depends(get_tenant_db)):
    return db.query(Expense).order_by(Expense.expense_date.desc()).all()


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(data: ExpenseCreate, db: Session = Depends(get_tenant_db)):
    expense = Expense(**data.model_dump())
    db.add(expense)
    db.commit()
    events.publish("finance.expense.created", {"tenant_id": db.info.get("tenant_id"), "id": expense.id})
    return expense
