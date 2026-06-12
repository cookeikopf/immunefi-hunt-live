"""Builder-API: Custom-Module verwalten + generische Record-CRUD.

- /api/builder/modules: Module anlegen/ändern/archivieren (Recht: builder)
- /api/custom/modules: Modul-Metadaten für UI/Navigation (Recht: custom:<slug> read)
- /api/custom/{slug}/records: CRUD mit dynamischer Validierung (Recht: custom:<slug>)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core import events
from ..modules.auth.deps import (
    READ_METHODS,
    get_current_user,
    get_tenant_db,
    has_permission,
    require_module,
)
from ..modules.auth.models import User
from .definitions import ModuleDef
from .models import CustomField, CustomModule, CustomRecord
from .records import (
    RecordValidationError,
    create_module_from_def,
    get_module,
    grant_default_permissions,
    record_card,
    validate_values,
)

router = APIRouter(
    prefix="/api/builder", dependencies=[Depends(require_module("builder"))], tags=["Builder"]
)
records_router = APIRouter(prefix="/api/custom", tags=["Custom-Module"])


def _module_out(module: CustomModule) -> dict:
    return {
        "id": module.id,
        "slug": module.slug,
        "name": module.name,
        "name_plural": module.name_plural,
        "description": module.description,
        "status": module.status,
        "version": module.version,
        "fields": [
            {
                "name": f.name, "label": f.label, "field_type": f.field_type,
                "required": f.required, "options": f.options or [],
                "reference_target": f.reference_target, "show_in_list": f.show_in_list,
            }
            for f in module.fields
        ],
    }


def _record_out(record: CustomRecord) -> dict:
    return {
        "id": record.id, "values": record.values,
        "created_at": record.created_at, "updated_at": record.updated_at,
    }


# ---- Modulverwaltung (Recht: builder) ----

@router.get("/modules")
def list_modules(db: Session = Depends(get_tenant_db)):
    return [_module_out(m) for m in db.query(CustomModule).order_by(CustomModule.name).all()]


@router.post("/modules", status_code=201)
def create_module(module_def: ModuleDef, db: Session = Depends(get_tenant_db)):
    if get_module(db, module_def.slug, include_archived=True) is not None:
        raise HTTPException(409, f"Modul '{module_def.slug}' existiert bereits")
    module = create_module_from_def(db, module_def)
    grant_default_permissions(db, module.slug)
    db.commit()
    return _module_out(module)


@router.patch("/modules/{slug}")
def update_module(slug: str, module_def: ModuleDef, db: Session = Depends(get_tenant_db)):
    module = get_module(db, slug)
    if module is None:
        raise HTTPException(404, "Modul nicht gefunden")
    if module_def.slug != slug:
        raise HTTPException(422, "Der Slug eines Moduls kann nicht geändert werden")
    module.name = module_def.name
    module.name_plural = module_def.name_plural or module_def.name
    module.description = module_def.description
    module.version += 1
    db.query(CustomField).filter(CustomField.module_id == module.id).delete()
    for position, field_def in enumerate(module_def.fields):
        db.add(CustomField(
            module_id=module.id, name=field_def.name, label=field_def.label,
            field_type=field_def.field_type, required=field_def.required,
            options=field_def.options or None, reference_target=field_def.reference_target,
            show_in_list=field_def.show_in_list, position=position,
        ))
    db.commit()
    db.refresh(module)
    return _module_out(module)


@router.delete("/modules/{slug}", status_code=204)
def archive_module(slug: str, db: Session = Depends(get_tenant_db)):
    module = get_module(db, slug)
    if module is None:
        raise HTTPException(404, "Modul nicht gefunden")
    module.status = "archiviert"
    from ..ai.rag.indexer import vector_store

    for record in db.query(CustomRecord).filter(CustomRecord.module_id == module.id).all():
        vector_store.remove(db, f"custom:{slug}", str(record.id))
    db.commit()


# ---- Widgets (Verwaltung: builder; Daten: Quellen-Berechtigung) ----

from .models import Widget  # noqa: E402
from .widgets import evaluate_widget, module_for_source  # noqa: E402


@router.get("/widgets")
def list_widgets(db: Session = Depends(get_tenant_db)):
    return [
        {"id": w.id, "title": w.title, "widget_type": w.widget_type,
         "source": w.source, "active": w.active}
        for w in db.query(Widget).order_by(Widget.position, Widget.id).all()
    ]


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: int, db: Session = Depends(get_tenant_db)):
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if widget is None:
        raise HTTPException(404, "Widget nicht gefunden")
    db.delete(widget)
    db.commit()


@records_router.get("/widgets/data")
def widget_data(
    user: User = Depends(get_current_user), db: Session = Depends(get_tenant_db)
):
    """Ausgewertete Dashboard-Widgets — nur Quellen, die der Benutzer lesen darf."""
    widgets = (
        db.query(Widget)
        .filter(Widget.active.is_(True))
        .order_by(Widget.position, Widget.id)
        .all()
    )
    return [
        evaluate_widget(db, widget)
        for widget in widgets
        if has_permission(db, user, module_for_source(widget.source), "read")
    ]


# ---- Automationen verwalten (Recht: builder) ----

from .models import Automation, AutomationRun  # noqa: E402


def _automation_out(automation: Automation) -> dict:
    return {
        "id": automation.id, "name": automation.name, "active": automation.active,
        "trigger_type": automation.trigger_type, "trigger_event": automation.trigger_event,
        "schedule": automation.schedule, "source": automation.source,
        "conditions": automation.conditions, "actions": automation.actions,
        "next_run_at": automation.next_run_at,
    }


@router.get("/automations")
def list_automations(db: Session = Depends(get_tenant_db)):
    return [_automation_out(a) for a in
            db.query(Automation).order_by(Automation.created_at.desc()).all()]


@router.patch("/automations/{automation_id}")
def toggle_automation(automation_id: int, active: bool, db: Session = Depends(get_tenant_db)):
    automation = db.query(Automation).filter(Automation.id == automation_id).first()
    if automation is None:
        raise HTTPException(404, "Automation nicht gefunden")
    automation.active = active
    db.commit()
    return _automation_out(automation)


@router.get("/automations/{automation_id}/runs")
def automation_runs(automation_id: int, db: Session = Depends(get_tenant_db)):
    runs = (
        db.query(AutomationRun)
        .filter(AutomationRun.automation_id == automation_id)
        .order_by(AutomationRun.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": r.id, "status": r.status, "detail": r.detail,
         "trigger_info": r.trigger_info, "created_at": r.created_at}
        for r in runs
    ]


# ---- KI-Builder: Entwurf → Vorschau → Aktivieren (Recht: builder) ----

from pydantic import BaseModel  # noqa: E402

from ..ai import llm  # noqa: E402
from .activation import materialize  # noqa: E402
from .definitions import parse_artifact  # noqa: E402
from .models import BuilderDraft  # noqa: E402


class DraftRequest(BaseModel):
    description: str


class DraftUpdate(BaseModel):
    definition: dict


def _draft_out(draft: BuilderDraft) -> dict:
    return {
        "id": draft.id, "kind": draft.kind, "status": draft.status,
        "description_input": draft.description_input,
        "definition": draft.definition,
        "erklaerung": draft.erklaerung,
        "created_at": draft.created_at,
    }


@router.post("/draft")
def create_draft(
    request: DraftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    """Übersetzt eine deutsche Beschreibung in Builder-Entwürfe (Vorschau)."""
    from .translator import translate

    if not llm.is_available():
        raise HTTPException(503, "KI nicht verfügbar (kein ANTHROPIC_API_KEY) — "
                                 "bitte den manuellen Editor verwenden.")
    result = translate(db, request.description)
    if result is None:
        raise HTTPException(502, "KI-Übersetzung fehlgeschlagen — bitte erneut versuchen "
                                 "oder den manuellen Editor verwenden.")

    drafts = []
    for artifact in result.artefakte:
        draft = BuilderDraft(
            kind=artifact.kind,
            description_input=request.description,
            definition=artifact.model_dump(),
            erklaerung=result.erklaerung,
            rueckfragen=result.rueckfragen or None,
            created_by=user.id,
        )
        db.add(draft)
        drafts.append(draft)
    db.commit()
    return {
        "erklaerung": result.erklaerung,
        "rueckfragen": result.rueckfragen,
        "drafts": [_draft_out(d) for d in drafts],
    }


@router.get("/drafts")
def list_drafts(db: Session = Depends(get_tenant_db)):
    drafts = (
        db.query(BuilderDraft)
        .filter(BuilderDraft.status == "vorschau")
        .order_by(BuilderDraft.created_at.desc())
        .all()
    )
    return [_draft_out(d) for d in drafts]


def _get_draft(db: Session, draft_id: int) -> BuilderDraft:
    draft = db.query(BuilderDraft).filter(BuilderDraft.id == draft_id).first()
    if draft is None:
        raise HTTPException(404, "Entwurf nicht gefunden")
    if draft.status != "vorschau":
        raise HTTPException(409, f"Entwurf ist bereits {draft.status}")
    return draft


@router.patch("/drafts/{draft_id}")
def update_draft(draft_id: int, data: DraftUpdate, db: Session = Depends(get_tenant_db)):
    """Nutzer hat die Vorschau im Editor angepasst — neu validieren."""
    draft = _get_draft(db, draft_id)
    try:
        artifact = parse_artifact(draft.kind, data.definition)
    except Exception as exc:
        raise HTTPException(422, f"Definition ungültig: {exc}")
    draft.definition = artifact.model_dump()
    db.commit()
    return _draft_out(draft)


@router.post("/drafts/{draft_id}/activate")
def activate_draft(draft_id: int, db: Session = Depends(get_tenant_db)):
    draft = _get_draft(db, draft_id)
    result = materialize(db, draft.kind, draft.definition)
    draft.status = "aktiviert"
    db.commit()
    return {"activated": result}


@router.post("/drafts/{draft_id}/discard")
def discard_draft(draft_id: int, db: Session = Depends(get_tenant_db)):
    draft = _get_draft(db, draft_id)
    draft.status = "verworfen"
    db.commit()
    return _draft_out(draft)


# ---- Records (Recht: custom:<slug>) ----

def require_custom(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
) -> Session:
    slug = request.path_params.get("slug", "")
    action = "read" if request.method in READ_METHODS else "write"
    if not has_permission(db, user, f"custom:{slug}", action):
        raise HTTPException(403, f"Keine Berechtigung für custom:{slug}:{action}")
    return db


def _get_active_module(db: Session, slug: str) -> CustomModule:
    module = get_module(db, slug)
    if module is None:
        raise HTTPException(404, f"Modul '{slug}' nicht gefunden")
    return module


@records_router.get("/modules")
def visible_modules(
    user: User = Depends(get_current_user), db: Session = Depends(get_tenant_db)
):
    """Aktive Custom-Module, die der angemeldete Benutzer sehen darf (für die Navigation)."""
    modules = db.query(CustomModule).filter(CustomModule.status == "aktiv").all()
    return [
        _module_out(m) for m in modules
        if has_permission(db, user, f"custom:{m.slug}", "read")
    ]


@records_router.get("/{slug}/records")
def list_records(slug: str, db: Session = Depends(require_custom)):
    module = _get_active_module(db, slug)
    records = (
        db.query(CustomRecord)
        .filter(CustomRecord.module_id == module.id)
        .order_by(CustomRecord.created_at.desc())
        .all()
    )
    return {"module": _module_out(module), "records": [_record_out(r) for r in records]}


@records_router.post("/{slug}/records", status_code=201)
def create_record(slug: str, values: dict, db: Session = Depends(require_custom)):
    module = _get_active_module(db, slug)
    try:
        clean = validate_values(module, values)
    except RecordValidationError as exc:
        raise HTTPException(422, exc.errors)
    record = CustomRecord(module_id=module.id, values=clean)
    db.add(record)
    db.commit()
    events.publish(f"custom.{slug}.record.created", {
        "tenant_id": db.info.get("tenant_id"), "id": record.id, "slug": slug,
        **{f"values.{k}": v for k, v in clean.items()},
    })
    return _record_out(record)


@records_router.patch("/{slug}/records/{record_id}")
def update_record(slug: str, record_id: int, values: dict, db: Session = Depends(require_custom)):
    module = _get_active_module(db, slug)
    record = (
        db.query(CustomRecord)
        .filter(CustomRecord.id == record_id, CustomRecord.module_id == module.id)
        .first()
    )
    if record is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    try:
        clean = validate_values(module, {**record.values, **values})
    except RecordValidationError as exc:
        raise HTTPException(422, exc.errors)
    record.values = clean  # komplett ersetzen (JSON-Mutation-Tracking)
    db.commit()
    events.publish(f"custom.{slug}.record.updated", {
        "tenant_id": db.info.get("tenant_id"), "id": record.id, "slug": slug,
        **{f"values.{k}": v for k, v in clean.items()},
    })
    return _record_out(record)


@records_router.delete("/{slug}/records/{record_id}", status_code=204)
def delete_record(slug: str, record_id: int, db: Session = Depends(require_custom)):
    module = _get_active_module(db, slug)
    record = (
        db.query(CustomRecord)
        .filter(CustomRecord.id == record_id, CustomRecord.module_id == module.id)
        .first()
    )
    if record is None:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(record)
    db.commit()
    events.publish(f"custom.{slug}.record.deleted", {
        "tenant_id": db.info.get("tenant_id"), "id": record_id, "slug": slug,
    })


# Re-Export für den Indexer
__all__ = ["router", "records_router", "record_card"]
