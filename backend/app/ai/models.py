"""KI-Datenmodelle: KPI-Schnappschüsse (für Wochenberichts-Deltas)
und persistente Chat-Unterhaltungen pro Benutzer."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..builder.models import JsonColumn
from ..core.database import Base
from ..core.tenancy import TenantMixin


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KpiSnapshot(TenantMixin, Base):
    __tablename__ = "kpi_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JsonColumn)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiConversation(TenantMixin, Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages: Mapped[list["AiMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="AiMessage.id",
    )


class AiMessage(TenantMixin, Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[AiConversation] = relationship(back_populates="messages")
