from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from fastapi import Response

requests = Counter("documents_http_requests_total", "HTTP responses", ["method", "route", "status"])
duration = Histogram("documents_http_request_duration_seconds", "Time to response headers", ["method", "route"],
                     buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10, 30))
in_flight = Gauge("documents_requests_in_flight", "Requests holding an admission slot")
rejected = Counter("documents_admission_rejections_total", "Requests rejected by the concurrency limit")


def route_label(path):
    if path.startswith("/documents/by-checksum/"):
        return "/documents/by-checksum/{checksum}"
    if path.startswith("/documents/"):
        return "/documents/{id}"
    if path in {"/documents", "/health", "/health/live", "/health/ready", "/metrics"}:
        return path
    return "other"


def observe(request, result):
    status, elapsed = result
    method = request.method if request.method in {"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD", "OPTIONS"} else "OTHER"
    route = route_label(request.url.path)
    requests.labels(method, route, str(status)).inc()
    duration.labels(method, route).observe(elapsed)


def exposition():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
