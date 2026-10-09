"""Reproducible job-market analysis used to decide which skills this lab should demonstrate.

Source data: the open AI Engineering Field Guide dataset (builtin.com postings, LLM-enriched YAML).
  https://github.com/alexeygrigorev/ai-engineering-field-guide  (job-market/)
The dataset repo ships no license file, so this repo commits ONLY this script and aggregate numbers,
never the raw postings. Pinned to a commit for reproducibility.

  python analysis/job_market/analyze.py --fetch            # sparse-clone at the pinned SHA, then analyse
  python analysis/job_market/analyze.py --data /path/to/job-market [--remote]
Writes docs/market-analysis.md and analysis/job_market/results.json
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re

# fixed git invocations only
import subprocess  # nosec B404
import sys
from pathlib import Path

import yaml

REPO = "https://github.com/alexeygrigorev/ai-engineering-field-guide.git"
PINNED_SHA = "ed590319553252e2b8275486597b144ac55a4f3c"
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "analysis" / "job_market" / ".cache"


def load_yaml(text: str):
    """CSafeLoader when libyaml is available (about 10x faster on 8k files), else the pure-Python safe loader."""
    if hasattr(yaml, "CSafeLoader"):
        return yaml.load(text, Loader=yaml.CSafeLoader)
    return yaml.safe_load(text)


# Skills tracked in the headline table (names as they appear in the extracted taxonomy).
HEADLINE = [
    ("GenAI", ["RAG", "AI Agents", "Agentic Workflows", "LLM Evaluation", "Guardrails", "Function Calling", "MCP",
               "Prompt Engineering", "LangChain", "LangGraph", "Fine-Tuning", "Responsible AI"]),
    ("Languages", ["Python", "TypeScript", "Java", "Go", "SQL"]),
    ("Cloud", ["AWS", "Azure", "GCP", "AWS Bedrock"]),
    ("Ops", ["CI/CD", "Docker", "Kubernetes", "Observability", "Monitoring", "MLOps", "Model Deployment", "Terraform"]),
    ("Data stores", ["Vector Databases", "PostgreSQL", "pgvector", "Pinecone", "Weaviate", "Elasticsearch"]),
    ("Web", ["APIs", "React", "FastAPI", "REST APIs", "Microservices"]),
    ("Telemetry tools", ["OpenTelemetry", "Prometheus", "Grafana"]),
]


def run(*args: str, cwd: Path) -> None:
    # constant args, pinned SHA
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)  # nosec B603 B607


def fetch(with_remote: bool) -> Path:
    dest = CACHE / "field-guide"
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        run("init", "-q", cwd=dest)
        run("remote", "add", "origin", REPO, cwd=dest)
    run("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", PINNED_SHA, cwd=dest)
    paths = ["job-market/data_structured"] + (["job-market/data_raw"] if with_remote else [])
    run("sparse-checkout", "init", "--no-cone", cwd=dest)
    run("sparse-checkout", "set", "--no-cone", *paths, cwd=dest)
    run("checkout", "-q", "FETCH_HEAD", cwd=dest)
    return dest / "job-market"


def load(data: Path) -> list[dict]:
    rows = []
    for f in sorted(data.glob("data_structured/*/*.yaml")):
        y = load_yaml(f.read_text()) or {}
        pos, meta, comp = y.get("position") or {}, y.get("meta") or {}, y.get("company") or {}
        skills = {s.strip() for v in (pos.get("skills") or {}).values() for s in (v or [])}
        rows.append({
            "scrape": f.parent.name, "job_id": str(meta.get("job_id")), "loc": meta.get("location") or "",
            "company": comp.get("name"), "title": pos.get("title"),
            "type": (pos.get("ai_type") or {}).get("type"), "skills": skills,
            "customer_facing": bool(pos.get("is_customer_facing")),
        })
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    """Job ids differ per scrape, so the same listing re-posted monthly is collapsed on company+title+location."""
    latest: dict = {}
    for r in sorted(rows, key=lambda r: r["scrape"]):
        latest[(r["company"], r["title"], r["loc"])] = r
    return list(latest.values())


def share(rows: list[dict], skill: str) -> float:
    return sum(skill in r["skills"] for r in rows) / max(len(rows), 1)


def remote_mentions(data: Path, us_rows: list[dict], scrape: str) -> dict | None:
    raw_dir = data / "data_raw" / scrape
    if not raw_dir.exists():
        return None
    ids = {r["job_id"] for r in us_rows if r["scrape"] == scrape}
    total = remote = hybrid = 0
    for f in raw_dir.glob("*.yaml"):
        if f.name.split("_")[0] not in ids:
            continue
        text = ((load_yaml(f.read_text()) or {}).get("description") or "").lower()
        total += 1
        remote += bool(re.search(r"\bremote\b|work from home", text))
        hybrid += bool(re.search(r"\bhybrid\b", text))
    return {"scrape": scrape, "us_postings_with_text": total, "mention_remote": remote / total if total else 0,
            "mention_hybrid": hybrid / total if total else 0}


def analyse(rows: list[dict], data: Path, with_remote: bool) -> dict:
    uniq = dedupe(rows)
    us = [r for r in uniq if r["loc"].endswith("USA")]
    non = [r for r in uniq if not r["loc"].endswith("USA")]
    k8s = [r for r in us if "Kubernetes" in r["skills"]]
    co = collections.Counter(s for r in k8s for s in r["skills"] if s != "Kubernetes")
    res = {
        "scrapes": sorted({r["scrape"] for r in rows}), "raw_rows": len(rows), "unique": len(uniq), "us": len(us),
        "non_us": len(non), "headline": {},
        "role_types_us": {k: v / len(us) for k, v in collections.Counter(r["type"] for r in us).items()},
        "customer_facing_us": sum(r["customer_facing"] for r in us) / len(us),
        "customer_facing_non_us": sum(r["customer_facing"] for r in non) / len(non),
        "top_us_employers": collections.Counter(r["company"] for r in us).most_common(10),
        "chicago": sorted({(r["company"], r["title"]) for r in uniq if r["loc"].startswith("Chicago")}),
        "us_generic_location": sum(1 for r in us if r["loc"] == "USA"),
        "k8s_us": {"n": len(k8s), "share": len(k8s) / len(us),
                   "ai_first_share": sum(r["type"] == "ai-first" for r in k8s) / max(len(k8s), 1),
                   "co_occurring": [(s, n / len(k8s)) for s, n in co.most_common(10)]},
    }
    for cat, skills in HEADLINE:
        res["headline"][cat] = {s: {"us": share(us, s), "non_us": share(non, s)} for s in skills}
    if with_remote:
        res["remote"] = remote_mentions(data, us, max(r["scrape"] for r in rows))
    return res


def pct(x: float) -> str:
    return f"{x:.1%}"


def render(res: dict) -> str:
    L = [
        "# Job-market analysis (US focus)", "",
        f"_Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d} by `analysis/job_market/analyze.py` from dataset commit "
        f"`{PINNED_SHA[:12]}` (scrapes {res['scrapes'][0]} to {res['scrapes'][-1]})._", "",
        "Data: AI Engineering Field Guide job-market dataset by Alexey Grigorev (builtin.com postings, LLM-enriched). "
        "Only aggregate numbers are reproduced here; raw postings are not redistributed.", "",
        "## Sample", "",
        f"- {res['raw_rows']:,} scraped rows, **{res['unique']:,} unique** after collapsing re-posted listings on company + title + location "
        "(job ids differ per scrape, so id-based dedupe does nothing).",
        f"- **{res['us']:,} US** postings ({res['us'] / res['unique']:.0%}), {res['non_us']:,} non-US (mostly India, UK, Germany).",
        f"- {res['us_generic_location']:,} US postings are located only as \"USA\" (city unknown, may be remote).",
        f"- Chicago is too thin to analyse: {len(res['chicago'])} unique postings. Treat the **US** as the market.", "",
        "## Skill share of postings: US vs non-US", "",
    ]
    for cat, items in res["headline"].items():
        L += [f"**{cat}**", "", "| Skill | US | Non-US |", "|---|---|---|"]
        L += [f"| {s} | {pct(v['us'])} | {pct(v['non_us'])} |" for s, v in items.items()]
        L.append("")
    rt = res["role_types_us"]
    L += ["## Role mix and shape (US)", "",
          f"- AI-first {pct(rt.get('ai-first', 0))}, AI-support (platforms, infra, tooling) {pct(rt.get('ai-support', 0))}, "
          f"ML-first {pct(rt.get('ml-first', 0))}.",
          f"- Customer-facing roles: US {pct(res['customer_facing_us'])} vs non-US {pct(res['customer_facing_non_us'])}.",
          f"- Kubernetes appears in {pct(res['k8s_us']['share'])} of US postings ({res['k8s_us']['n']}); "
          f"{pct(res['k8s_us']['ai_first_share'])} of those are AI-first roles, so it is mostly a plus inside AI-first jobs.",
          "- Skills co-occurring with Kubernetes: " + ", ".join(f"{s} {pct(v)}" for s, v in res["k8s_us"]["co_occurring"]) + ".", ""]
    if res.get("remote"):
        r = res["remote"]
        L += [f"- In {r['us_postings_with_text']} US postings from the {r['scrape']} scrape, {pct(r['mention_remote'])} mention "
              f"\"remote\" and {pct(r['mention_hybrid'])} mention \"hybrid\" in the text (rough keyword match).", ""]
    L += ["## Top US employers (unique postings)", "", "| Employer | Postings |", "|---|---|"]
    L += [f"| {c} | {n} |" for c, n in res["top_us_employers"]]
    L += ["", "## Chicago postings in the dataset", ""]
    L += [f"- {c}: {t}" for c, t in res["chicago"]]
    L += ["", "## Caveats", "",
          "- Single source (builtin.com); skewed to large repeat posters (e.g. Capital One).",
          "- Skills were extracted by an LLM and count only when a posting spells them out, so shares are a floor.",
          "- Each scrape is a cross-section: shares describe the mix of postings, not hiring volume or salary.",
          "- Keyword presence is not seniority: a tool named in 2% of postings can still matter for a specific employer.", "",
          "## How this shaped the lab", "",
          "See `docs/skills-evidence-map.md` for the skill-by-skill mapping to repo artifacts.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="sparse-clone the dataset at the pinned commit")
    ap.add_argument("--data", type=Path, help="path to an existing job-market/ directory")
    ap.add_argument("--remote", action="store_true", help="also scan raw descriptions for remote/hybrid (needs data_raw)")
    a = ap.parse_args()
    if not (a.fetch or a.data):
        ap.error("pass --fetch or --data")
    data = fetch(a.remote) if a.fetch else a.data
    rows = load(data)
    if not rows:
        print("no postings found", file=sys.stderr)
        return 1
    res = analyse(rows, data, a.remote)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "market-analysis.md").write_text(render(res))
    (ROOT / "analysis" / "job_market" / "results.json").write_text(json.dumps(res, indent=2, default=list))
    print(f"unique={res['unique']} us={res['us']} -> docs/market-analysis.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
