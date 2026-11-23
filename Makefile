.PHONY: atlas-run atlas-judge atlas-monitoring agent-access agent agent-eval install fetch ingest index search test eval-retrieval eval serve ui lab market audit lint dashboard \
	image obs-up platform-up promote rollback platform-down helm-lint incident-validate incident-export incident-prepare rollout-demo

atlas-run: ## actual model runs; explicit configured key/prices/budget; use a NEW RUN_DIR
	python -m eval.atlas_eval investigate --directory $(RUN_DIR)

atlas-judge: ## evaluate saved runs in a separate model context
	python -m eval.atlas_eval judge --directory $(RUN_DIR)

atlas-monitoring: ## isolated loopback Grafana :13000 and OTLP :14318
	docker compose -p capstone-atlas -f compose.atlas-monitoring.yaml up -d

rollout-demo: ## offline synthetic replay; output JSON + HTML (use a new OUT path for repeat runs)
	python -m runbook_copilot.investigation --case $(or $(CASE),routing) --mode $(or $(MODE),rag) --output $(or $(OUT),eval/reports/atlas-demo.json)

incident-prepare: ## freeze a new comparison; defaults to eval/reports/comparison-first
	python -m eval.incident_comparison prepare --directory $(or $(RUN_DIR),eval/reports/comparison-first)

incident-validate: ## validate synthetic cases; no API key or cluster required
	python -m eval.incident_eval validate

incident-export: ## export both comparison arms; answer keys are excluded
	python -m eval.incident_eval export --mode baseline --output eval/reports/baseline-prompts.json
	python -m eval.incident_eval export --mode patterns --output eval/reports/pattern-prompts.json

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
	streamlit run app/ui.py --server.address 127.0.0.1 --server.port 8501

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

.PHONY: history-image history-install history-demo history-chat
HISTORY_IMAGE ?= runbook-history:capstone-v4
history-image: ## build the isolated collector; no credentials or corpus bundled
	docker build -f Dockerfile.history -t $(HISTORY_IMAGE) .

history-install: ## dedicated capstone kubeconfig only; also refreshes 8-hour dev access
	kind load docker-image $(HISTORY_IMAGE) --name runbook-capstone
	HISTORY_IMAGE=$(HISTORY_IMAGE) python deploy/history/install.py

history-demo: ## install synthetic workloads into dev and production-mode lab namespaces
	kubectl --kubeconfig .agent/capstone-admin.kubeconfig --context kind-runbook-capstone -n dev-capstone apply -f deploy/history/demo.yaml
	kubectl --kubeconfig .agent/capstone-admin.kubeconfig --context kind-runbook-capstone -n prod-capstone apply -f deploy/history/demo.yaml

history-chat: ## host-side model credentials; collector remains read-only
	streamlit run app/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false

.PHONY: knowledge-study-prepare knowledge-study-audit knowledge-study-test
STUDY_DIR ?= eval/reports/knowledge-value-development-v3
knowledge-study-prepare: ## offline: freeze cases, corpus and prompts; fails if directory exists
	python -m eval.knowledge_value.study prepare $(STUDY_DIR)

knowledge-study-audit: ## offline: document selection and conservative cost estimate
	python -m eval.knowledge_value.study audit $(STUDY_DIR)
	python -m eval.knowledge_value.study estimate $(STUDY_DIR)

knowledge-study-test: ## protocol tests, never provider calls
	pytest -q tests/test_knowledge_value.py

.PHONY: history-compare history-demo-test
history-compare: ## six paid investigations; use a new RUN_DIR; preserves previous attempts
	python -m eval.history_demo $(RUN_DIR)

history-demo-test: ## offline controls and isolation checks
	pytest -q tests/test_history.py tests/test_history_demo.py

.PHONY: submission-check capstone-demo
capstone-demo: ## locked install first: uv sync --locked --all-extras
	uv run --frozen --all-extras streamlit run app/ui.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false

submission-check: ## offline checks; no API calls or Kubernetes access
	uv run --frozen --all-extras ruff check src app eval tests analysis observability scripts
	uv run --frozen --all-extras pytest -q
	uv run --frozen --all-extras python scripts/check_submission.py
