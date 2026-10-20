from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import app.main as api


@pytest.fixture
def client(monkeypatch):
    mongo = MongoClient(
        "mongodb://127.0.0.1:27017",
        serverSelectionTimeoutMS=5000,
    )
    database_name = f"pdf_test_{uuid4().hex}"
    collection = mongo[database_name]["documents"]

    try:
        mongo.admin.command("ping")
        collection.create_index("checksum", unique=True)

        # Los endpoints usarán la colección de pruebas.
        monkeypatch.setattr(api, "documents", collection)

        # Sin contexto para no ejecutar el lifespan de producción.
        http_client = TestClient(api.app)
        try:
            yield http_client
        finally:
            http_client.close()
    finally:
        mongo.drop_database(database_name)
        mongo.close()


def test_ciclo_completo_documento(client):
    payload = {
        "checksum": "d" * 64,
        "content": "# Documento de prueba",
        "page_count": 1,
        "filename": "original.pdf",
    }

    # Crear.
    created = client.post("/documents", json=payload)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    # Repetir el guardado no crea otro documento.
    duplicate = client.post("/documents", json=payload)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["id"] == document_id

    # Buscar por checksum.
    found = client.get(
        f"/documents/by-checksum/{payload['checksum']}"
    )
    assert found.status_code == 200
    assert found.json()["id"] == document_id

    # Buscar por identificador.
    found = client.get(f"/documents/{document_id}")
    assert found.status_code == 200
    assert found.json()["content"] == payload["content"]

    # Listar: debe existir un solo documento.
    listed = client.get("/documents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Cambiar el nombre conservando el contenido.
    updated = client.patch(
        f"/documents/{document_id}",
        json={"filename": "renombrado.pdf"},
    )
    assert updated.status_code == 200
    assert updated.json()["filename"] == "renombrado.pdf"
    assert updated.json()["content"] == payload["content"]

    persisted = client.get(f"/documents/{document_id}")
    assert persisted.json()["filename"] == "renombrado.pdf"

    # Eliminar y comprobar que ya no existe.
    deleted = client.delete(f"/documents/{document_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    assert client.get(
        f"/documents/{document_id}"
    ).status_code == 404

    assert client.delete(
        f"/documents/{document_id}"
    ).status_code == 404