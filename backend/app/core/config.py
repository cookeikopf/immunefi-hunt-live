"""Zentrale Konfiguration des KMU-OS.

Alle Einstellungen sind über Umgebungsvariablen mit dem Präfix ``KMUOS_``
überschreibbar (siehe .env.example im Projektwurzelverzeichnis).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KMUOS_", env_file=".env", extra="ignore")

    app_name: str = "KMU-OS"
    company_name: str = "Musterfirma GmbH"
    database_url: str = "sqlite:///./kmuos.db"

    # KI-Konfiguration (Anthropic Claude)
    anthropic_model: str = "claude-opus-4-8"
    ai_max_tokens: int = 16000

    # RAG-Konfiguration
    rag_chunk_size: int = 800        # Zeichen pro Chunk
    rag_chunk_overlap: int = 150     # Überlappung zwischen Chunks
    rag_top_k: int = 6               # Anzahl Treffer pro Anfrage
    embedding_dim: int = 512         # Dimension des Hashing-Embedders


@lru_cache
def get_settings() -> Settings:
    return Settings()
