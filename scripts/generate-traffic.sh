#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8000}"

echo "Generating traffic against ${APP_URL}. Press Ctrl+C to stop."
while true; do
  curl --silent --output /dev/null "${APP_URL}/"
  curl --silent --output /dev/null "${APP_URL}/work"
  sleep 0.5
done
