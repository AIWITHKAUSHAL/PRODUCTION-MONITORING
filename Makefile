.PHONY: test validate run build install-monitoring deploy port-forward-app port-forward-grafana traffic

test:
	pytest -q

validate:
	bash -n scripts/*.sh
	pytest -q tests/test_manifests.py

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

build:
	docker build -t python-monitor:1.0.0 .

install-monitoring:
	./scripts/install-monitoring.sh

deploy:
	./scripts/deploy.sh

port-forward-app:
	kubectl port-forward -n production-monitoring svc/python-monitor 8000:8000

port-forward-grafana:
	kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80

traffic:
	./scripts/generate-traffic.sh
