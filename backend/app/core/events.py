"""Einfacher In-Process-Event-Bus.

Module publizieren Domänen-Ereignisse (z. B. "invoice.created"), andere
Komponenten – insbesondere der RAG-Indexer – abonnieren sie, damit der
KI-Wissensstand automatisch aktuell bleibt.
"""

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[str, dict[str, Any]], None]

_subscribers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_pattern: str, handler: Handler) -> None:
    """Abonniert ein Ereignis. ``*`` abonniert alle Ereignisse."""
    _subscribers[event_pattern].append(handler)


def publish(event: str, payload: dict[str, Any] | None = None) -> None:
    payload = payload or {}
    for handler in _subscribers.get(event, []) + _subscribers.get("*", []):
        try:
            handler(event, payload)
        except Exception:  # Ein fehlerhafter Handler darf den Request nicht abbrechen
            logger.exception("Event-Handler für %s fehlgeschlagen", event)


def reset() -> None:
    """Nur für Tests: entfernt alle Abonnements."""
    _subscribers.clear()
