"""Hybrid-Retrieval: Vektor-Ähnlichkeit + BM25-Keyword-Score.

Die Kombination beider Verfahren ist robuster als jedes einzelne:
Der Vektor-Score fängt semantische Nähe ein, BM25 belohnt exakte
Begriffe (Rechnungsnummern, Eigennamen, Fachbegriffe).
"""

import math
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .embeddings import tokenize
from .vectorstore import RagChunk, VectorStore


@dataclass
class RetrievedChunk:
    source: str
    source_id: str
    title: str
    content: str
    score: float


def _bm25_scores(query_tokens: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    if n == 0:
        return []
    avg_len = sum(len(d) for d in docs) / n or 1.0
    # Dokumentfrequenz je Query-Term
    df = {t: sum(1 for d in docs if t in d) for t in set(query_tokens)}
    scores = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for term in query_tokens:
            if df.get(term, 0) == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            f = tf.get(term, 0)
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(doc) / avg_len))
        scores.append(score)
    return scores


class HybridRetriever:
    def __init__(self, store: VectorStore, vector_weight: float = 0.6):
        self.store = store
        self.vector_weight = vector_weight

    def retrieve(self, db: Session, query: str, top_k: int = 6) -> list[RetrievedChunk]:
        chunks: list[RagChunk] = db.query(RagChunk).all()
        if not chunks:
            return []

        query_vec = self.store.embedder.embed(query)
        from .embeddings import cosine  # lokaler Import vermeidet Zyklus beim Modul-Load

        vector_scores = [cosine(query_vec, c.embedding) for c in chunks]
        bm25 = _bm25_scores(tokenize(query), [tokenize(c.content) for c in chunks])

        def normalize(values: list[float]) -> list[float]:
            hi = max(values) if values else 0.0
            return [v / hi if hi > 0 else 0.0 for v in values]

        v_norm, b_norm = normalize(vector_scores), normalize(bm25)
        combined = [
            (c, self.vector_weight * v + (1 - self.vector_weight) * kw)
            for c, v, kw in zip(chunks, v_norm, b_norm)
        ]
        combined.sort(key=lambda pair: pair[1], reverse=True)
        return [
            RetrievedChunk(
                source=c.source, source_id=c.source_id, title=c.title,
                content=c.content, score=round(score, 4),
            )
            for c, score in combined[:top_k]
            if score > 0
        ]
