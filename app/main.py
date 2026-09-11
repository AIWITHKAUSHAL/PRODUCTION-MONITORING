import logging
import os
import random
import time

import psutil
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("python-monitor")

app = FastAPI(title="Production Monitoring Demo", version="1.0.0")

REQUESTS = Counter(
    "app_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
IN_PROGRESS = Gauge(
    "app_http_requests_in_progress",
    "HTTP requests currently being served",
)
PROCESS_CPU = Gauge("app_process_cpu_percent", "Application process CPU percent")
PROCESS_MEMORY = Gauge("app_process_memory_bytes", "Application process RSS memory")

process = psutil.Process()


@app.middleware("http")
async def observe_request(request: Request, call_next):
    # Do not record Prometheus scraping itself as application traffic.
    if request.url.path.startswith("/metrics"):
        return await call_next(request)

    start = time.perf_counter()
    IN_PROGRESS.inc()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        REQUESTS.labels(request.method, path, str(status)).inc()
        LATENCY.labels(request.method, path).observe(elapsed)
        IN_PROGRESS.dec()
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            path,
            status,
            elapsed * 1000,
        )


@app.get("/")
def home():
    return {"message": "Production Monitoring Demo", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/work")
def work():
    """Generate a small, safe amount of CPU work for dashboard demonstrations."""
    iterations = random.randint(40_000, 100_000)
    result = sum(number * number for number in range(iterations))
    logger.info("workload completed iterations=%s", iterations)
    return {"status": "completed", "iterations": iterations, "result": result}


@app.get("/error")
def error():
    logger.error("demonstration error requested")
    raise HTTPException(status_code=500, detail="Demonstration error")


def update_process_metrics() -> None:
    PROCESS_CPU.set(process.cpu_percent(interval=None))
    PROCESS_MEMORY.set(process.memory_info().rss)


@app.middleware("http")
async def refresh_process_metrics(request: Request, call_next):
    update_process_metrics()
    return await call_next(request)


@app.get("/metrics", include_in_schema=False)
def metrics():
    update_process_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
