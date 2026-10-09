#!/usr/bin/env bash
# Capture read-only evidence for one lab scenario into data/lab_evidence/<scenario>/evidence.md
#
#   bash labs/capture.sh crashloop            (or: make lab SCENARIO=crashloop)
#
# SAFETY: this script APPLIES a manifest and DELETES the namespace it created. It is run by YOU against a
# disposable local cluster (kind / k3d / minikube). It refuses to run against any other kube context.
# The Copilot application itself never executes anything.
set -euo pipefail

SCENARIO="${1:?usage: labs/capture.sh <scenario>  (see labs/scenarios/)}"
WAIT="${WAIT:-60}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SC="$HERE/scenarios/$SCENARIO"
NS="lab-$SCENARIO"
OUT_DIR="$HERE/../data/lab_evidence/$SCENARIO"
OUT="$OUT_DIR/evidence.md"

[ -f "$SC/manifest.yaml" ] || { echo "unknown scenario: $SCENARIO"; exit 1; }

CTX="$(kubectl config current-context)"
case "$CTX" in
  kind-*|k3d-*|minikube*) ;;
  *) [ "${LAB_ALLOW_CONTEXT:-}" = "1" ] || { echo "refusing to run on context '$CTX' (not kind/k3d/minikube)"; exit 1; } ;;
esac
kubectl get ns "$NS" >/dev/null 2>&1 && { echo "namespace $NS already exists; delete it first"; exit 1; }

mkdir -p "$OUT_DIR"
kubectl create ns "$NS" >/dev/null
trap 'kubectl delete ns "$NS" --wait=false >/dev/null 2>&1 || true' EXIT

echo "applying $SCENARIO in $NS, waiting ${WAIT}s ..."
kubectl apply -n "$NS" -f "$SC/manifest.yaml" >/dev/null
sleep "$WAIT"
if [ -f "$SC/update.yaml" ]; then
  echo "applying update.yaml, waiting ${WAIT}s ..."
  kubectl apply -n "$NS" -f "$SC/update.yaml" >/dev/null
  sleep "$WAIT"
fi

section() { printf '\n## %s\n\n```\n$ %s\n' "$1" "$2"; }
run() { section "$1" "$2"; bash -c "$2" 2>&1 || true; printf '```\n'; }

{
  printf -- '---\ntitle: Lab Evidence - %s\n---\n\n' "$SCENARIO"
  printf '# Lab evidence: %s\n\nCaptured from a local `%s` cluster, namespace `%s`, using read-only kubectl commands. Server: ' "$SCENARIO" "$CTX" "$NS"
  kubectl version -o json 2>/dev/null | grep -m1 gitVersion | tr -d ' ,"' || true
  echo
  echo "Scenario notes: $(grep -m3 '^#' "$SC/manifest.yaml" | sed 's/^# *//' | tr '\n' ' ')"
  run "Pod status" "kubectl get pods -n $NS -o wide"
  run "Workloads and services" "kubectl get deploy,rs,svc,endpoints -n $NS"
  run "Events" "kubectl get events -n $NS --sort-by=.lastTimestamp"
  run "Describe pods" "kubectl describe pods -n $NS"
  run "Describe deployments" "kubectl describe deployments -n $NS"
  run "Resource quota" "kubectl describe quota -n $NS"
  for p in $(kubectl get pods -n "$NS" -o name 2>/dev/null); do
    run "Logs ${p#pod/}" "kubectl logs $p -n $NS --all-containers --tail=30"
    run "Previous logs ${p#pod/}" "kubectl logs $p -n $NS --all-containers --previous --tail=30"
  done
  for d in $(kubectl get deploy -n "$NS" -o name 2>/dev/null); do
    run "Rollout status ${d#deployment.apps/}" "kubectl rollout status $d -n $NS --timeout=5s"
  done
} > "$OUT"

echo "wrote $OUT  - review it for anything sensitive, then run: make ingest"
