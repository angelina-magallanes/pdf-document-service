import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DocumentTooLarge, DuplicateKeyError, ServerSelectionTimeoutError, WriteError

import app.main as api


@pytest.fixture
def storage(monkeypatch):
    collection = MagicMock()
    mongo = MagicMock()
    monkeypatch.setattr(api, "documents", collection)
    monkeypatch.setattr(api, "client", mongo)
    return collection, mongo


@pytest.fixture
def client(storage, api_token):
    # El ciclo de arranque se prueba aparte; estas pruebas no necesitan MongoDB.
    http = TestClient(api.app, headers={"Authorization": f"Bearer {api_token}"})
    yield http
    http.close()


@pytest.fixture
def payload():
    return {"checksum": "a" * 64, "content": "# Markdown", "page_count": 2}


def test_health_identifica_servicio(client, storage):
    _, mongo = storage
    for path in ["/health", "/health/ready"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "documents", "db": "connected"}
    assert mongo.admin.command.call_count == 2


def test_liveness_no_depende_de_mongo(client, storage):
    _, mongo = storage
    mongo.admin.command.side_effect = ServerSelectionTimeoutError("internal-db-host")
    assert client.get("/health/live").json() == {"status": "ok", "service": "documents"}
    mongo.admin.command.assert_not_called()


@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_readiness_fallida_controlada(client, storage, path):
    _, mongo = storage
    mongo.admin.command.side_effect = ServerSelectionTimeoutError("mongodb://user:secret@internal")
    response = client.get(path, headers={"X-Request-ID": "ready-123"})
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "1"
    assert response.json()["request_id"] == response.headers["x-request-id"] == "ready-123"
    assert "secret" not in response.text
    assert response.json()["detail"] == "Base de datos no disponible"


@pytest.mark.parametrize("method,path,body,operation", [
    ("post", "/documents", "create", "insert_one"),
    ("get", "/documents/by-checksum/" + "a" * 64, None, "find_one"),
    ("get", "/documents/507f1f77bcf86cd799439011", None, "find_one"),
    ("get", "/documents", None, "find"),
    ("patch", "/documents/507f1f77bcf86cd799439011", "rename", "find_one_and_update"),
    ("delete", "/documents/507f1f77bcf86cd799439011", None, "delete_one"),
])
def test_operaciones_con_mongodb_caido(client, storage, payload, method, path, body, operation):
    collection, _ = storage
    getattr(collection, operation).side_effect = ServerSelectionTimeoutError("private-host")
    kwargs = {}
    if body:
        kwargs["json"] = payload if body == "create" else {"filename": "renamed.pdf"}
    response = client.request(method, path, **kwargs)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert "private-host" not in response.text


def test_error_al_consumir_cursor(client, storage):
    collection, _ = storage
    cursor = collection.find.return_value.sort.return_value.skip.return_value.limit.return_value
    cursor.__iter__.side_effect = ServerSelectionTimeoutError("cursor-host")
    assert client.get("/documents").status_code == 503


@pytest.mark.parametrize("error", [DocumentTooLarge("internal-message"), WriteError("internal-message", code=10334)])
def test_documento_demasiado_grande_no_se_presenta_como_caida_de_mongo(client, storage, payload, error):
    collection, _ = storage
    collection.insert_one.side_effect = error
    response = client.post("/documents", json=payload)
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert "retry-after" not in response.headers
    assert "internal-message" not in response.text


@pytest.mark.parametrize("value", ["bad checksum", "z" * 64, "a" * 63])
def test_checksum_invalido_no_consulta_mongo(client, storage, value):
    collection, _ = storage
    response = client.get(f"/documents/by-checksum/{value}")
    assert response.status_code == 422
    assert response.json()["status"] == 422
    collection.find_one.assert_not_called()


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_id_invalido_no_consulta_mongo(client, storage, method):
    collection, _ = storage
    kwargs = {"json": {"filename": "test.pdf"}} if method == "patch" else {}
    response = client.request(method, "/documents/not-an-id", **kwargs)
    assert response.status_code == 422
    assert collection.mock_calls == []


@pytest.mark.parametrize("query", ["skip=-1", "limit=0", "limit=101", "limit=bad"])
def test_paginacion_invalida(client, storage, query):
    collection, _ = storage
    assert client.get("/documents?" + query).status_code == 422
    collection.find.assert_not_called()


def test_error_de_validacion_no_expone_cuerpo(client, payload):
    response = client.post("/documents", json={**payload, "page_count": {"secret": "private-content"}})
    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["body", "page_count"]
    assert "private-content" not in response.text


def test_error_de_validador_es_serializable(client, payload):
    response = client.post("/documents", json={**payload, "filename": "   "})
    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "value_error"


