.PHONY: agent-access agent agent-eval install fetch ingest index search test eval-retrieval eval serve ui lab market audit lint dashboard \
	image obs-up platform-up promote rollback platform-down helm-lint

install:
	pip install -e ".[app,otel,dev]"

fetch:            ## clone public sources at pinned commits (sparse)
	python -m runbook_copilot.ingest.fetch

ingest:           ## fetch + parse + chunk -> data/processed/chunks.jsonl
	python -m runbook_copilot.ingest.run

index:            ## optional: compute embeddings for hybrid search (needs EMBED_MODEL)
	python -m runbook_copilot.retrieval.index

search:           ## make search Q="pod stuck in CrashLoopBackOff"
	python -m runbook_copilot.retrieval.search "$(Q)"

test:
	pytest -q

eval-retrieval:   ## no LLM needed
	python -m eval.run_eval --mode retrieval

eval:             ## full pipeline, needs LLM credentials
	python -m eval.run_eval --mode full

serve:
	uvicorn app.api:app --reload --port 8000

ui:
	streamlit run app/ui.py

lab:              ## make lab SCENARIO=crashloop  (needs a kind/k3d/minikube cluster)
	bash labs/capture.sh $(SCENARIO)

lint:
	ruff check src app eval tests analysis observability

audit:            ## security: static analysis + dependency vulnerabilities
	bandit -q -r src app eval analysis -x tests
	pip-audit .

market:           ## regenerate docs/market-analysis.md from the pinned open dataset
	python analysis/job_market/analyze.py --fetch

dashboard:        ## regenerate the Grafana dashboard JSON
	python observability/build_dashboard.py

image:            ## build the container image
	docker build --build-arg APP_VERSION=local -t runbook-copilot:local .

obs-up:           ## local stack: copilot + Grafana LGTM (Grafana on :3000)
	docker compose up --build

helm-lint:
	helm lint deploy/helm/runbook-copilot -f deploy/helm/runbook-copilot/values-dev.yaml
	helm lint deploy/helm/runbook-copilot -f deploy/helm/runbook-copilot/values-prod.yaml

platform-up:      ## kind + build once + deploy to dev (+ observability backend)
	bash deploy/scripts/platform-up.sh

promote:          ## promote exactly the image running in dev to prod
	bash deploy/scripts/promote.sh

rollback:         ## roll prod back one revision
	helm --kube-context kind-$${CLUSTER:-runbook-lab} rollback copilot -n prod

platform-down:
	bash deploy/scripts/platform-down.sh

agent-access:     ## identity for the agent: make agent-access ENV=dev NS=lab-oomkilled  (ENV=prod gives READ-ONLY)
	bash deploy/scripts/agent-access.sh $(ENV) $(NS)

agent:            ## make agent ENV=dev NS=lab-oomkilled INCIDENT="my pod keeps restarting"
	python -m runbook_copilot.agent --env $(ENV) -n $(NS) --kubeconfig .agent/$(ENV).kubeconfig --incident "$(INCIDENT)"

agent-eval:       ## fix-and-verify eval on a local kind cluster (needs LLM key)
	python -m eval.agent_eval
