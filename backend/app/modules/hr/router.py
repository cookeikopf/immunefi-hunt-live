from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.database import get_db
from .models import Absence, Employee
from .schemas import AbsenceCreate, AbsenceOut, EmployeeCreate, EmployeeOut

router = APIRouter(prefix="/api/hr", tags=["Personal"])


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).order_by(Employee.last_name).all()


@router.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    employee = Employee(**data.model_dump())
    db.add(employee)
    db.commit()
    events.publish("hr.employee.created", {"id": employee.id})
    return employee


@router.post("/employees/{employee_id}/absences", response_model=AbsenceOut, status_code=201)
def add_absence(employee_id: int, data: AbsenceCreate, db: Session = Depends(get_db)):
    if db.get(Employee, employee_id) is None:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    if data.end_date < data.start_date:
        raise HTTPException(422, "Enddatum liegt vor dem Startdatum")
    absence = Absence(employee_id=employee_id, **data.model_dump())
    db.add(absence)
    db.commit()
    events.publish("hr.absence.created", {"id": absence.id, "employee_id": employee_id})
    return absence
