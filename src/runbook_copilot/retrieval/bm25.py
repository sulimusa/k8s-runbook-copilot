"""Tiny BM25 (Okapi) with an inverted index. Pure Python, returns real scores.

We use this instead of minsearch because the abstention gate needs a score, and minsearch's TF-IDF
search does not expose one. Swapping retrievers later only requires the same `.search()` shape.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict


class BM25:
    def __init__(self, k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_len: list[int] = []
        self.avg_len = 0.0
        self.n_docs = 0

    def fit(self, tokenized_docs: list[list[str]]) -> BM25:
        self.postings = defaultdict(list)
        self.doc_len = [len(d) for d in tokenized_docs]
        self.n_docs = len(tokenized_docs)
        self.avg_len = sum(self.doc_len) / max(self.n_docs, 1)
        for i, doc in enumerate(tokenized_docs):
            for term, tf in Counter(doc).items():
                self.postings[term].append((i, tf))
        return self

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def search(self, query_tokens: list[str], k: int = 10) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(query_tokens):
            idf = self.idf(term)
            for i, tf in self.postings.get(term, ()):
                norm = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avg_len)
                scores[i] += idf * tf * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
