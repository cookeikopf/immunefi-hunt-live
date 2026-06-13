"""Datenbank-Setup (SQLAlchemy 2.x, standardmäßig SQLite)."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    # Die Event-Handler (RAG-Indexer, Automationen, Workflows) öffnen eigene
    # Sessions = eigene SQLite-Verbindungen, die mit der Request-Verbindung
    # überlappen können. Ohne Härtung führt das sporadisch zu
    # "database is locked". WAL erlaubt gleichzeitiges Lesen+Schreiben,
    # busy_timeout lässt einen Schreiber kurz warten statt sofort zu scheitern.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Erzeugt alle Tabellen. Modelle müssen vorher importiert sein."""
    Base.metadata.create_all(bind=engine)
