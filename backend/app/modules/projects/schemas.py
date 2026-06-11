from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    title: str
    assignee_id: int | None = None
    status: str = "offen"
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    assignee_id: int | None = None
    status: str | None = None
    due_date: date | None = None


class TaskOut(TaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str
    customer_id: int | None = None
    description: str | None = None
    status: str = "aktiv"
    budget: float | None = None
    deadline: date | None = None


class ProjectOut(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    tasks: list[TaskOut] = []
