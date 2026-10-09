"""Hybrid retrieval (BM25 + optional embeddings, fused with Reciprocal Rank Fusion) and the
retrieval gate that decides whether we have enough evidence to even call the LLM.

CLI:  python -m runbook_copilot.retrieval.search "pod stuck in CrashLoopBackOff"
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import numpy as np

from ..config import Settings, get_settings
from ..schemas import Chunk, RetrievedChunk
from .bm25 import BM25
from .text import tokenize

# Cheap scope check: a question with none of these (deliberately specific) terms is treated as out of scope.
# Generic words like 'service' or 'cluster' are excluded on purpose: they appear in non-Kubernetes questions too.
K8S_TERMS = frozenset("""
kubernetes k8s kubectl kubelet pod deployment replicaset statefulset daemonset cronjob node namespace
container ingress endpoint endpoints configmap pvc probe liveness readiness rollout crashloopbackoff imagepullbackoff
errimagepull oomkilled oom evicted eviction pending unschedulable taint toleration quota coredns kube-dns nslookup
kubeadm helm kind minikube k3d containerd scheduler hpa networkpolicy notready dns kustomize
""".split())


@dataclass
class GateResult:
    ok: bool
    reason: str | None
    top_bm25: float
    coverage: float
    in_scope: bool


def _index_text(c: Chunk) -> str:
    # Title and headings are repeated so they weigh more than body text.
    return f"{c.title} {c.title} {c.heading_path} {c.heading_path} {c.text}"


class Retriever:
    def __init__(self, chunks: list[Chunk], embeddings: np.ndarray | None = None, embedder=None):
        self.chunks = chunks
        self.tokens = [tokenize(_index_text(c)) for c in chunks]
        self.bm25 = BM25().fit(self.tokens)
        self.embeddings = embeddings
        self.embedder = embedder

    @classmethod
    def load(cls, settings: Settings | None = None) -> Retriever:
        s = settings or get_settings()
        if not s.chunks_path.exists():
            raise FileNotFoundError(f"{s.chunks_path} not found. Run `make ingest` first.")
        chunks = [Chunk.model_validate_json(line) for line in s.chunks_path.read_text().splitlines() if line.strip()]
        emb, embedder = None, None
        emb_path, ids_path = s.index_dir / "embeddings.npy", s.index_dir / "embedding_ids.json"
        if s.embed_model and emb_path.exists() and ids_path.exists():
            ids = json.loads(ids_path.read_text())
            if ids == [c.chunk_id for c in chunks]:
                from .index import make_embedder  # lazy: only needed for hybrid mode
                emb, embedder = np.load(emb_path), make_embedder(s)
        return cls(chunks, emb, embedder)

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = 6, max_per_doc: int = 3, candidates: int = 30) -> list[RetrievedChunk]:
        q_tokens = tokenize(query)
        kw = self.bm25.search(q_tokens, k=candidates)
        bm25_by_idx = dict(kw)
        ranked_lists = [[i for i, _ in kw]]

        if self.embeddings is not None and self.embedder is not None:
            qv = np.asarray(self.embedder([query])[0], dtype=np.float32)
            sims = self.embeddings @ qv / (np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(qv) + 1e-9)
            ranked_lists.append(list(np.argsort(-sims)[:candidates]))

        fused: dict[int, float] = {}
        for lst in ranked_lists:  # Reciprocal Rank Fusion
            for rank, idx in enumerate(lst):
                fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (60 + rank + 1)
        order = sorted(fused, key=fused.get, reverse=True)

        out, per_doc = [], {}
        for idx in order:
            c = self.chunks[idx]
            if per_doc.get(c.doc_path, 0) >= max_per_doc:
                continue
            per_doc[c.doc_path] = per_doc.get(c.doc_path, 0) + 1
            out.append(RetrievedChunk(chunk=c, score=fused[idx], bm25=bm25_by_idx.get(idx, 0.0)))
            if len(out) == k:
                break
        return out


def evaluate_gate(query: str, hits: list[RetrievedChunk], settings: Settings | None = None) -> GateResult:
    """Decide whether retrieved evidence is strong enough to answer. Deterministic and cheap."""
    s = settings or get_settings()
    q_terms = set(tokenize(query))
    in_scope = bool(set(tokenize(query, keep_stopwords=True)) & K8S_TERMS)
    if not hits:
        return GateResult(False, "no_results", 0.0, 0.0, in_scope)
    top = max(h.bm25 for h in hits)
    seen = set()
    for h in hits[:3]:
        seen.update(tokenize(f"{h.chunk.title} {h.chunk.heading_path} {h.chunk.text}"))
    coverage = len(q_terms & seen) / len(q_terms) if q_terms else 0.0
    # The keyword scope check is brittle (people describe symptoms in many ways), so a very strong
    # lexical match against the corpus overrides it.
    strong = top >= s.strong_match_score and coverage >= 0.6
    if not in_scope and not strong:
        return GateResult(False, "out_of_scope: no recognised Kubernetes troubleshooting terms", top, coverage, False)
    if top < s.min_bm25_score:
        return GateResult(False, f"weak_retrieval: top BM25 {top:.1f} < {s.min_bm25_score}", top, coverage, True)
    if coverage < s.min_query_coverage:
        return GateResult(False, f"low_coverage: {coverage:.2f} < {s.min_query_coverage}", top, coverage, True)
    return GateResult(True, None, top, coverage, True)


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python -m runbook_copilot.retrieval.search "your question"')
        return 1
    q = " ".join(sys.argv[1:])
    s = get_settings()
    r = Retriever.load(s)
    hits = r.search(q, k=s.top_k)
    gate = evaluate_gate(q, hits, s)
    print(f"gate: ok={gate.ok} top_bm25={gate.top_bm25:.1f} coverage={gate.coverage:.2f} reason={gate.reason}\n")
    for i, h in enumerate(hits, 1):
        print(f"{i}. [{h.bm25:5.1f}] {h.chunk.chunk_id}\n   {h.chunk.heading_path}\n   {h.chunk.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
