"""Zerlegung von Dokumenten in überlappende Text-Chunks.

Es wird bevorzugt an Absatz- und Satzgrenzen geschnitten, damit die
Chunks für Retrieval und LLM-Kontext semantisch sinnvoll bleiben.
"""

import re


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    # An Absätzen, dann Sätzen splitten und gierig zu Chunks zusammensetzen
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        parts = re.split(r"(?<=[.!?:])\s+", paragraph.strip())
        sentences.extend(p for p in parts if p)

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        # Übergroße Einzelsätze hart zerlegen
        while len(sentence) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:chunk_size])
            sentence = sentence[chunk_size - overlap:]
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > chunk_size and current:
            chunks.append(current)
            # Überlappung: Ende des letzten Chunks an den Anfang des nächsten
            tail = current[-overlap:] if overlap > 0 else ""
            current = f"{tail} {sentence}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
