"""Generische CRUD-Engine für Custom-Records.

Validierung über dynamisch erzeugte Pydantic-Modelle aus den
Felddefinitionen (gecacht pro Modul-Version). Werte werden
JSON-serialisierbar gespeichert (Datumswerte als ISO-Strings).
Filterung passiert in v1.0 in Python — das vermeidet die
JSON-Query-Divergenz zwischen SQLite und PostgreSQL.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError, create_model
from sqlalchemy.orm import Session

from .models import CustomField, CustomModule, CustomRecord

_TYPE_MAP: dict[str, type] = {
    "text": str, "textarea": str, "select": str,
    "number": float, "date": date, "bool": bool, "reference": int,
}

_model_cache: dict[tuple[int, int], type[BaseModel]] = {}


def record_model(module: CustomModule) -> type[BaseModel]:
    cache_key = (module.id, module.version)
    if cache_key not in _model_cache:
        field_specs: dict[str, Any] = {}
        for field in module.fields:
            py_type = _TYPE_MAP[field.field_type]
            if field.required:
                field_specs[field.name] = (py_type, ...)
            else:
                field_specs[field.name] = (py_type | None, None)
        _model_cache[cache_key] = create_model(f"Record_{module.slug}_v{module.version}", **field_specs)
    return _model_cache[cache_key]


class RecordValidationError(ValueError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("Validierung fehlgeschlagen")


def validate_values(module: CustomModule, data: dict) -> dict:
    """Validiert Eingabewerte und liefert ein JSON-serialisierbares Dict."""
    try:
        parsed = record_model(module).model_validate(data)
    except ValidationError as exc:
        raise RecordValidationError([
            {"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]}
            for e in exc.errors()
        ]) from exc

    values: dict[str, Any] = {}
    field_by_name = {f.name: f for f in module.fields}
    for name, value in parsed.model_dump().items():
        field = field_by_name[name]
        if field.field_type == "select" and value is not None and field.options:
            if value not in field.options:
                raise RecordValidationError([
                    {"field": name, "error": f"Wert muss einer von {field.options} sein"}
                ])
        values[name] = value.isoformat() if isinstance(value, date) else value
    return values


def record_card(module: CustomModule, record: CustomRecord) -> str:
    """Text-Repräsentation eines Records für den RAG-Index."""
    lines = [f"{module.name} ({module.name_plural or module.slug}), Eintrag #{record.id}:"]
    for field in module.fields:
        value = record.values.get(field.name)
        if value not in (None, ""):
            lines.append(f"- {field.label}: {value}")
    return "\n".join(lines)


def get_module(db: Session, slug: str, include_archived: bool = False) -> CustomModule | None:
    query = db.query(CustomModule).filter(CustomModule.slug == slug)
    if not include_archived:
        query = query.filter(CustomModule.status == "aktiv")
    return query.first()


def create_module_from_def(db: Session, module_def) -> CustomModule:
    """Materialisiert eine validierte ModuleDef als Custom-Modul."""
    module = CustomModule(
        slug=module_def.slug,
        name=module_def.name,
        name_plural=module_def.name_plural or module_def.name,
        description=module_def.description,
    )
    db.add(module)
    db.flush()
    for position, field_def in enumerate(module_def.fields):
        db.add(CustomField(
            module_id=module.id,
            name=field_def.name,
            label=field_def.label,
            field_type=field_def.field_type,
            required=field_def.required,
            options=field_def.options or None,
            reference_target=field_def.reference_target,
            show_in_list=field_def.show_in_list,
            position=position,
        ))
    return module


def grant_default_permissions(db: Session, slug: str) -> None:
    """Neue Custom-Module: alle Rollen außer Admin (hat '*') erhalten
    Schreibzugriff — der Admin kann das in der Rechte-Matrix einschränken."""
    from ..modules.auth.models import Role, RolePermission

    module_key = f"custom:{slug}"
    for role in db.query(Role).all():
        has_all = any(p.module == "*" for p in role.permissions)
        already = any(p.module == module_key for p in role.permissions)
        if not has_all and not already:
            db.add(RolePermission(role_id=role.id, module=module_key, action="write"))
