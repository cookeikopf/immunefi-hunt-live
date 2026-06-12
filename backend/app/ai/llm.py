"""Anbindung an die Claude API (Anthropic Python SDK).

Der Client liest den API-Schlüssel aus der Umgebungsvariable
``ANTHROPIC_API_KEY``. Ohne Schlüssel laufen alle Geschäftsmodule und
das RAG-Retrieval normal weiter — nur die LLM-Antworten werden durch
einen klaren Hinweis ersetzt (Graceful Degradation), sodass das System
auch offline entwickelt und getestet werden kann.
"""

import logging
import os

from ..core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

try:
    import anthropic
except ImportError:  # pragma: no cover - SDK ist in requirements.txt enthalten
    anthropic = None


def is_available() -> bool:
    return anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))


_NO_KEY_MESSAGE = (
    "KI-Antworten sind derzeit nicht verfügbar: Es ist kein ANTHROPIC_API_KEY "
    "konfiguriert. Hinterlegen Sie den Schlüssel in der .env-Datei oder als "
    "Umgebungsvariable, um den Firmen-Assistenten zu aktivieren."
)


def parse(system_stable: str, system_context: str, user_message: str, output_format):
    """Structured-Outputs-Anfrage: Claude antwortet garantiert im Schema.

    ``system_stable`` ist der über Anfragen hinweg identische Teil
    (mit Cache-Breakpoint), ``system_context`` der mandanten-spezifische
    Teil dahinter. Liefert die validierte Pydantic-Instanz oder None
    (kein API-Key / Fehler) — der Aufrufer fällt dann auf den manuellen
    Editor zurück.
    """
    if not is_available():
        return None

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=settings.ai_max_tokens,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": system_stable,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": system_context},
            ],
            messages=[{"role": "user", "content": user_message}],
            output_format=output_format,
        )
        return response.parsed_output
    except anthropic.APIStatusError as exc:
        logger.error("Claude-Parse-Fehler (%s): %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        logger.error("Keine Verbindung zur Claude API (parse)")
        return None


def complete(
    system: str,
    user_message: str,
    max_tokens: int | None = None,
    history: list[dict] | None = None,
) -> str:
    """Eine Claude-Anfrage mit adaptivem Denken und Streaming.

    ``history`` (optional): vorherige Gesprächsrunden als
    ``[{"role": "user"|"assistant", "content": str}, ...]``.
    Streaming schützt bei langen Antworten vor HTTP-Timeouts; das
    vollständige Ergebnis wird über ``get_final_message()`` eingesammelt.
    """
    if not is_available():
        return _NO_KEY_MESSAGE

    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=max_tokens or settings.ai_max_tokens,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": system,
                    # Der Systemprompt (Firmenkontext) wiederholt sich über
                    # Anfragen hinweg — Caching spart Kosten und Latenz.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=(history or []) + [{"role": "user", "content": user_message}],
        ) as stream:
            message = stream.get_final_message()
        return "".join(block.text for block in message.content if block.type == "text")
    except anthropic.APIStatusError as exc:
        logger.error("Claude-API-Fehler (%s): %s", exc.status_code, exc.message)
        return f"KI-Anfrage fehlgeschlagen (HTTP {exc.status_code}). Bitte später erneut versuchen."
    except anthropic.APIConnectionError:
        logger.error("Keine Verbindung zur Claude API")
        return "KI-Anfrage fehlgeschlagen: keine Verbindung zur Claude API."
