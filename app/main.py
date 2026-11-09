import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from threading import BoundedSemaphore
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pymongo.errors import DocumentTooLarge, PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import PUBLIC_PATHS, authorized, bearer_scheme, load_api_token
from app.database import client, documents, max_inflight
from app.domain import Document, DocumentConflict, DocumentNotFound, InvalidDocumentId
from app.errors import database_error, document_too_large, http_error, problem_response, problem_spec, validation_error
from app.repository import MongoDocumentRepository
from app.schemas import DocumentCreate, DocumentResponse, DocumentUpdate
from app.service import DocumentService

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)
logger = logging.getLogger(__name__)
TRACE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
admission = BoundedSemaphore(max_inflight)


def get_service():
    return DocumentService(MongoDocumentRepository(documents))


def initialize_database():
    client.admin.command("ping")
    MongoDocumentRepository(documents).initialize()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.api_token = load_api_token()
        await run_in_threadpool(initialize_database)
        yield
    finally:
        app.state.api_token = None
        await run_in_threadpool(client.close)


app = FastAPI(
    title="Servicio de persistencia de documentos",
    description="MongoDB, CRUD y deduplicación por SHA-256 del PDF original.",
    version="1.0.0", lifespan=lifespan,
    responses={401: problem_spec("Credenciales inválidas o ausentes"),
               422: problem_spec("Solicitud inválida"), 503: problem_spec("Base de datos no disponible o servicio saturado")},
)
app.state.api_token = None
app.add_exception_handler(StarletteHTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)
app.add_exception_handler(PyMongoError, database_error)
app.add_exception_handler(DocumentTooLarge, document_too_large)


async def domain_error(request: Request, exc: Exception):
    if isinstance(exc, DocumentNotFound):
        return problem_response(request, 404, "Documento no encontrado")
    if isinstance(exc, InvalidDocumentId):
        return problem_response(request, 422, "El ID debe tener 24 caracteres hexadecimales")
    return problem_response(request, 409, "Conflicto al guardar el documento; reintentá")


for exception in (DocumentNotFound, InvalidDocumentId, DocumentConflict):
    app.add_exception_handler(exception, domain_error)


def needs_admission(path: str) -> bool:
    return path == "/documents" or path.startswith("/documents/") or path in ("/health", "/health/ready")


async def admitted_request(request: Request, call_next):
    if not needs_admission(request.url.path):
        return await call_next(request)
    if not admission.acquire(blocking=False):
        return problem_response(request, 503, "Servicio de documentos saturado", headers={"Retry-After": "1"})
    try:
        return await call_next(request)
    finally:
        admission.release()


@app.middleware("http")
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


@app.get("/health/live", tags=["Health"])
def health_live():
    return {"status": "ok", "service": "documents"}


@app.get("/health", tags=["Health"])
@app.get("/health/ready", tags=["Health"])
def health_ready():
    client.admin.command("ping")
    return {"status": "ok", "service": "documents", "db": "connected"}


@app.post(
    "/documents", response_model=DocumentResponse, status_code=201, tags=["Documents"],
    dependencies=[Depends(bearer_scheme)],
    responses={200: {"model": DocumentResponse, "description": "Checksum ya almacenado"},
               413: problem_spec("Documento demasiado grande para MongoDB"),
               409: problem_spec("Conflicto concurrente; volver a consultar por checksum")},
)
def create_document(payload: DocumentCreate, response: Response):
    document = Document.new(payload.checksum, payload.content, payload.page_count, payload.filename)
    result, created = get_service().create(document)
    if not created:
        response.status_code = 200
    return asdict(result)


@app.get("/documents/by-checksum/{checksum}", response_model=DocumentResponse,
         dependencies=[Depends(bearer_scheme)],
         tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def get_document_by_checksum(checksum: str = Path(pattern=r"^[0-9a-fA-F]{64}$")):
    return asdict(get_service().get_by_checksum(checksum))


@app.get("/documents/{document_id}", response_model=DocumentResponse,
         dependencies=[Depends(bearer_scheme)],
         tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def get_document_by_id(document_id: str):
    return asdict(get_service().get_by_id(document_id))


@app.get("/documents", response_model=list[DocumentResponse], tags=["Documents"], dependencies=[Depends(bearer_scheme)])
def list_documents(skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    return [asdict(document) for document in get_service().list(skip, limit)]


@app.patch("/documents/{document_id}", response_model=DocumentResponse,
           dependencies=[Depends(bearer_scheme)],
           tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def update_document(document_id: str, payload: DocumentUpdate):
    return asdict(get_service().rename(document_id, payload.filename))


@app.delete("/documents/{document_id}", status_code=204,
            dependencies=[Depends(bearer_scheme)],
            tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def delete_document(document_id: str):
    get_service().delete(document_id)
    return Response(status_code=204)
