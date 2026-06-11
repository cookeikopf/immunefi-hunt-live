from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AbsenceCreate(BaseModel):
    kind: str = "urlaub"
    start_date: date
    end_date: date
    note: str | None = None


class AbsenceOut(AbsenceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    created_at: datetime


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    role: str | None = None
    department: str | None = None
    email: str | None = None
    weekly_hours: float = 40.0
    vacation_days_per_year: int = 30
    hired_at: date | None = None
    active: bool = True


class EmployeeOut(EmployeeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    absences: list[AbsenceOut] = []
