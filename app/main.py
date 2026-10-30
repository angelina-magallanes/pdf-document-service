import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pymongo import ReturnDocument
from pymongo.errors import DocumentTooLarge, DuplicateKeyError, PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import client, documents
from app.errors import (
    database_error, document_too_large, http_error, problem_spec, validation_error,
)
from app.schemas import DocumentCreate, DocumentResponse, DocumentUpdate

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)
logger = logging.getLogger(__name__)
TRACE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def initialize_database():
    client.admin.command("ping")
    documents.create_index("checksum", unique=True, name="uq_documents_checksum")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await run_in_threadpool(initialize_database)
        yield
    finally:
        await run_in_threadpool(client.close)


app = FastAPI(
    title="Servicio de persistencia de documentos",
    description="MongoDB, CRUD y deduplicación por SHA-256 del PDF original.",
    version="1.0.0",
    lifespan=lifespan,
    responses={
        422: problem_spec("Solicitud inválida"),
        503: problem_spec("Base de datos no disponible"),
    },
)
app.add_exception_handler(StarletteHTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)
app.add_exception_handler(PyMongoError, database_error)
app.add_exception_handler(DocumentTooLarge, document_too_large)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    audit_id = request.headers.get("X-Audit-Id", "")
    request.state.request_id = request_id if TRACE_ID.fullmatch(request_id) else uuid4().hex
    request.state.audit_id = audit_id if TRACE_ID.fullmatch(audit_id) else None
    start = perf_counter()
    response = await call_next(request)
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


def document_response(document):
    return {
        **{key: value for key, value in document.items() if key != "_id"},
        "id": str(document["_id"]),
        "filename": document.get("filename") or "document.pdf",
    }


def require_document(document):
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document_response(document)


def parse_id(document_id: str):
    try:
        return ObjectId(document_id)
    except InvalidId:
        raise HTTPException(
            status_code=422, detail="El ID debe tener 24 caracteres hexadecimales",
        ) from None


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
    responses={
        200: {"model": DocumentResponse, "description": "Checksum ya almacenado"},
        413: problem_spec("Documento demasiado grande para MongoDB"),
        409: problem_spec("Conflicto concurrente; volver a consultar por checksum"),
    },
)
def create_document(payload: DocumentCreate, response: Response):
    """Guarda Markdown; un checksum repetido devuelve el original sin modificarlo."""
    document = payload.model_dump()
    document["filename"] = payload.filename or "document.pdf"
    document["created_at"] = datetime.now(timezone.utc)
    try:
        result = documents.insert_one(document)
    except DuplicateKeyError:
        existing = documents.find_one({"checksum": payload.checksum})
        if existing is None:
            raise HTTPException(
                status_code=409, detail="Conflicto al guardar el documento; reintentá",
            ) from None
        response.status_code = 200
        return document_response(existing)
    document["_id"] = result.inserted_id
    return document_response(document)


@app.get(
    "/documents/by-checksum/{checksum}", response_model=DocumentResponse,
    tags=["Documents"], responses={404: problem_spec("Documento no encontrado")},
)
def get_document_by_checksum(checksum: str = Path(pattern=r"^[0-9a-fA-F]{64}$")):
    return require_document(documents.find_one({"checksum": checksum.lower()}))


@app.get(
    "/documents/{document_id}", response_model=DocumentResponse,
    tags=["Documents"], responses={404: problem_spec("Documento no encontrado")},
)
def get_document_by_id(document_id: str):
    return require_document(documents.find_one({"_id": parse_id(document_id)}))


@app.get("/documents", response_model=list[DocumentResponse], tags=["Documents"])
def list_documents(
    skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
):
    cursor = documents.find().sort("_id", 1).skip(skip).limit(limit)
    return [document_response(document) for document in cursor]


@app.patch(
    "/documents/{document_id}", response_model=DocumentResponse,
    tags=["Documents"], responses={404: problem_spec("Documento no encontrado")},
)
def update_document(document_id: str, payload: DocumentUpdate):
    document = documents.find_one_and_update(
        {"_id": parse_id(document_id)}, {"$set": {"filename": payload.filename}},
        return_document=ReturnDocument.AFTER,
    )
    return require_document(document)


@app.delete(
    "/documents/{document_id}", status_code=204,
    tags=["Documents"], responses={404: problem_spec("Documento no encontrado")},
)
def delete_document(document_id: str):
    result = documents.delete_one({"_id": parse_id(document_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return Response(status_code=204)
