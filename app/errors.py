import logging
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.documents import Problem
from app.models.errors import (DocumentNotFound, InvalidDocumentId, DocumentTooLarge,
                        PersistenceUnavailable, PageTooLarge)

logger = logging.getLogger(__name__)


def problem_spec(description: str):
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": Problem.model_json_schema()}},
    }


def problem_response(request: Request, status: int, detail: str, *, headers=None, errors=None):
    body = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": request.state.request_id,
    }
    if errors is not None:
        body["errors"] = errors
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request.state.request_id
    if request.state.audit_id:
        response_headers["X-Audit-Id"] = request.state.audit_id
    return JSONResponse(
        body, status_code=status, headers=response_headers,
        media_type="application/problem+json",
    )


async def http_error(request: Request, exc: HTTPException):
    return problem_response(request, exc.status_code, str(exc.detail), headers=exc.headers)


async def validation_error(request: Request, exc: RequestValidationError):
    # Avoid echoing document content or validator context in error responses.
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return problem_response(request, 422, "Solicitud inválida", errors=errors)


async def database_error(request: Request, exc: PersistenceUnavailable):
    logger.warning("MongoDB no disponible request_id=%s", request.state.request_id)
    return problem_response(
        request, 503, "Base de datos no disponible", headers={"Retry-After": "1"},
    )


async def document_too_large(request: Request, exc: DocumentTooLarge):
    return problem_response(request, 413, "El documento excede el tamaño permitido por MongoDB")


async def domain_error(request: Request, exc: Exception):
    if isinstance(exc, DocumentNotFound):
        return problem_response(request, 404, "Documento no encontrado")
    if isinstance(exc, InvalidDocumentId):
        return problem_response(request, 422, "El ID debe tener 24 caracteres hexadecimales")
    return problem_response(request, 409, "Conflicto al guardar el documento; reintentá")


async def page_too_large(request: Request, exc: PageTooLarge):
    return problem_response(request, 413, "La página excede el límite; reducir limit o consultar por ID")
