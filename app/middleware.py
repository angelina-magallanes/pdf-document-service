import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app import dependencies, metrics
from app.auth import PUBLIC_PATHS, authorized
from app.errors import problem_response

logger = logging.getLogger(__name__)
TRACE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def needs_admission(path: str) -> bool:
    return path == "/documents" or path.startswith("/documents/") or path in ("/health", "/health/ready")


class AdmissionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not needs_admission(scope["path"]):
            return await self.app(scope, receive, send)
        if not dependencies.admission.acquire(blocking=False):
            metrics.rejected.inc()
            response = problem_response(Request(scope), 503, "Servicio de documentos saturado",
                                        headers={"Retry-After": "1"})
            return await response(scope, receive, send)
        metrics.in_flight.inc()
        try:
            await self.app(scope, receive, send)
        finally:
            metrics.in_flight.dec()
            dependencies.admission.release()


def set_correlation(request):
    request_id = request.headers.get("X-Request-ID", "")
    audit_id = request.headers.get("X-Audit-Id", "")
    request.state.request_id = request_id if TRACE_ID.fullmatch(request_id) else uuid4().hex
    request.state.audit_id = audit_id if TRACE_ID.fullmatch(audit_id) else None


async def authenticated_request(request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    if not request.app.state.api_token:
        return problem_response(request, 503, "Servicio no configurado")
    if not authorized(request.headers, request.app.state.api_token):
        return problem_response(request, 401, "Credenciales inválidas o ausentes",
                                headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


def response_correlation(request, response):
    response.headers["X-Request-ID"] = request.state.request_id
    if request.state.audit_id:
        response.headers["X-Audit-Id"] = request.state.audit_id


def log_request(request, result):
    status, elapsed = result
    logger.info(
        "method=%s path=%s status=%s duration_ms=%.1f request_id=%s audit_id=%s",
        request.method, request.url.path, status, elapsed * 1000,
        request.state.request_id, request.state.audit_id or "-",
    )


async def trace_request(request: Request, call_next):
    set_correlation(request)
    start, status = perf_counter(), 500
    try:
        response = await authenticated_request(request, call_next)
        status = response.status_code
        response_correlation(request, response)
        return response
    finally:
        result = (status, perf_counter() - start)
        log_request(request, result)
        metrics.observe(request, result)