def test_correlacion_en_respuestas_y_logs(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get("/health/live", headers={
            "X-Request-ID": "request-123", "X-Audit-Id": "audit-456",
        })
    assert response.headers["x-request-id"] == "request-123"
    assert response.headers["x-audit-id"] == "audit-456"
    assert "request_id=request-123 audit_id=audit-456" in caplog.text


@pytest.mark.parametrize("headers", [{}, {"X-Request-ID": "x" * 129}, {"X-Request-ID": "bad id"}])
def test_genera_identificador_si_falta_o_es_invalido(client, headers):
    response = client.get("/health/live", headers=headers)
    assert len(response.headers["x-request-id"]) == 32


def test_error_http_conserva_correlacion(client):
    response = client.get("/missing", headers={"X-Request-ID": "missing-123", "X-Audit-Id": "audit-123"})
    assert response.status_code == 404
    assert response.json()["request_id"] == "missing-123"
    assert response.headers["x-audit-id"] == "audit-123"


def test_colision_con_eliminacion_concurrente_devuelve_409(client, storage, payload):
    collection, _ = storage
    collection.insert_one.side_effect = DuplicateKeyError("duplicate-key")
    collection.find_one.return_value = None
    response = client.post("/documents", json=payload)
    assert response.status_code == 409
    assert response.json()["status"] == 409


def test_error_mongo_durante_recuperacion_de_duplicado(client, storage, payload):
    collection, _ = storage
    collection.insert_one.side_effect = DuplicateKeyError("duplicate-key")
    collection.find_one.side_effect = ServerSelectionTimeoutError("private-host")
    response = client.post("/documents", json=payload)
    assert response.status_code == 503


@pytest.mark.parametrize("filename", [None, "informe.pdf"])
def test_documento_existente_compatible_y_sin_mutacion(client, storage, payload, filename):
    collection, _ = storage
    document = {**payload, "_id": ObjectId(), "created_at": datetime.now(timezone.utc), "filename": filename}
    collection.find_one.return_value = document
    response = client.get("/documents/by-checksum/" + "a" * 64)
    assert response.status_code == 200
    assert response.json()["filename"] == (filename or "document.pdf")
    assert isinstance(response.json()["id"], str)
    assert response.json()["content"] == payload["content"]
    assert response.json()["page_count"] == payload["page_count"]
    assert "_id" not in response.json()
    assert "_id" in document


def test_ciclo_de_vida_crea_indice_y_cierra_cliente(storage):
    collection, mongo = storage
    with TestClient(api.app):
        collection.create_index.assert_called_once_with("checksum", unique=True, name="uq_documents_checksum")
        mongo.admin.command.assert_called_once_with("ping")
        mongo.close.assert_not_called()
    mongo.close.assert_called_once()


def test_arranque_fallido_cierra_cliente(storage):
    _, mongo = storage
    mongo.admin.command.side_effect = ServerSelectionTimeoutError("unavailable")
    with pytest.raises(ServerSelectionTimeoutError):
        with TestClient(api.app):
            pass
    mongo.close.assert_called_once()


def test_openapi_documenta_duplicados_y_errores(client):
    spec = client.get("/openapi.json").json()
    post = spec["paths"]["/documents"]["post"]["responses"]
    assert {"200", "201", "409", "422", "503"} <= post.keys()
    assert set(post["422"]["content"]) == {"application/problem+json"}
    assert set(post["503"]["content"]) == {"application/problem+json"}
    assert "/documents/by-checksum/{checksum}" in spec["paths"]


def test_saturacion_rechaza_sin_consultar_mongo_y_mantiene_liveness(client, storage, monkeypatch):
    from threading import BoundedSemaphore

    limiter = BoundedSemaphore(1)
    assert limiter.acquire(blocking=False)
    monkeypatch.setattr(api, "admission", limiter)
    collection, mongo = storage
    response = client.get("/documents", headers={"X-Request-ID": "saturated"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json()["request_id"] == "saturated"
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    collection.find.assert_not_called()
    mongo.admin.command.assert_not_called()
    limiter.release()
    assert client.get("/health/ready").status_code == 200


def test_admision_se_libera_si_mongo_falla(client, storage, monkeypatch):
    from threading import BoundedSemaphore

    monkeypatch.setattr(api, "admission", BoundedSemaphore(1))
    collection, _ = storage
    collection.find_one.side_effect = ServerSelectionTimeoutError("unavailable")
    assert client.get("/documents/507f1f77bcf86cd799439011").status_code == 503
    assert client.get("/health/ready").status_code == 200


def test_otra_peticion_falla_rapido_mientras_una_operacion_ocupa_el_cupo(client, storage, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import BoundedSemaphore, Event

    entered, finish = Event(), Event()
    collection, _ = storage
    document = {"_id": ObjectId(), "checksum": "a" * 64, "content": "# x", "page_count": 1,
                "filename": "x.pdf", "created_at": datetime.now(timezone.utc)}

    def slow_read(*args, **kwargs):
        entered.set()
        assert finish.wait(5)
        return document

    monkeypatch.setattr(api, "admission", BoundedSemaphore(1))
    collection.find_one.side_effect = slow_read
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.get, "/documents/507f1f77bcf86cd799439011")
        try:
            assert entered.wait(5)
            second = client.get("/documents/507f1f77bcf86cd799439011")
            assert second.status_code == 503
            assert second.headers["retry-after"] == "1"
        finally:
            finish.set()
        assert first.result(timeout=5).status_code == 200
    assert client.get("/health/ready").status_code == 200
