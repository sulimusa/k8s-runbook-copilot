#!/usr/bin/env bash
# Promote EXACTLY the image currently running in dev to prod (no rebuild).
#   bash deploy/scripts/promote.sh        (or: make promote)     YES=1 skips the confirmation prompt
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

CLUSTER="${CLUSTER:-runbook-lab}"
CTX="kind-${CLUSTER}"
CHART=deploy/helm/runbook-copilot

IMG="$(kubectl --context "$CTX" -n dev get deploy -l app.kubernetes.io/instance=copilot \
  -o jsonpath='{.items[0].spec.template.spec.containers[0].image}')"
[ -n "$IMG" ] || { echo "nothing deployed in dev"; exit 1; }
REPO="${IMG%:*}"; TAG="${IMG##*:}"

echo "dev runs: $IMG"
if [ "${YES:-}" != "1" ]; then
  read -r -p "Promote ${IMG} to prod? [y/N] " ans
  [ "$ans" = "y" ] || { echo "aborted"; exit 1; }
fi

helm --kube-context "$CTX" upgrade --install copilot "$CHART" -n prod -f "$CHART/values-prod.yaml" \
  --set image.repository="$REPO" --set image.tag="$TAG" --set image.pullPolicy=Never --wait --timeout 3m
echo "prod now runs ${IMG}. Roll back with: make rollback"
