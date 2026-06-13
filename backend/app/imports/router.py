"""CSV-Import für Kunden und Rechnungen.

Erwartete Spalten (Kopfzeile, Trennzeichen ; oder , — wird erkannt):
- Kunden:    name*, industry, email, phone, address, status, notes
- Rechnungen: number*, amount_net*, issue_date* (JJJJ-MM-TT), due_date,
              vat_rate, status, customer_name (wird angelegt, falls unbekannt)
"""

import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core import events
from ..modules.auth.deps import get_tenant_db, require_module
from ..modules.crm.models import Customer
from ..modules.finance.models import Invoice
from .models import ImportJob

router = APIRouter(prefix="/api/imports", tags=["Import"])


def _read_csv(file: UploadFile) -> list[dict]:
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    delimiter = ";" if text.splitlines()[0].count(";") >= text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [
        { (k or "").strip().lower(): (v or "").strip() for k, v in row.items() }
        for row in reader
    ]


def _finish_job(db: Session, kind: str, filename: str, total: int,
                imported: int, errors: list[dict]) -> dict:
    job = ImportJob(
        kind=kind, filename=filename, total_rows=total,
        imported=imported, errors_json=json.dumps(errors, ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    return {"job_id": job.id, "total": total, "imported": imported, "errors": errors}


@router.post("/customers", dependencies=[Depends(require_module("crm"))])
def import_customers(file: UploadFile, db: Session = Depends(get_tenant_db)):
    rows = _read_csv(file)
    if not rows:
        raise HTTPException(422, "CSV ist leer oder hat keine Kopfzeile")

    imported, errors, pending_events = 0, [], []
    for index, row in enumerate(rows, start=2):  # Zeile 1 = Kopfzeile
        name = row.get("name", "")
        if not name:
            errors.append({"row": index, "error": "Spalte 'name' fehlt oder ist leer"})
            continue
        if db.query(Customer).filter(Customer.name == name).first():
            errors.append({"row": index, "error": f"Kunde '{name}' existiert bereits"})
            continue
        customer = Customer(
            name=name,
            industry=row.get("industry") or None,
            email=row.get("email") or None,
            phone=row.get("phone") or None,
            address=row.get("address") or None,
            status=row.get("status") or "lead",
            notes=row.get("notes") or None,
        )
        db.add(customer)
        db.flush()
        pending_events.append(("crm.customer.created", customer.id))
        imported += 1
    db.commit()
    # Events erst nach dem Commit — Handler arbeiten mit eigenen Sessions
    for event, object_id in pending_events:
        events.publish(event, {"tenant_id": db.info.get("tenant_id"), "id": object_id})
    return _finish_job(db, "customers", file.filename or "kunden.csv", len(rows), imported, errors)


@router.post("/invoices", dependencies=[Depends(require_module("finance"))])
def import_invoices(file: UploadFile, db: Session = Depends(get_tenant_db)):
    rows = _read_csv(file)
    if not rows:
        raise HTTPException(422, "CSV ist leer oder hat keine Kopfzeile")

    imported, errors, pending_events = 0, [], []
    for index, row in enumerate(rows, start=2):
        try:
            number = row.get("number", "")
            if not number:
                raise ValueError("Spalte 'number' fehlt oder ist leer")
            if db.query(Invoice).filter(Invoice.number == number).first():
                raise ValueError(f"Rechnungsnummer '{number}' existiert bereits")
            amount_net = float(row.get("amount_net", "").replace(",", "."))
            issue_date = date.fromisoformat(row["issue_date"])
            due_date = date.fromisoformat(row["due_date"]) if row.get("due_date") else None
            vat_rate = float(row.get("vat_rate", "19").replace(",", ".") or 19)

            customer_id = None
            customer_name = row.get("customer_name", "")
            if customer_name:
                customer = db.query(Customer).filter(Customer.name == customer_name).first()
                if customer is None:
                    customer = Customer(name=customer_name, status="aktiv")
                    db.add(customer)
                    db.flush()
                    pending_events.append(("crm.customer.created", customer.id))
                customer_id = customer.id

            invoice = Invoice(
                number=number, customer_id=customer_id, amount_net=amount_net,
                vat_rate=vat_rate, issue_date=issue_date, due_date=due_date,
                status=row.get("status") or "offen",
                description=row.get("description") or None,
            )
            db.add(invoice)
            db.flush()
            pending_events.append(("finance.invoice.created", invoice.id))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append({"row": index, "error": str(exc)})
    db.commit()
    # Events erst nach dem Commit — Handler arbeiten mit eigenen Sessions
    for event, object_id in pending_events:
        events.publish(event, {"tenant_id": db.info.get("tenant_id"), "id": object_id})
    return _finish_job(db, "invoices", file.filename or "rechnungen.csv", len(rows), imported, errors)


@router.get("/jobs", dependencies=[Depends(require_module("admin"))])
def list_jobs(db: Session = Depends(get_tenant_db)):
    jobs = db.query(ImportJob).order_by(ImportJob.created_at.desc()).limit(50).all()
    return [
        {"id": j.id, "kind": j.kind, "filename": j.filename, "total": j.total_rows,
         "imported": j.imported, "errors": j.errors, "created_at": j.created_at}
        for j in jobs
    ]
