#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Every file this script installs. All are committed to the repository.
PROMETHEUS_VALUES="${ROOT_DIR}/monitoring/kube-prometheus-stack-values.yaml"
LOKI_VALUES="${ROOT_DIR}/monitoring/loki-values.yaml"
PROMTAIL_VALUES="${ROOT_DIR}/monitoring/promtail-values.yaml"
DASHBOARD="${ROOT_DIR}/monitoring/dashboard-configmap.yaml"

command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 1; }
command -v helm >/dev/null || { echo "helm is required" >&2; exit 1; }

missing=0
for file in "${PROMETHEUS_VALUES}" "${LOKI_VALUES}" "${PROMTAIL_VALUES}" "${DASHBOARD}"; do
  [[ -f "${file}" ]] || { echo "Missing required file: ${file#"${ROOT_DIR}"/}" >&2; missing=1; }
done
(( missing == 0 )) || exit 1

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Prometheus, Grafana (with Loki datasource + dashboard sidecar), Alertmanager,
# kube-state-metrics, node-exporter, and the kubelet/cAdvisor scrape that
# provides pod CPU and memory metrics.
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values "${PROMETHEUS_VALUES}" \
  --wait --timeout 10m

# Log storage (single-binary, development configuration).
helm upgrade --install loki grafana/loki \
  --namespace monitoring \
  --values "${LOKI_VALUES}" \
  --wait --timeout 10m

# Log collector DaemonSet that ships every pod's logs to Loki.
helm upgrade --install promtail grafana/promtail \
  --namespace monitoring \
  --values "${PROMTAIL_VALUES}" \
  --wait --timeout 10m

# Grafana dashboard: request rate, status codes, p95 latency, pod CPU,
# pod memory, and Loki pod logs. Picked up by the Grafana dashboard sidecar.
kubectl apply -f "${DASHBOARD}"

echo "Monitoring stack installed successfully."
