"""Aktivierung von Builder-Entwürfen: materialisiert validierte
Definitionen als echte Objekte (Modul, Automation, Widget, Workflow)."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .definitions import parse_artifact
from .records import create_module_from_def, get_module, grant_default_permissions


def materialize(db: Session, kind: str, definition: dict) -> dict:
    """Validiert und aktiviert eine Definition. Liefert eine Kurzinfo."""
    try:
        artifact = parse_artifact(kind, definition)
    except Exception as exc:  # Pydantic-Fehler verständlich durchreichen
        raise HTTPException(422, f"Definition ungültig: {exc}")

    if kind == "module":
        if get_module(db, artifact.slug, include_archived=True) is not None:
            raise HTTPException(409, f"Modul '{artifact.slug}' existiert bereits")
        module = create_module_from_def(db, artifact)
        grant_default_permissions(db, module.slug)
        db.commit()
        return {"kind": "module", "slug": module.slug, "name": module.name_plural or module.name}

    if kind == "automation":
        from .automations import create_automation

        automation = create_automation(db, artifact)
        return {"kind": "automation", "id": automation.id, "name": automation.name}

    if kind == "widget":
        from .widgets import create_widget

        widget = create_widget(db, artifact)
        return {"kind": "widget", "id": widget.id, "title": widget.title}

    if kind == "workflow":
        from .workflows import create_workflow

        workflow = create_workflow(db, artifact)
        return {"kind": "workflow", "id": workflow.id, "name": workflow.name}

    raise HTTPException(422, f"Unbekannte Artefakt-Art: {kind}")
