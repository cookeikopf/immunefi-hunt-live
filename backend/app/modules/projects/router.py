from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import events
from ...core.tenancy import tenant_get
from ..auth.deps import get_tenant_db, require_module
from .models import Project, Task
from .schemas import ProjectCreate, ProjectOut, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_module("projects"))], tags=["Projekte"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_tenant_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_tenant_db)):
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    events.publish("projects.project.created", {"tenant_id": db.info.get("tenant_id"), "id": project.id})
    return project


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(project_id: int, data: TaskCreate, db: Session = Depends(get_tenant_db)):
    if tenant_get(db, Project, project_id) is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    task = Task(project_id=project_id, **data.model_dump())
    db.add(task)
    db.commit()
    events.publish("projects.task.created", {"tenant_id": db.info.get("tenant_id"), "id": task.id, "project_id": project_id})
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskUpdate, db: Session = Depends(get_tenant_db)):
    task = tenant_get(db, Task, task_id)
    if task is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    events.publish("projects.task.updated", {"tenant_id": db.info.get("tenant_id"), "id": task.id})
    return task
