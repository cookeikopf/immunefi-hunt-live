"""Alembic-Umgebung: nutzt die App-Konfiguration und alle Modelle."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import get_settings
from backend.app.core.database import Base

# Alle Modelle importieren, damit Base.metadata vollständig ist
from backend.app.core import tenancy  # noqa: F401
from backend.app.modules.auth import models as auth_models  # noqa: F401
from backend.app.modules.crm import models as crm_models  # noqa: F401
from backend.app.modules.finance import models as finance_models  # noqa: F401
from backend.app.modules.hr import models as hr_models  # noqa: F401
from backend.app.modules.knowledge import models as knowledge_models  # noqa: F401
from backend.app.modules.projects import models as projects_models  # noqa: F401
from backend.app.ai.rag import vectorstore  # noqa: F401
from backend.app.imports import models as import_models  # noqa: F401
from backend.app.builder import models as builder_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # nötig für ALTER TABLE unter SQLite
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
