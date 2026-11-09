import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app import dependencies
from app.auth import PUBLIC_PATHS, authorized
from app.errors import problem_response

logger = logging.getLogger(__name__)
TRACE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def needs_admission(path: str) -> bool:
    return path == "/documents" or path.startswith("/documents/") or path in ("/health", "/health/ready")


async def admitted_request(request: Request, call_next):
    if not needs_admission(request.url.path):
        return await call_next(request)
    if not dependencies.admission.acquire(blocking=False):
        return problem_response(request, 503, "Servicio de documentos saturado", headers={"Retry-After": "1"})
    try:
        return await call_next(request)
    finally:
        dependencies.admission.release()


async def trace_request(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    audit_id = request.headers.get("X-Audit-Id", "")
    request.state.request_id = request_id if TRACE_ID.fullmatch(request_id) else uuid4().hex
    request.state.audit_id = audit_id if TRACE_ID.fullmatch(audit_id) else None
    start = perf_counter()
    if request.url.path in PUBLIC_PATHS:
        response = await admitted_request(request, call_next)
    elif not request.app.state.api_token:
        response = problem_response(request, 503, "Servicio no configurado")
    elif not authorized(request.headers, request.app.state.api_token):
        response = problem_response(
            request, 401, "Credenciales inválidas o ausentes",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        response = await admitted_request(request, call_next)
    response.headers["X-Request-ID"] = request.state.request_id
    if request.state.audit_id:
        response.headers["X-Audit-Id"] = request.state.audit_id
    logger.info(
        "method=%s path=%s status=%s duration_ms=%.1f request_id=%s audit_id=%s",
        request.method, request.url.path, response.status_code,
        (perf_counter() - start) * 1000, request.state.request_id,
        request.state.audit_id or "-",
    )
    return response


