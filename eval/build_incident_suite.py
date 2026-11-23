"""Build original synthetic evidence, isolated answer keys and reference-pattern summaries.

No article text, cluster access, random generation or external calls. These are authored
diagnostic exercises, not logs captured from the companies or reproduced kernel bugs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Source synopses are independently maintained: never derive them from fictional keys.
SOURCE_SUMMARIES = {
    'host-routing': 'Datadog reports that a systemd-networkd restart removed pod routing rules during unattended updates across environments.',
    'rollout-api-load': 'Reddit reports that cached-image startup synchronized large LIST requests and exhausted control-plane VM memory.',
    'gitops-pruning': 'Skyscanner reports a templating change producing an empty desired state and automated reconciliation deleting resources.',
    'selector-concentration': 'Grafana reports a Service selector excluding old replicas, concentrating traffic on a small updated subset and causing OOMs.',
    'delayed-identity': 'Stytch reports a deleted shared instance profile, failed replacement provisioning and delayed failures on existing nodes. Exact credential expiry and role-removal API calls are fixture details, not verified historical observations.',
    'pdb-endpoint': 'GitLab reports that a PDB prevented Redis pod eviction while a GKE controller independently removed its load-balancer endpoint.',
    'tls-keepalive': 'Shopify reports an expired root and stale client trust bundle; existing TLS connections concealed the problem until pod replacement forced new handshakes.',
    'volume-ownership': 'Cloudflare reports long pod startup delays while kubelet recursively changed volume group ownership across many files.',
    'observer-tail-latency': 'Pinterest links rare latency to cAdvisor memory inspection. The precise kernel locking explanation remains qualified; direct lock traces and a controlled re-enable experiment in our exercise are fictional evidence.',
    'dns-stale-state': 'Preply reports DNS failures after CoreDNS scale-down with traffic directed to a removed endpoint. The underlying conntrack cleanup failure was not conclusively established.',
    'webhook-lifecycle': 'ACRL reports a fail-open webhook certificate race followed by mutation errors: ordinary Pod updates failed on nodeSelector changes and kubelet status updates failed on label changes.',
    'node-bootstrap': 'FREE NOW reports that a moved package invalidated a hardcoded bootstrap URL, leaving launched worker instances unable to join Kubernetes.'
}

# name, company, source, symptom, common observation, supported evidence, cause,
# look-alike evidence, different cause, next discriminating check.
FAMILIES = [
    (
        'host-routing', 'Datadog',
        'https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-platform-level-impact/',
        'Cross-node pod connections timed out after a routine maintenance window.',
        '09:02Z Deployment ledger-api has 4/4 Ready pods; same-node requests succeed; cross-node requests time out.',
        ['09:00Z host journal: unattended package update restarted systemd-networkd on both affected workers.',
         '09:01Z routing snapshot: pod policy-routing rules present before maintenance are absent afterward. CNI desired configuration is unchanged.'],
        'Host network maintenance removed required pod policy-routing rules.',
        ['09:00Z host journal: no package updates or network service restarts. Pod policy-routing rules match the pre-incident snapshot.',
         '09:01Z cloud flow logs: cross-node pod traffic REJECT. Firewall audit: the inter-worker allow rule was removed at 09:00Z.'],
        'A cloud firewall change blocks cross-node traffic while host routing remains intact.',
        'Compare host routing and maintenance history with cloud firewall decisions for the failed packet path.'
    ),
    (
        'rollout-api-load', 'Reddit',
        'https://www.reddit.com/r/RedditEng/comments/1id01im/unseen_catalyst_a_simple_rollout_caused_a/',
        'A node-agent rollout coincided with API timeouts and slow scheduling.',
        '10:10Z API p99 latency rose sharply while node-agent pods started; application deployment content was unchanged.',
        ['10:09Z runtime events: the new node-agent image was already cached on 240 nodes; their start times fall in the same 8-second interval.',
         '10:10Z audit aggregation: node-agent issued 240 unpaginated LIST pods requests concurrently. API-server RSS then crossed its memory limit.'],
        'Near-simultaneous node-agent startup with cached images produced concurrent unpaginated LIST requests and API-server memory pressure above its configured limit.',
        ['10:09Z runtime events: image pulls took several minutes; node-agent startup and LIST traffic remained at their normal rate.',
         '10:10Z etcd fsync p99 increased from 4ms to 1800ms during a storage snapshot; API-server memory stayed below half its limit.'],
        'Etcd storage latency during a snapshot slows the API, rather than a node-agent LIST storm.',
        'Compare audit request concurrency and API memory with etcd fsync latency and the rollout start-time distribution.'
    ),
    (
        'gitops-pruning', 'Skyscanner',
        'https://medium.com/@SkyscannerEng/how-a-couple-of-characters-brought-down-our-site-356ccaf1fbc3',
        'Services vanished from the cluster shortly after an infrastructure change.',
        '11:05Z gateway returns 503; several application Services are absent, but the Kubernetes API is responsive.',
        ['11:00Z GitOps render diff: previous revision contains 18 application resources; new revision contains zero after a template condition changed.',
         '11:01Z audit events: GitOps controller DELETE requests removed those 18 resources; automated pruning was enabled.'],
        'An empty rendered desired state combined with automated pruning removed live application resources.',
        ['11:00Z GitOps render diff is empty; desired and live configuration matched immediately before the incident.',
         '11:01Z audit events: a cleanup service account explicitly deleted the affected namespaces; no GitOps DELETE requests occurred.'],
        'A cleanup identity deleted namespaces; the evidence does not support an empty-render GitOps prune.',
        'Inspect rendered desired state and the identity, timestamps and targets of resource deletion audit events.'
    ),
    (
        'selector-concentration', 'Grafana Labs',
        'https://grafana.com/blog/how-adding-kubernetes-label-selectors-caused-an-outage-in-grafana-cloud-logs-and-how-we-resolved-it/',
        'A rolling update stalled while new pods repeatedly ran out of memory.',
        '12:10Z old ReplicaSet has 8 Ready pods; new ReplicaSet has 2 pods restarting with OOMKilled; requests return intermittent 503.',
        ['12:09Z Service selector: app=ingester, generation=next. Old pods have generation=previous; new pods have generation=next.',
         '12:10Z EndpointSlice includes only the two new pods. Their request rate is five times the old per-pod rate; controlled equal-rate tests show no memory regression.'],
        'The Service selector excludes old replicas and concentrates traffic on the new pods.',
        ['12:09Z Service selector is app=ingester; EndpointSlice includes all ten pods and observed per-pod request rates are comparable.',
         '12:10Z equal-rate load test: new image RSS rises continuously to its limit; previous image RSS stabilizes under the same workload.'],
        'The new image has a workload-related memory regression; endpoint selection is not concentrating traffic.',
        'Compare Service selectors and EndpointSlices with per-pod traffic and equal-workload memory profiles.'
    ),
    (
        'delayed-identity', 'Stytch',
        'https://stytch.com/blog/stytch-postmortem-2023-02-23/',
        'Cloud API access stopped and replacement nodes failed after a quiet interval.',
        '13:40Z existing workers report cloud credential failures; newly requested workers fail to initialize.',
        ['12:40Z fictional IAM audit: RemoveRoleFromInstanceProfile removed the role, then DeleteInstanceProfile successfully deleted the shared profile referenced by a retired node group and active workers.',
         '13:40Z cached worker credentials expire. Replacement provisioning reports instance profile not found; instance clock offset is 0.1 seconds.'],
        'A shared instance profile was deleted; cached credentials delayed symptoms and replacements cannot obtain the profile.',
        ['13:40Z IAM profile exists and is unchanged; provisioning successfully resolves it. No deletion event exists.',
         '13:40Z signing errors report RequestExpired; node clock is 19 minutes behind trusted time after time synchronization stopped.'],
        'Node clock skew invalidates signed cloud requests; profile deletion is contradicted.',
        'Inspect instance-profile references and audit history, credential expiry and trusted clock offset without exposing credentials.'
    ),
    (
        'pdb-endpoint', 'GitLab',
        'https://gitlab.com/gitlab-com/gl-infra/production/-/issues/21208',
        'A running Redis pod became unreachable through its internal load balancer.',
        '14:02Z Redis pod is Running and Ready. Clients using the internal load-balancer address time out.',
        ['14:01Z eviction event: blocked by PodDisruptionBudget. Direct in-cluster connection to Redis pod IP still succeeds.',
         '14:01Z load-balancer controller audit: pod endpoint removed from network endpoint group during the same scaling operation; group now has zero endpoints.'],
        'The load-balancer endpoint was removed independently of the PDB-protected pod.',
        ['14:01Z endpoint group contains the pod and external target health is healthy. Direct pod-IP requests from the client namespace also time out.',
         '14:01Z policy audit: a new ingress NetworkPolicy selects Redis and excludes the client namespace; flow logs show matching policy drops.'],
        'A NetworkPolicy blocks client traffic; the load-balancer endpoint still exists.',
        'Compare direct pod reachability, endpoint-group membership, target health and network-policy drop evidence.'
    ),
    (
        'tls-keepalive', 'Shopify',
        'https://shopify.engineering/that-old-certificate-expired-and-started-an-outage-this-is-what-happened-next',
        'Newly deployed pods fail TLS calls while old pods continue serving.',
        '15:12Z new pods fail authentication-service calls; old pods continue using established TLS connections successfully.',
        ['15:10Z failed handshake: certificate verify failed, expired trust anchor. Leaf certificate is valid; hostname matches.',
         '15:12Z new connections from old pods also fail. Bundled client CA store trusts only the expired root; a client using the current system CA store succeeds.'],
        'An outdated trust store fails new TLS handshakes; existing keepalive connections concealed the expired-root problem.',
        ['15:10Z failed handshake: hostname mismatch; presented certificate SAN contains auth.internal, but the new deployment calls login.internal.',
         '15:12Z both deployments have the same current CA store; new connections to auth.internal succeed from old and new pods.'],
        'A changed upstream hostname does not match the certificate; root expiry is not supported.',
        'Compare fresh versus reused connections, certificate SAN/validity, request hostname and the actual client trust store.'
    ),
    (
        'volume-ownership', 'Cloudflare',
        'https://blog.cloudflare.com/one-line-kubernetes-fix-saved-600-hours-a-year/',
        'A stateful tool takes a long time to start after replacement.',
        '16:05Z replacement pod has not started its application; its PVC contains millions of small files.',
        ['16:01Z volume attachment succeeded; kubelet is walking the mounted filesystem and changing group ownership for fsGroup.',
         '16:05Z storage reads are normal; ownership-operation count increases continuously. Application starts only after this traversal completes.'],
        'Recursive volume ownership processing delays startup before the application runs.',
        ['16:01Z CSI attach event: Multi-Attach error; volume is still attached to the previous node, which is NotReady.',
         '16:05Z no successful volume mount or ownership traversal occurred on the replacement; application has never started.'],
        'A stale volume attachment prevents mounting, rather than recursive ownership changes delaying startup.',
        'Establish whether delay occurs during attach, mount, ownership processing or application initialization.'
    ),
    (
        'observer-tail-latency', 'Pinterest',
        'https://medium.com/pinterest-engineering/debugging-the-one-in-a-million-failure-migrating-pinterests-search-infrastructure-to-kubernetes-bef9af9dabf4',
        'Rare search latency spikes appeared after moving workloads to Kubernetes.',
        '17:00Z average request latency is stable, but rare requests exceed the tail-latency objective; average node CPU is not saturated.',
        ['17:01Z correlated traces: slow requests wait on a memory-map lock while the metrics collector reads process mapping information.',
         '17:20Z controlled isolated comparison: disabling only that collector inspection removes the stalls; re-enabling reproduces them under equal request load.'],
        'Collector memory-map inspection contends with application memory operations and causes rare stalls.',
        ['17:01Z slow-request intervals do not align with collector activity; no memory-map lock contention appears in captured profiles.',
         '17:20Z slow intervals align with stop-the-world garbage collection; allocation reduction removes stalls while collector settings remain unchanged.'],
        'Application garbage-collection pauses explain the tail latency; collector contention is contradicted.',
        'Correlate tail requests with profiles, collector timing and GC pauses; use a bounded isolated comparison.'
    ),
    (
        'dns-stale-state', 'Preply',
        'https://medium.com/preply-engineering/dns-postmortem-e169efd45afd',
        'Some pods have intermittent DNS timeouts after CoreDNS scaled down.',
        '18:03Z two CoreDNS replicas are Ready; only a subset of clients times out, and successful answers are correct.',
        ['18:02Z EndpointSlice no longer contains the removed CoreDNS IP. Failing-client UDP conntrack entries still map the DNS Service to that removed IP.',
         '18:03Z packet capture shows timed-out queries sent to the removed IP; a fresh client flow reaches a live DNS endpoint and succeeds.'],
        'Stale UDP connection tracking sends affected DNS flows to a removed endpoint; the reason cleanup failed remains unknown.',
        ['18:02Z EndpointSlices and conntrack destinations all point to live CoreDNS pods; no packets go to the removed IP.',
         '18:03Z affected clients are denied DNS egress by a newly selected NetworkPolicy; policy flow logs record the dropped UDP queries.'],
        'DNS egress is blocked by policy, not stale endpoint mappings.',
        'Inspect failing flow destinations and policy decisions; do not claim the underlying conntrack cleanup defect without more evidence.'
    ),
    (
        'webhook-lifecycle', 'Applied Computing Research Labs',
        'https://appliedcomputing.io/posts/2025-12-08-postmortem-ci-runner/',
        'A simulation finished its workload but never completed cleanup.',
        '19:10Z the simulation process exited successfully, but its pod remains and the simulation controller waits for cleanup.',
        ['19:00Z webhook TLS validation failed before CA injection; failurePolicy=Ignore admitted the simulation pod onto a real node.',
         '19:10Z after CA injection, the webhook matches UPDATE requests for both pods and pods/status. A job-controller ordinary Pod update is rejected because the webhook adds an immutable nodeSelector. Separately, the webhook adds labels to a kubelet pods/status update; with NodeRestriction enabled, admission rejects the label change from the node identity, and completion status never persists.'],
        'Fail-open admission during delayed CA injection allowed real-node scheduling; later webhook label mutation of kubelet status updates was rejected by NodeRestriction, blocking completion status and cleanup. Ordinary Pod updates separately failed after injected nodeSelector changes.',
        ['19:00Z webhook TLS is healthy; it handles CREATE only. Simulation pod was scheduled on the intended simulated node.',
         '19:10Z pod status is Succeeded; deletion is blocked by simulation.example/cleanup finalizer. Its owning cleanup controller is absent.'],
        'An orphaned finalizer blocks deletion after successful status update; UPDATE mutation is not the cause.',
        'Inspect admission timing and rules, accepted status updates, deletionTimestamp, finalizers and their owning controller.'
    ),
    (
        'node-bootstrap', 'FREE NOW',
        'https://github.com/freenowtech/postmortems/blob/master/2019-09-19%20-%20New%20K8s%20workers%20unable%20to%20join%20cluster.pdf',
        'Autoscaling launched instances but application pods remain Pending.',
        '20:05Z cloud group has six running instances while Kubernetes lists only two nodes; Pending pods report insufficient capacity.',
        ['20:01Z bootstrap log on all four missing nodes: required package download returned HTTP 404 at a fixed repository URL; bootstrap stopped.',
         '20:05Z image test: the package exists at a new repository path; cluster endpoint connectivity and registration identity checks succeed before package installation.'],
        'An invalid hardcoded package URL stops node bootstrap before registration.',
        ['20:01Z package installation and bootstrap completed on all four missing nodes; no download failure occurred.',
         '20:05Z kubelet registration returns Unauthorized; new instance role is missing from the cluster authentication mapping. Network connection to the API succeeds.'],
        'A missing node identity mapping blocks registration after successful bootstrap.',
        'Compare cloud instance counts with node registration, then inspect bootstrap completion and API authentication errors.'
    ),
]


def build():
    inputs, keys, patterns = [], [], []
    for n, (family, company, source, symptom, common, facts, cause, other, alternative, check) in enumerate(FAMILIES):
        split = 'development' if n < 8 else 'evaluation-candidate'
        reported = SOURCE_SUMMARIES[family]
        patterns.append({'id':f'P{n+1:02}', 'company':company, 'source_url':source,
                         'text':f'{symptom} Historical context: {reported} Useful checks: {check}',
                         'note':'Original synopsis and diagnostic suggestions; historical analogy is not proof of a current cause.'})
        for variant, details, answer in [('supported',facts,cause),('counterfactual',other,alternative),('insufficient',[],None)]:
            opaque=hashlib.sha256(f'{family}/{variant}/v1'.encode()).hexdigest()[:10]
            case_id=f'case-{opaque}'
            evidence=[{'id':'E1','text':common}]+[{'id':f'E{i+2}','text':t} for i,t in enumerate(details)]
            inputs.append({'id':case_id,'synthetic':True,'question':symptom,
                           'environment':'Fictional Kubernetes environment. Snippets are normalized observations, not raw command output. No cluster access is available.',
                           'evidence':evidence})
            keys.append({'id':case_id,'family':family,'variant':variant,'split':split,
                         'source_company':company,'source_url':source,
                         'expected_status':'insufficient_evidence' if not details else 'supported',
                         'expected_cause':answer,'decisive_evidence_ids':['E2','E3'] if details else [],
                         'required_next_check':check,
                         'contradicted_cause':cause if variant=='counterfactual' else None,
                         'review_status':'Authored draft; independent technical review pending',
                         'historical_fidelity':'Mechanism-inspired synthetic exercise; not a reproduction of the reported incident.'})
    base=ROOT/'eval'/'incident_suite'
    base.mkdir(exist_ok=True)
    for filename,rows in [('inputs.json',inputs),('answer_keys.json',keys)]:
        (base/filename).write_text(json.dumps(rows,indent=2)+'\n')
    (ROOT/'data'/'incident_patterns.json').write_text(json.dumps(patterns,indent=2)+'\n')
    print(f'Built {len(inputs)} synthetic scenarios, {len(FAMILIES)} families, {len(patterns)} source synopses.')


if __name__=='__main__':
    build()
