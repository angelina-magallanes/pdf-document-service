"""Application composition; run with uvicorn app.main:app."""
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pymongo.errors import DocumentTooLarge, PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import dependencies
from app.domain import DocumentConflict, DocumentNotFound, InvalidDocumentId
from app.errors import (database_error, document_too_large, domain_error, http_error,
                        problem_spec, validation_error)
from app.middleware import trace_request
from app.routes import router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)

app = FastAPI(
    title="Servicio de persistencia de documentos",
    description="MongoDB, CRUD y deduplicación por SHA-256 del PDF original.",
    version="1.0.0", lifespan=dependencies.lifespan,
    responses={401: problem_spec("Credenciales inválidas o ausentes"),
               422: problem_spec("Solicitud inválida"), 503: problem_spec("Base de datos no disponible o servicio saturado")},
)
app.state.api_token = None
app.add_exception_handler(StarletteHTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)
app.add_exception_handler(PyMongoError, database_error)
app.add_exception_handler(DocumentTooLarge, document_too_large)


for exception in (DocumentNotFound, InvalidDocumentId, DocumentConflict):
    app.add_exception_handler(exception, domain_error)

app.middleware("http")(trace_request)
app.include_router(router)
