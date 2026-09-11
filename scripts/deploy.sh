#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Every file this script applies. All are committed to the repository.
APP_MANIFEST="${ROOT_DIR}/k8s/app.yaml"
SERVICE_MONITOR="${ROOT_DIR}/k8s/monitoring/service-monitor.yaml"
ALERTS="${ROOT_DIR}/k8s/monitoring/alerts.yaml"

command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 1; }

missing=0
for file in "${APP_MANIFEST}" "${SERVICE_MONITOR}" "${ALERTS}"; do
  [[ -f "${file}" ]] || { echo "Missing required file: ${file#"${ROOT_DIR}"/}" >&2; missing=1; }
done
(( missing == 0 )) || exit 1

# ServiceMonitor and PrometheusRule are Prometheus Operator CRDs.
if ! kubectl get crd servicemonitors.monitoring.coreos.com prometheusrules.monitoring.coreos.com >/dev/null 2>&1; then
  echo "Prometheus Operator CRDs not found. Run 'make install-monitoring' first." >&2
  exit 1
fi

# Namespace, Deployment (2 replicas, probes, resource limits), and Service.
kubectl apply -f "${APP_MANIFEST}"
# Tells Prometheus to scrape /metrics on the Service every 15 seconds.
kubectl apply -f "${SERVICE_MONITOR}"
# Alerts: high 5xx error rate, no available replicas, memory near limit.
kubectl apply -f "${ALERTS}"
kubectl rollout status deployment/python-monitor -n production-monitoring --timeout=180s

echo "Application deployed successfully."
