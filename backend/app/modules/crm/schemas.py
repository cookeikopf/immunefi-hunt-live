from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InteractionCreate(BaseModel):
    kind: str = "notiz"
    summary: str


class InteractionOut(InteractionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    created_at: datetime


class CustomerCreate(BaseModel):
    name: str
    industry: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: str = "lead"
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: str | None = None
    notes: str | None = None


class CustomerOut(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    interactions: list[InteractionOut] = []
