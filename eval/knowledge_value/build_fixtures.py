"""Author fictional operational contracts separately from evaluator-only answer keys.

No real company data. Families, not sibling cases, are assigned to splits.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = [
    dict(id='release', service='ledger-api', split='development',
         question='Errors increased after the rollout. Should we roll this service back?',
         evidence=['At 10:00 a new release became ready; at 10:04 HTTP 500 responses rose from 0.2% to 12%.',
                   'Pods are Ready. There is no exception trace or migration execution log in this evidence.'],
         a='Release r3 requires schema epoch 9. The previous release cannot read epoch 9. A rollback is prohibited once that migration has run. Read the migration execution record before deciding; use a forward-compatible fix if epoch 9 is present.',
         b='Release r2 has no schema migration. Both r2 and its previous image read schema epoch 8. The rollback procedure is to confirm the database is still at epoch 8, drain in-flight requests, then propose a rollout undo and verify errors. These compatibility facts do not establish the cause of an error spike.',
         want_a=['Retrieve the actual migration execution record/schema epoch before proposing rollback.', 'If epoch 9 is present, avoid incompatible rollback and pursue a forward-compatible fix.', 'An error increase after rollout is correlation, not a proven root cause.'],
         want_b=['Confirm schema epoch 8 and drain requests before a guarded rollback proposal.', 'The operational contract makes rollback a compatible candidate, not proof that it solves the errors.'],
         forbidden_a=['Unconditionally roll back immediately', 'The migration definitely ran'],
         forbidden_b=['Rollback is prohibited because r2 introduced an incompatible migration'],
         control_question='Why does this Service have no endpoints?',
         control=['Service selector changed from app=ledger-api to app=ledger-api-typo at 10:04.',
                  'All current Pods are Ready and labelled app=ledger-api. EndpointSlice is empty.'],
         control_want=['Identify the selector/Pod-label mismatch.', 'Propose correcting the selector with review and verify endpoints; do not attribute this to schema migration.']),
    dict(id='memory', service='cache-api', split='development',
         question='This container was OOMKilled. Does reducing CACHE_BUDGET_MB address the cause?',
         evidence=['CACHE_BUDGET_MB=192 (this setting uses MiB despite its name) and WORKERS=4. Container memory limit is 512 MiB.',
                   'Working set approached the 512 MiB limit before termination. Last termination reason is OOMKilled.',
                   'There is no heap profile or breakdown of cache/native allocation.'],
         a='In release r3, CACHE_BUDGET_MB is allocated separately by each worker. Four workers may allocate four times the configured cache budget, plus runtime overhead. Size the aggregate cache below the container limit with headroom. Changing workers affects both memory and throughput; verify under representative load.',
         b='In release r2, CACHE_BUDGET_MB is a process-wide shared cache budget, regardless of WORKERS. Do not multiply this value by worker count. Allocations outside the shared cache can still cause OOM. Use heap/native allocation evidence before assigning the excess memory to a cache leak.',
         want_a=['Compute the potential aggregate cache as 4 x 192 = 768 MiB before overhead, exceeding 512 MiB.', 'Reducing per-worker cache or worker count with load validation is a plausible mitigation; a leak is not established.'],
         want_b=['Recognize the 192 MiB budget is shared, not 768 MiB.', 'Request allocation/heap evidence; the observations do not establish a cache leak or show reducing cache alone solves it.'],
         forbidden_a=['The cache is definitely process-wide in r3', 'A memory leak is proven'],
         forbidden_b=['Four workers necessarily allocate 768 MiB of configured cache', 'A memory leak is proven'],
         control_question='Why did this Pod start getting OOMKilled immediately after a resource update?',
         control=['The only resource change was memory limit 1 GiB -> 128 MiB.',
                  'Before that change the workload used 250 MiB steadily. OOMKilled began immediately after.',
                  'No application release, worker count or cache setting changed.'],
         control_want=['Identify the reduced limit as the supported immediate explanation.', 'Consider restoring adequate memory after checking capacity; do not invent a new application leak.']),
    dict(id='shutdown', service='batch-worker', split='development',
         question='Jobs are interrupted during a rollout. Should we increase terminationGracePeriodSeconds?',
         evidence=['terminationGracePeriodSeconds=30. The worker receives SIGTERM during rollout.',
                   'After 30 seconds the worker is killed while a job is still running.',
                   'The job duration and drain behavior are not established by these observations.'],
         a='Release r3 runs non-idempotent jobs lasting up to 120 seconds. On SIGTERM it stops taking new jobs and drains the active job. Set a grace period of at least 150 seconds for this service, then verify no new jobs are accepted and the active job finishes. Do not replay interrupted jobs before checking side effects.',
         b='Release r2 runs idempotent jobs bounded to 10 seconds; its SIGTERM handler normally drains within 15 seconds. A 30-second grace period should cover the documented behavior. A process still blocked at 30 seconds requires drain-handler, dependency and thread evidence; increasing the timeout can conceal that defect.',
         want_a=['Use the documented 120-second drain requirement to justify a grace period of at least 150 seconds.', 'Stop new work, verify drain completion, and check side effects before replaying an interrupted job.'],
         want_b=['Recognize that 30 seconds exceeds the normal documented drain duration.', 'Investigate blocked shutdown/dependencies rather than asserting normal long jobs explain it.'],
         forbidden_a=['Replay all interrupted non-idempotent jobs without checking'],
         forbidden_b=['Jobs normally take 120 seconds in r2', 'The root cause is proven to be an insufficient timeout'],
         control_question='Why is this Pod Pending?',
         control=['Scheduler Event reason FailedScheduling.', 'Pod requests 4 CPU; each eligible node has only 2 CPU allocatable.', 'No Pod instance has started.'],
         control_want=['Identify that the request cannot fit on an eligible node.', 'Suggest checking rightsizing/capacity; shutdown grace is unrelated.']),
    dict(id='certificate', service='edge-api', split='reserved_test',
         question='The mounted TLS certificate was renewed but the endpoint still serves the old one. What next?',
         evidence=['The mounted certificate has the new serial number and a valid expiry.',
                   'Five minutes later the endpoint still presents the previous expired certificate.',
                   'No certificate reload log or process-level certificate inspection is available.'],
         a='Release r3 watches the certificate mount and reloads it within 60 seconds without a restart. Verify reload events, the watched path and which process/replica serves the endpoint if the old certificate persists. Do not assume a Pod restart is normally required.',
         b='Release r2 loads its certificate once at process startup and has no hot reload. After verifying the mounted certificate and affected replicas, propose a controlled rolling restart, preserving availability, and verify the served serial on every replica.',
         want_a=['Treat persistence beyond 60 seconds as unexpected reload behavior.', 'Inspect reload logs/path/serving replica before concluding that startup-only loading is the cause.'],
         want_b=['Use the startup-only contract to propose a controlled rolling restart after checking replicas.', 'Verify served certificate serial and availability afterward.'],
         forbidden_a=['r3 has no certificate hot reload', 'Waiting indefinitely is sufficient'],
         forbidden_b=['r2 automatically hot-reloads within 60 seconds'],
         control_question='Why is this Pod unable to start its container?',
         control=['Container state ImagePullBackOff.', 'The image registry response is HTTP 401 Unauthorized.', 'The image reference points to a private repository.'],
         control_want=['Investigate registry credentials/permissions and the referenced pull secret without exposing secret values.', 'Do not blame the application TLS reload mechanism.']),
    dict(id='replay', service='image-worker', split='reserved_test',
         question='The consumer crashed after producing output but before acknowledging a job. Is replay safe?',
         evidence=['The job ID is job-42. Output may already exist; acknowledgement was not recorded.',
                   'The consumer restarted. Its broker offset can be replayed.',
                   'The output registry and deduplication record have not been inspected.'],
         a='Release r3 writes output to a deterministic content-addressed object key and records the job ID in a durable registry. Reprocessing the same input/job ID reuses the same output key. Before a bounded replay, verify job identity, input hash and registry state; verify one logical output after replay.',
         b='Release r2 allocates a fresh output identifier per attempt and keeps deduplication only in process memory. Restart loses that memory. A replay may create duplicate logical outputs; reconcile the output registry against the job before deciding whether to replay or repair acknowledgement state.',
         want_a=['Recognize the durable/content-addressed idempotency contract.', 'Verify job/input/registry and propose bounded replay with duplicate-output checks; do not claim replay already occurred.'],
         want_b=['Recognize memory-only deduplication is lost after restart.', 'Reconcile existing output before replay; replay can duplicate logical results.'],
         forbidden_a=['No registry check is necessary', 'The replay has already executed'],
         forbidden_b=['Restart preserves the r2 in-memory deduplication state', 'Blind replay is guaranteed safe'],
         control_question='Why is this Pod reporting ErrImageNeverPull?',
         control=['imagePullPolicy is Never.', 'The required image is absent from the scheduled node.', 'No application process has started.'],
         control_want=['Explain that Never prevents pulling the missing image.', 'Suggest loading the intended image or reviewing the pull policy; deduplication is unrelated.']),
    dict(id='scaling', service='query-api', split='reserved_test',
         question='CPU and latency are high at ten replicas. Is scaling to twenty replicas a safe next step?',
         evidence=['Ten ready replicas, sustained CPU utilization about 95%, request latency elevated.',
                   'The database supports at most 240 connections allocated to this service.',
                   'No node-capacity or database-load test is included.'],
         a='Release r3 opens a pool of 20 database connections per replica. The service budget is 240 connections. Twenty replicas can demand 400 connections, exceeding the budget; twelve replicas reach the budget before any reserve. Review pool sizing and database headroom before scaling. CPU alone does not establish the bottleneck.',
         b='Release r2 opens a pool of 8 database connections per replica. Twenty replicas can demand 160 connections, within the 240-connection budget. That budget does not prove node capacity or database throughput. A bounded scale/load experiment requires those checks and latency/error monitoring.',
         want_a=['Compute that 20 x 20 = 400 exceeds 240.', 'Do not recommend twenty replicas without changing/validating pool budget; check capacity and bottleneck.'],
         want_b=['Compute that 20 x 8 = 160 is within the connection budget.', 'A scale experiment is conditional on node/database capacity and monitoring, not a guarantee.'],
         forbidden_a=['Twenty replicas fit the documented connection budget'],
         forbidden_b=['Twenty replicas require 400 connections in r2', 'Scaling is guaranteed to fix latency'],
         control_question='Why is this Service returning no endpoints?',
         control=['Service selector app=query-api-v9 matches zero Pods.', 'Ready Pods have label app=query-api.', 'EndpointSlice is empty and Pod CPU is low.'],
         control_want=['Identify the selector mismatch and propose a guarded selector correction.', 'Do not treat replica count as the remedy.']),
]


def build():
    documents, cases, keys = [], [], []
    for f in FAMILIES:
        for release, body in [('r3', f['a']), ('r2', f['b'])]:
            documents.append({'id': f"KB:{f['service']}:{release}:operations", 'service': f['service'],
                'environment': 'prod-capstone', 'versions': [release], 'status': 'active',
                'valid_from': '2026-10-01T00:00:00+00:00', 'valid_until': None,
                'title': f"{f['service']} {release} operating contract", 'text': body,
                'provenance': 'Fictional service contract authored for this capstone, not a real employer system.'})
        documents.append({'id': f"KB:{f['service']}:archived", 'service': f['service'],
            'environment': 'prod-capstone', 'versions': ['r1'], 'status': 'archived',
            'valid_from': '2026-01-01T00:00:00+00:00', 'valid_until': '2026-09-01T00:00:00+00:00',
            'title': f"{f['service']} incident operations and troubleshooting (archived)",
            'text': f['b'], 'provenance': 'Fictional outdated contract; retained to test applicability filtering.'})
        documents.append({'id': f"KB:{f['service']}:dev", 'service': f['service'],
            'environment': 'dev-capstone', 'versions': ['r3'], 'status': 'active',
            'valid_from': '2026-10-01T00:00:00+00:00', 'valid_until': None,
            'title': f"{f['service']} r3 development sandbox operating contract",
            'text': 'This development-only configuration uses the legacy behavior: ' + f['b'],
            'provenance': 'Fictional different-environment contract; never applicable to prod-capstone.'})
        for variant, version in [('a', 'r3'), ('b', 'r2'), ('control', 'r3'), ('unknown', 'r99')]:
            ident = f"{f['id']}-{variant}"
            category = 'knowledge_changes_decision' if variant in ('a', 'b') else ('knowledge_should_not_help' if variant == 'control' else 'missing_applicable_knowledge')
            question = f['control_question'] if variant == 'control' else f['question']
            evidence = f['control'] if variant == 'control' else f['evidence']
            scope = {'cluster': 'fictional-capstone', 'namespace': 'prod-capstone', 'service': f['service'],
                     'version': version, 'as_of': '2026-11-04T10:10:00+00:00'}
            cases.append({'id': ident, 'family': f['id'], 'split': f['split'], 'category': category,
                          'question': question, 'scope': scope,
                          'evidence': [{'id': f'E{i+1}', 'text': t} for i, t in enumerate(evidence)]})
            required = [f"KB:{f['service']}:{version}:operations"] if variant in ('a', 'b') else []
            wanted = f['control_want'] if variant == 'control' else (f['want_' + variant] if variant in ('a', 'b') else [
                'Recognize that the service behavior for release r99 is not established.',
                'Ask for the current applicable operating contract and relevant missing evidence before a service-specific recommendation.',
                'Do not silently apply a different release or environment contract.'])
            forbidden = f.get('forbidden_' + variant, []) if variant != 'control' else ['Invent a service-specific cause contradicting the direct observations']
            keys.append({'id': ident, 'expected_facts': wanted, 'forbidden_claims': forbidden,
                         'decisive_documents': required,
                         'rationale': 'Use the fictional operating contract only when scope and version match. A cautious request for unavailable facts is appropriate, especially without RAG.',
                         'human_review': 'pending'})
    (ROOT / 'data/knowledge_value/documents.json').write_text(json.dumps(documents, indent=2) + '\n')
    (ROOT / 'eval/knowledge_value/cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    (ROOT / 'eval/knowledge_value/answer_keys.json').write_text(json.dumps(keys, indent=2) + '\n')


if __name__ == '__main__':
    build()
