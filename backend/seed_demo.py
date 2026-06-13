"""CLI-Seed: legt eine Demo-Firma mit Admin-Konto und Musterdaten an.

Aufruf (aus dem Projektwurzelverzeichnis):
    python -m backend.seed_demo

Zugangsdaten danach: admin@demo.de / demo1234
"""

from backend.app.core.config import get_settings
from backend.app.core.database import SessionLocal, init_db
from backend.app.core.tenancy import Tenant
from backend.app.demo_data import seed_demo_data
from backend.app.modules.auth.router import create_tenant_with_admin


def seed() -> None:
    settings = get_settings()
    init_db()
    db = SessionLocal()
    try:
        if db.query(Tenant).count() > 0:
            print("Datenbank enthält bereits einen Mandanten — Seeding übersprungen.")
            return

        tenant, admin = create_tenant_with_admin(
            db,
            company_name=settings.company_name,
            industry="Dienstleistung",
            admin_name="Demo Admin",
            admin_email="admin@demo.de",
            admin_password="demo1234",
        )
        print(f"Mandant angelegt: {tenant.name} (slug: {tenant.slug})")
        print(f"Admin-Login: {admin.email} / demo1234")

        db.info["tenant_id"] = tenant.id
        counts = seed_demo_data(db)
        print(f"Demo-Daten angelegt, RAG-Index aufgebaut: {counts}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
