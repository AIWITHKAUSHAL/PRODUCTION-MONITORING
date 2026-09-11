#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl apply -f "${ROOT_DIR}/k8s/app.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/monitoring/service-monitor.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/monitoring/alerts.yaml"
kubectl rollout status deployment/python-monitor -n production-monitoring --timeout=180s

echo "Application deployed successfully."
