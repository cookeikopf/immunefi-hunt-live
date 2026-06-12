"""KMU-OS — Operating System für kleine und mittlere Unternehmen.

Startet die FastAPI-Anwendung, registriert alle Modul-Router, initialisiert
die Datenbank und verbindet den RAG-Indexer mit dem Event-Bus.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai.router import router as ai_router
from .builder.notifications_router import router as notifications_router
from .builder.workflows_router import router as workflows_router
from .builder.router import records_router as custom_records_router
from .builder.router import router as builder_router
from .core.config import get_settings
from .core.database import init_db
from .imports.router import router as imports_router
from .modules.auth.admin_router import router as admin_router
from .modules.auth.router import router as auth_router
from .modules.crm.router import router as crm_router
from .modules.finance.router import router as finance_router
from .modules.hr.router import router as hr_router
from .modules.knowledge.router import router as knowledge_router
from .modules.projects.router import router as projects_router

settings = get_settings()

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alle Modelle sind über die Router-Importe geladen → Tabellen anlegen
    init_db()
    from .ai.rag.indexer import register_event_handlers
    from .builder.automations import register_automation_handlers
    from .builder.workflows import register_workflow_handlers

    register_event_handlers()
    register_automation_handlers()
    register_workflow_handlers()

    from .builder import scheduler

    if settings.scheduler_enabled:
        scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Operating System für KMUs: CRM, Finanzen, Personal, Projekte und "
        "Wissensmanagement in einem System — mit gebündelten Daten als "
        "Grundlage für KI-Analysen und einen firmeneigenen RAG-Assistenten."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(imports_router)
app.include_router(crm_router)
app.include_router(finance_router)
app.include_router(hr_router)
app.include_router(projects_router)
app.include_router(knowledge_router)
app.include_router(builder_router)
app.include_router(custom_records_router)
app.include_router(notifications_router)
app.include_router(workflows_router)
app.include_router(ai_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "company": settings.company_name}


if (FRONTEND_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "static" / "index.html")
