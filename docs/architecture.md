# Architecture

```mermaid
flowchart LR
  subgraph Offline["Offline (make ingest)"]
    S[Public sources<br/>pinned git commits] --> P[parse<br/>strip shortcodes]
    P --> C[heading-aware chunks<br/>stable chunk_id]
    L[lab runbooks + evidence] --> P
    C --> J[(chunks.jsonl)]
    J -. optional .-> E[(embeddings.npy)]
  end
  subgraph Online["Online (per request)"]
    Q[question] --> R[BM25 + optional dense<br/>RRF fusion]
    R --> G{retrieval gate<br/>scope, score, coverage}
    G -- weak --> A1[abstain: no LLM call]
    G -- ok --> M[prompt + numbered context]
    M --> LLM[OpenAI-compatible LLM<br/>JSON output]
    LLM --> V[Pydantic validation<br/>retry once]
    V --> F[guardrails<br/>citation subset, command allowlist,<br/>remediation flags, groundedness]
    F --> OUT[TriageResponse + trace + sources]
  end
  J --> R
  OUT --> LOG[(requests.jsonl)] --> ST[/stats]
  OUT -. OTLP .-> OT[(traces + metrics<br/>Grafana)]
```

## Components
| Module | Responsibility |
|---|---|
| `ingest/fetch.py` | sparse, blobless git fetch at a pinned SHA; writes `sources.lock.json` |
| `ingest/parse.py` | markdown/MDX to clean text; strips Hugo shortcodes, JSX lines, comments |
| `ingest/chunk.py` | split at H1-H4 (never inside code fences), merge tiny sections, split big ones, stable ids |
| `retrieval/bm25.py` | pure-Python BM25 with real scores |
| `retrieval/search.py` | hybrid search (RRF), per-doc diversity cap, **retrieval gate** |
| `llm/prompts.py` | system prompt contract + context formatting |
| `llm/client.py` | OpenAI-compatible call, JSON extraction, validate-and-retry |
| `safety.py` | command allowlist, remediation sanitiser, citation check, groundedness |
| `pipeline.py` | orchestration, abstention paths, confidence calibration |
| `observability.py` | JSONL request log and summary (`/stats`) |
| `telemetry.py` | optional OpenTelemetry traces and metrics, token and cost tracking (no-op when disabled) |

## Design decisions
1. **Guardrails outside the model.** The prompt asks for read-only commands and valid citations; `safety.py` enforces both deterministically. `trace.dropped_commands` / `dropped_citations` record every time the model needed correcting, which is itself an eval metric.
2. **Gate before generation.** If retrieval is weak or the question is out of scope we abstain without an LLM call: cheaper, faster, safer.
3. **Three more abstention paths** after generation: the model abstains, the citations are invalid, or confidence (capped by lexical groundedness) is below threshold.
4. **BM25 first.** Troubleshooting text is full of exact tokens (reason codes, event strings, alert names) where keyword search is strong. Embeddings are an optional upgrade (`EMBED_MODEL`).
5. **Own BM25 instead of minsearch.** minsearch's TF-IDF search does not expose scores, and the gate needs one. The `Retriever.search()` shape is simple enough to swap back.
6. **Flat files.** JSONL for chunks and logs, YAML for cases and sources. No database to operate. pgvector/Qdrant is a documented upgrade.
7. **Stable chunk ids** (`<source>:<doc path>#<nn>`) so citations are human-readable and diffable across re-ingests.

## Known limitations
- Lexical groundedness cannot detect a fluent but wrong paraphrase; an LLM judge is the upgrade.
- The scope check is a keyword heuristic with a strong-match override; both thresholds were calibrated on the dev eval set.
- Corpus is a focused subset (pods, probes, scheduling, services/DNS, quotas, rollout). Anything outside it should abstain.
- English only. Kubernetes version drift: docs are pinned to one commit.
