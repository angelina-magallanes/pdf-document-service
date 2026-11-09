import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import app.main as api

pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch, api_token):
    mongo = MongoClient(
        os.getenv("MONGODB_TEST_URI", "mongodb://127.0.0.1:27017"),
        serverSelectionTimeoutMS=5000,
    )
    database_name = f"pdf_test_{uuid4().hex}"
    collection = mongo[database_name]["documents"]

    try:
        mongo.admin.command("ping")
        # La aplicación crea el índice real durante su ciclo de arranque.
        app_mongo = MongoClient(
            os.getenv("MONGODB_TEST_URI", "mongodb://127.0.0.1:27017"),
            serverSelectionTimeoutMS=5000,
        )
        monkeypatch.setattr(api, "client", app_mongo)
        monkeypatch.setattr(api, "documents", collection)
        with TestClient(api.app, headers={"Authorization": f"Bearer {api_token}"}) as http_client:
            yield http_client
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


def test_guardados_simultaneos_no_duplican(client):
    payload = {"checksum": "a" * 64, "content": "# Concurrente", "page_count": 1}
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.post("/documents", json=payload), range(16)))

    assert sorted(response.status_code for response in responses) == [200] * 15 + [201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert len(client.get("/documents").json()) == 1


def test_checksum_normalizado_conserva_original(client):
    payload = {"checksum": "B" * 64, "content": "# Original", "page_count": 2}
    original = client.post("/documents", json=payload)
    repeated = client.post("/documents", json={**payload, "content": "Otro texto", "page_count": 9})
    found = client.get(f"/documents/by-checksum/{payload['checksum']}")

    assert original.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json() == original.json() == found.json()
    assert found.json()["checksum"] == "b" * 64
    assert found.json()["filename"] == "document.pdf"


def test_checksum_inexistente_y_paginacion(client):
    assert client.get(f"/documents/by-checksum/{'c' * 64}").status_code == 404
    identifiers = []
    for checksum in ["a", "b", "c"]:
        created = client.post("/documents", json={
            "checksum": checksum * 64, "content": "# Test", "page_count": 1,
        })
        identifiers.append(created.json()["id"])
    page = client.get("/documents?skip=1&limit=1").json()
    assert [document["id"] for document in page] == identifiers[1:2]


def test_documento_supera_limite_bson_sin_afectar_mongodb(client):
    response = client.post("/documents", json={
        "checksum": "e" * 64, "content": "x" * (16 * 1024 * 1024), "page_count": 1,
    })
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert client.get("/health/ready").status_code == 200
    assert client.get("/documents").json() == []
