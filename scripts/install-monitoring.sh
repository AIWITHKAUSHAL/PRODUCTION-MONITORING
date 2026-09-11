#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v kubectl >/dev/null || { echo "kubectl is required"; exit 1; }
command -v helm >/dev/null || { echo "helm is required"; exit 1; }

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values "${ROOT_DIR}/monitoring/kube-prometheus-stack-values.yaml" \
  --wait --timeout 10m

helm upgrade --install loki grafana/loki \
  --namespace monitoring \
  --values "${ROOT_DIR}/monitoring/loki-values.yaml" \
  --wait --timeout 10m

helm upgrade --install promtail grafana/promtail \
  --namespace monitoring \
  --values "${ROOT_DIR}/monitoring/promtail-values.yaml" \
  --wait --timeout 10m

kubectl apply -f "${ROOT_DIR}/monitoring/dashboard-configmap.yaml"

echo "Monitoring stack installed successfully."
