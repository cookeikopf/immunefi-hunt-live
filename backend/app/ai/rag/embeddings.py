"""Einbettungs-Schicht für das RAG-System.

Standardmäßig kommt ein deterministischer Hashing-Embedder zum Einsatz
(Bag-of-Words mit Feature-Hashing, L2-normalisiert). Er benötigt keine
externen Modelle oder Netzzugriff und funktioniert sprachunabhängig
ausreichend gut für kleine Korpora.

Die Schnittstelle ist bewusst minimal (``embed(text) -> list[float]``),
sodass später ein echtes Embedding-Modell (z. B. sentence-transformers
oder ein API-Dienst) eingesteckt werden kann, ohne den Rest des Systems
zu ändern.
"""

import hashlib
import math
import re
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-zA-ZäöüÄÖÜß0-9]{2,}")

# Deutsche + englische Stoppwörter (kleine, pragmatische Liste)
_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "eines", "einem", "einen",
    "ist", "sind", "war", "waren", "wird", "werden", "hat", "haben", "mit", "von", "für",
    "auf", "aus", "bei", "nach", "über", "unter", "vor", "zu", "zum", "zur", "im", "in",
    "an", "am", "den", "dem", "des", "als", "auch", "es", "sich", "nicht", "wir", "sie",
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "to", "of", "in",
    "on", "for", "with", "at", "by", "from", "it", "this", "that", "not",
}


def tokenize(text: str) -> list[str]:
    return [t for t in (m.group(0).lower() for m in _TOKEN_RE.finditer(text)) if t not in _STOPWORDS]


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Feature-Hashing-Embedder: deterministisch, offline, ohne Abhängigkeiten."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % self.dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        return index, sign

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in tokenize(text):
            index, sign = self._bucket(token)
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
