"""Optional step: compute embeddings for hybrid search.  `python -m runbook_copilot.retrieval.index`

Needs EMBED_MODEL plus an OpenAI-compatible embeddings endpoint. Without it the system is keyword-only,
which already works well for troubleshooting vocabulary (error strings, reason codes, alert names).
"""
from __future__ import annotations

import json
import sys

import numpy as np
from openai import OpenAI

from ..config import Settings, get_settings
from ..schemas import Chunk


def make_embedder(s: Settings):
    client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key or "none")

    def embed(texts: list[str]) -> list[list[float]]:
        resp = client.embeddings.create(model=s.embed_model, input=texts)
        return [d.embedding for d in resp.data]

    return embed


def main() -> int:
    s = get_settings()
    if not s.embed_model:
        print("EMBED_MODEL is empty; skipping (keyword-only retrieval).")
        return 0
    chunks = [Chunk.model_validate_json(ln) for ln in s.chunks_path.read_text().splitlines() if ln.strip()]
    embed = make_embedder(s)
    vecs: list[list[float]] = []
    for i in range(0, len(chunks), 64):
        batch = chunks[i:i + 64]
        vecs += embed([f"{c.title}\n{c.heading_path}\n{c.text}"[:6000] for c in batch])
        print(f"embedded {min(i + 64, len(chunks))}/{len(chunks)}", file=sys.stderr)
    s.index_dir.mkdir(parents=True, exist_ok=True)
    np.save(s.index_dir / "embeddings.npy", np.asarray(vecs, dtype=np.float32))
    (s.index_dir / "embedding_ids.json").write_text(json.dumps([c.chunk_id for c in chunks]))
    print(f"saved embeddings for {len(chunks)} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
