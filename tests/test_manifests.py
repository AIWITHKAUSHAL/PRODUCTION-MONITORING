"""Static checks for the Kubernetes and monitoring manifests.

These run without a cluster. They confirm that every file the helper scripts
reference is committed, and that the Service, ServiceMonitor, alerts, and
Grafana dashboard agree with each other and with the metrics the app exposes.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ["scripts/install-monitoring.sh", "scripts/deploy.sh"]


def load_docs(relative_path: str) -> list[dict]:
    with open(ROOT / relative_path) as handle:
        return [doc for doc in yaml.safe_load_all(handle) if doc]


def find(docs: list[dict], kind: str) -> dict:
    matches = [doc for doc in docs if doc["kind"] == kind]
    assert len(matches) == 1, f"expected one {kind}, found {len(matches)}"
    return matches[0]


def referenced_files(script: str) -> list[str]:
    text = (ROOT / script).read_text()
    return re.findall(r"\$\{ROOT_DIR\}/([\w./-]+\.yaml)", text)


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_only_reference_committed_files(script):
    files = referenced_files(script)
    assert files, f"{script} references no manifests"
    for relative_path in files:
        assert (ROOT / relative_path).is_file(), f"{script} references missing {relative_path}"


@pytest.fixture(scope="module")
def app_docs():
    return load_docs("k8s/app.yaml")


@pytest.fixture(scope="module")
def dashboard():
    configmap = find(load_docs("monitoring/dashboard-configmap.yaml"), "ConfigMap")
    return configmap, json.loads(configmap["data"]["python-monitor.json"])


@pytest.fixture(scope="module")
def alert_rules():
    rule = find(load_docs("k8s/monitoring/alerts.yaml"), "PrometheusRule")
    return rule, [r for group in rule["spec"]["groups"] for r in group["rules"]]


@pytest.fixture(scope="module")
def stack_values():
    return load_docs("monitoring/kube-prometheus-stack-values.yaml")[0]


@pytest.fixture(scope="module")
def exposed_metrics() -> str:
    client = TestClient(app)
    client.get("/")
    return client.get("/metrics").text


def test_deployment_has_probes_and_resources(app_docs):
    container = find(app_docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["resources"]["limits"]["memory"]
    assert container["resources"]["limits"]["cpu"]


def test_service_monitor_targets_the_app_service(app_docs, stack_values):
    service = find(app_docs, "Service")
    monitor = find(load_docs("k8s/monitoring/service-monitor.yaml"), "ServiceMonitor")

    assert monitor["metadata"]["namespace"] == service["metadata"]["namespace"]
    assert monitor["spec"]["selector"]["matchLabels"].items() <= service["metadata"]["labels"].items()

    endpoint = monitor["spec"]["endpoints"][0]
    assert endpoint["path"] == "/metrics"
    assert endpoint["port"] in {port["name"] for port in service["spec"]["ports"]}
    # Prometheus must be allowed to pick up ServiceMonitors from any release.
    assert stack_values["prometheus"]["prometheusSpec"]["serviceMonitorSelectorNilUsesHelmValues"] is False


def test_alert_rules_cover_errors_availability_and_memory(alert_rules, stack_values):
    _, rules = alert_rules
    assert {rule["alert"] for rule in rules} == {
        "PythonMonitorHighErrorRate",
        "PythonMonitorPodUnavailable",
        "PythonMonitorHighMemory",
    }
    for rule in rules:
        assert rule["expr"] and rule["for"] and rule["labels"]["severity"]
    assert stack_values["prometheus"]["prometheusSpec"]["ruleSelectorNilUsesHelmValues"] is False


def test_dashboard_is_discovered_by_grafana_sidecar(dashboard, stack_values):
    configmap, _ = dashboard
    sidecar_label = stack_values["grafana"]["sidecar"]["dashboards"]["label"]
    assert configmap["metadata"]["labels"][sidecar_label] == "1"


def test_dashboard_has_required_panels(dashboard):
    _, board = dashboard
    queries = {
        panel["title"]: (panel["datasource"]["type"], panel["targets"][0]["expr"])
        for panel in board["panels"]
    }

    assert "app_http_requests_total" in queries["Application Request Rate"][1]
    assert "histogram_quantile" in queries["P95 Request Latency"][1]
    assert "container_cpu_usage_seconds_total" in queries["Pod CPU Usage"][1]
    assert "container_memory_working_set_bytes" in queries["Pod Memory Usage"][1]
    assert queries["Pod Logs"][0] == "loki"


def test_dashboard_loki_datasource_is_provisioned(dashboard, stack_values):
    _, board = dashboard
    loki = next(ds for ds in stack_values["grafana"]["additionalDataSources"] if ds["type"] == "loki")
    log_panel = next(panel for panel in board["panels"] if panel["type"] == "logs")
    assert log_panel["datasource"]["uid"] == loki["uid"]

    promtail = load_docs("monitoring/promtail-values.yaml")[0]
    assert promtail["config"]["clients"][0]["url"].startswith(loki["url"])


def test_dashboard_and_alerts_only_use_exposed_app_metrics(dashboard, alert_rules, exposed_metrics):
    _, board = dashboard
    _, rules = alert_rules
    expressions = [panel["targets"][0]["expr"] for panel in board["panels"]]
    expressions += [rule["expr"] for rule in rules]

    used = {name for expr in expressions for name in re.findall(r"\bapp_\w+", expr)}
    assert used
    for name in used:
        assert name in exposed_metrics, f"{name} is queried but not exposed by /metrics"
