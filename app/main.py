from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Path, Response
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.database import client, documents
from app.schemas import DocumentCreate, DocumentResponse
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, Path, Query, Response
from app.schemas import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
)
from pymongo import ReturnDocument


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        client.admin.command("ping")
        documents.create_index(
            "checksum",
            unique=True,
            name="uq_documents_checksum",
        )
        yield
    finally:
        client.close()


app = FastAPI(
    title="Servicio de persistencia de documentos",
    lifespan=lifespan,
)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health")
@app.get("/health/ready")
def health_ready():
    try:
        client.admin.command("ping")
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="MongoDB no disponible",
        ) from None

    return {"status": "ok", "db": "connected"}

@app.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=201,
)
def create_document(
    payload: DocumentCreate,
    response: Response,
):
    document = payload.model_dump()
    document["created_at"] = datetime.now(timezone.utc)

    try:
        result = documents.insert_one(document)
    except DuplicateKeyError:
        try:
            existing = documents.find_one(
                {"checksum": payload.checksum}
            )
        except PyMongoError:
            raise HTTPException(
                status_code=503,
                detail="Base de datos no disponible",
            ) from None

        if existing is None:
            raise HTTPException(
                status_code=409,
                detail="Conflicto al guardar el documento; reintentá",
            )

        response.status_code = 200
        existing["id"] = str(existing.pop("_id"))
        return existing

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None

    document.pop("_id", None)
    document["id"] = str(result.inserted_id)
    return document

@app.get(
    "/documents/by-checksum/{checksum}",
    response_model=DocumentResponse,
)
def get_document_by_checksum(
    checksum: str = Path(pattern=r"^[0-9a-fA-F]{64}$"),
):
    try:
        document = documents.find_one(
            {"checksum": checksum.lower()}
        )
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Documento no encontrado",
        )

    document["id"] = str(document.pop("_id"))
    return document

@app.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_document_by_id(document_id: str):
    try:
        object_id = ObjectId(document_id)
    except InvalidId:
        raise HTTPException(
            status_code=422,
            detail="El ID debe tener 24 caracteres hexadecimales",
        ) from None

    try:
        document = documents.find_one({"_id": object_id})
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Documento no encontrado",
        )

    document["id"] = str(document.pop("_id"))
    return document

@app.get(
    "/documents",
    response_model=list[DocumentResponse],
)
def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        cursor = (
            documents.find()
            .sort("_id", 1)
            .skip(skip)
            .limit(limit)
        )

        results = []

        for document in cursor:
            document["id"] = str(document.pop("_id"))
            results.append(document)

        return results

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None
        
@app.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
)
def update_document(
    document_id: str,
    payload: DocumentUpdate,
):
    try:
        object_id = ObjectId(document_id)
    except InvalidId:
        raise HTTPException(
            status_code=422,
            detail="El ID debe tener 24 caracteres hexadecimales",
        ) from None

    try:
        document = documents.find_one_and_update(
            {"_id": object_id},
            {"$set": {"filename": payload.filename}},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Documento no encontrado",
        )

    document["id"] = str(document.pop("_id"))
    return document

@app.delete(
    "/documents/{document_id}",
    status_code=204,
)
def delete_document(document_id: str):
    try:
        object_id = ObjectId(document_id)
    except InvalidId:
        raise HTTPException(
            status_code=422,
            detail="El ID debe tener 24 caracteres hexadecimales",
        ) from None

    try:
        result = documents.delete_one({"_id": object_id})
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from None

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Documento no encontrado",
        )

    return Response(status_code=204)