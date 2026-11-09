from dataclasses import asdict

from fastapi import APIRouter, Depends, Path, Query, Response

from app import dependencies, metrics
from app.auth import bearer_scheme
from app.domain import Document
from app.errors import problem_spec
from app.schemas import DocumentCreate, DocumentResponse, DocumentUpdate

router = APIRouter()


@router.get("/health/live", tags=["Health"])
def health_live():
    return {"status": "ok", "service": "documents"}


@router.get("/health", tags=["Health"])
@router.get("/health/ready", tags=["Health"])
def health_ready():
    dependencies.check_database()
    return {"status": "ok", "service": "documents", "db": "connected"}


@router.post(
    "/documents", response_model=DocumentResponse, status_code=201, tags=["Documents"],
    dependencies=[Depends(bearer_scheme)],
    responses={200: {"model": DocumentResponse, "description": "Checksum ya almacenado"},
               413: problem_spec("Documento demasiado grande para MongoDB"),
               409: problem_spec("Conflicto concurrente; volver a consultar por checksum")},
)
def create_document(payload: DocumentCreate, response: Response):
    document = Document.new(payload.checksum, payload.content, payload.page_count, payload.filename)
    result, created = dependencies.get_service().create(document)
    if not created:
        response.status_code = 200
    return asdict(result)


@router.get("/documents/by-checksum/{checksum}", response_model=DocumentResponse,
         dependencies=[Depends(bearer_scheme)],
         tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def get_document_by_checksum(checksum: str = Path(pattern=r"^[0-9a-fA-F]{64}$")):
    return asdict(dependencies.get_service().get_by_checksum(checksum))


@router.get("/documents/{document_id}", response_model=DocumentResponse,
         dependencies=[Depends(bearer_scheme)],
         tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def get_document_by_id(document_id: str):
    return asdict(dependencies.get_service().get_by_id(document_id))


@router.get("/documents", response_model=list[DocumentResponse], tags=["Documents"], dependencies=[Depends(bearer_scheme)],
            responses={413: problem_spec("Página demasiado grande; reducir limit")})
def list_documents(skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    return [asdict(document) for document in dependencies.get_service().list(skip, limit)]


@router.patch("/documents/{document_id}", response_model=DocumentResponse,
           dependencies=[Depends(bearer_scheme)],
           tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def update_document(document_id: str, payload: DocumentUpdate):
    return asdict(dependencies.get_service().rename(document_id, payload.filename))


@router.delete("/documents/{document_id}", status_code=204,
            dependencies=[Depends(bearer_scheme)],
            tags=["Documents"], responses={404: problem_spec("Documento no encontrado")})
def delete_document(document_id: str):
    dependencies.get_service().delete(document_id)
    return Response(status_code=204)


@router.get("/metrics", tags=["Monitoring"], dependencies=[Depends(bearer_scheme)])
def get_metrics():
    return metrics.exposition()
