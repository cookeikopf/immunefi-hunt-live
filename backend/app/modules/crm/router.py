from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.database import get_db
from .models import Customer, Interaction
from .schemas import (
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    InteractionCreate,
    InteractionOut,
)

router = APIRouter(prefix="/api/crm", tags=["CRM"])


def _get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Kunde nicht gefunden")
    return customer


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.name).all()


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    events.publish("crm.customer.created", {"id": customer.id})
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return _get_customer(db, customer_id)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerUpdate, db: Session = Depends(get_db)):
    customer = _get_customer(db, customer_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    events.publish("crm.customer.updated", {"id": customer.id})
    return customer


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    db.delete(_get_customer(db, customer_id))
    db.commit()
    events.publish("crm.customer.deleted", {"id": customer_id})


@router.post(
    "/customers/{customer_id}/interactions",
    response_model=InteractionOut,
    status_code=201,
)
def add_interaction(customer_id: int, data: InteractionCreate, db: Session = Depends(get_db)):
    _get_customer(db, customer_id)
    interaction = Interaction(customer_id=customer_id, **data.model_dump())
    db.add(interaction)
    db.commit()
    events.publish("crm.interaction.created", {"id": interaction.id, "customer_id": customer_id})
    return interaction
