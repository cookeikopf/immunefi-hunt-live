"""Import-Protokoll: jeder CSV-Import wird mit Ergebnis festgehalten."""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from ..core.tenancy import TenantMixin


class ImportJob(TenantMixin, Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # customers | invoices
    filename: Mapped[str] = mapped_column(String(300))
    total_rows: Mapped[int] = mapped_column(default=0)
    imported: Mapped[int] = mapped_column(default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def errors(self) -> list:
        return json.loads(self.errors_json)
