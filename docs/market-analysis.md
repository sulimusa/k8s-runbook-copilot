# Job-market analysis (US focus)

_Generated 2026-10-05 by `analysis/job_market/analyze.py` from dataset commit `ed5903195532` (scrapes 2026-02-04 to 2026-09-23)._

Data: AI Engineering Field Guide job-market dataset by Alexey Grigorev (builtin.com postings, LLM-enriched). Only aggregate numbers are reproduced here; raw postings are not redistributed.

## Sample

- 8,051 scraped rows, **7,375 unique** after collapsing re-posted listings on company + title + location (job ids differ per scrape, so id-based dedupe does nothing).
- **3,160 US** postings (43%), 4,215 non-US (mostly India, UK, Germany).
- 1,714 US postings are located only as "USA" (city unknown, may be remote).
- Chicago is too thin to analyse: 15 unique postings. Treat the **US** as the market.

## Skill share of postings: US vs non-US

**GenAI**

| Skill | US | Non-US |
|---|---|---|
| RAG | 37.8% | 42.6% |
| AI Agents | 43.6% | 40.0% |
| Agentic Workflows | 33.9% | 30.8% |
| LLM Evaluation | 27.6% | 19.8% |
| Guardrails | 15.8% | 11.2% |
| Function Calling | 16.9% | 13.0% |
| MCP | 14.1% | 15.2% |
| Prompt Engineering | 33.0% | 36.6% |
| LangChain | 16.9% | 25.6% |
| LangGraph | 11.1% | 16.6% |
| Fine-Tuning | 17.0% | 19.0% |
| Responsible AI | 7.9% | 9.9% |

**Languages**

| Skill | US | Non-US |
|---|---|---|
| Python | 66.8% | 72.7% |
| TypeScript | 23.2% | 17.3% |
| Java | 15.9% | 18.4% |
| Go | 14.7% | 8.8% |
| SQL | 17.0% | 21.4% |

**Cloud**

| Skill | US | Non-US |
|---|---|---|
| AWS | 36.8% | 42.0% |
| Azure | 23.2% | 34.0% |
| GCP | 24.2% | 29.0% |
| AWS Bedrock | 6.4% | 8.1% |

**Ops**

| Skill | US | Non-US |
|---|---|---|
| CI/CD | 29.5% | 42.5% |
| Docker | 18.0% | 29.2% |
| Kubernetes | 19.8% | 27.7% |
| Observability | 24.9% | 18.8% |
| Monitoring | 13.7% | 14.4% |
| MLOps | 12.8% | 19.9% |
| Model Deployment | 13.5% | 14.1% |
| Terraform | 10.2% | 10.0% |

**Data stores**

| Skill | US | Non-US |
|---|---|---|
| Vector Databases | 22.2% | 24.7% |
| PostgreSQL | 11.7% | 10.4% |
| pgvector | 3.0% | 3.4% |
| Pinecone | 5.4% | 8.5% |
| Weaviate | 4.1% | 5.6% |
| Elasticsearch | 1.2% | 2.1% |

**Web**

| Skill | US | Non-US |
|---|---|---|
| APIs | 27.1% | 26.1% |
| React | 14.9% | 15.2% |
| FastAPI | 6.5% | 12.1% |
| REST APIs | 11.5% | 20.4% |
| Microservices | 9.5% | 18.8% |

**Telemetry tools**

| Skill | US | Non-US |
|---|---|---|
| OpenTelemetry | 2.2% | 3.2% |
| Prometheus | 2.5% | 4.2% |
| Grafana | 3.2% | 4.4% |

## Role mix and shape (US)

- AI-first 71.8%, AI-support (platforms, infra, tooling) 23.7%, ML-first 3.8%.
- Customer-facing roles: US 21.2% vs non-US 14.3%.
- Kubernetes appears in 19.8% of US postings (627); 63.5% of those are AI-first roles, so it is mostly a plus inside AI-first jobs.
- Skills co-occurring with Kubernetes: Python 82.6%, LLMs 66.0%, Docker 64.3%, AWS 60.6%, CI/CD 53.3%, GCP 44.0%, AI Agents 44.0%, RAG 43.9%, Machine Learning 37.3%, Azure 37.2%.

- In 423 US postings from the 2026-09-23 scrape, 36.9% mention "remote" and 21.0% mention "hybrid" in the text (rough keyword match).

## Top US employers (unique postings)

| Employer | Postings |
|---|---|
| Capital One | 114 |
| NVIDIA | 41 |
| PwC | 35 |
| BJAK | 28 |
| Microsoft | 28 |
| New York Life Insurance Company | 27 |
| Life360 | 25 |
| Photon | 22 |
| Thomson Reuters | 20 |
| Scale AI | 18 |

## Chicago postings in the dataset

- Applico Capital: Ontology Engineer - Applied AI & Data Platforms
- DV Trading: AI Engineer
- DV Trading: Senior AI Engineer
- DriveWealth: Principal AI Engineer
- Hudson River Trading: Experienced Software Engineer - AI Tools
- Ironclad: AI Engineer
- Ironclad: Staff Software Engineer - Applied AI
- Okta: Senior Software Engineer, AI Agentic Experience (Auth0)
- OneStream Software: Associate AI Engineer
- Ovative Group: AI Engineer
- Ovative Group: Lead AI Engineer
- Ovative Group: Lead Engineer, AI & Business Intelligence
- Qumis: Founding Staff AI Engineer
- Salesforce: Lead AI Engineer, Data Solutions
- Salesforce: Principal AI Engineer

## Caveats

- Single source (builtin.com); skewed to large repeat posters (e.g. Capital One).
- Skills were extracted by an LLM and count only when a posting spells them out, so shares are a floor.
- Each scrape is a cross-section: shares describe the mix of postings, not hiring volume or salary.
- Keyword presence is not seniority: a tool named in 2% of postings can still matter for a specific employer.

## How this shaped the lab

See `docs/skills-evidence-map.md` for the skill-by-skill mapping to repo artifacts.
