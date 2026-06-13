from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class InvoiceCreate(BaseModel):
    number: str
    customer_id: int | None = None
    description: str | None = None
    amount_net: float
    vat_rate: float = 19.0
    issue_date: date
    due_date: date | None = None
    status: str = "offen"


class InvoiceUpdate(BaseModel):
    description: str | None = None
    amount_net: float | None = None
    vat_rate: float | None = None
    due_date: date | None = None
    status: str | None = None


class InvoiceOut(InvoiceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount_gross: float
    created_at: datetime


class ExpenseCreate(BaseModel):
    category: str
    description: str | None = None
    amount_net: float
    expense_date: date


class ExpenseOut(ExpenseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
