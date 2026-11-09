import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as api
from app import dependencies


@pytest.fixture
def storage(monkeypatch):
    collection, mongo = MagicMock(), MagicMock()
    monkeypatch.setattr(dependencies, "documents", collection)
    monkeypatch.setattr(dependencies, "client", mongo)
    return collection, mongo


@pytest.mark.parametrize("method,path", [
    ("POST", "/documents"), ("GET", "/documents"),
    ("GET", "/documents/by-checksum/" + "a" * 64),
    ("GET", "/documents/507f1f77bcf86cd799439011"),
    ("PATCH", "/documents/507f1f77bcf86cd799439011"),
    ("DELETE", "/documents/507f1f77bcf86cd799439011"),
    ("GET", "/documents/"),
])
@pytest.mark.parametrize("authorization", [None, "", "Basic abc", "Bearer incorrecto", "Bearer", "Bearer a b"])
def test_rechaza_credenciales_antes_de_validar_o_consultar_mongo(storage, method, path, authorization):
    headers = {"X-Request-ID": "auth-123", "X-Audit-Id": "audit-123"}
    if authorization is not None:
        headers["Authorization"] = authorization
    with TestClient(api.app) as client:
        for mock in storage:
            mock.reset_mock()
        response = client.request(method, path, headers=headers, content=b"{JSON invalido")
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["detail"] == "Credenciales inválidas o ausentes"
        assert response.json()["request_id"] == "auth-123"
        assert response.headers["X-Audit-Id"] == "audit-123"
        assert all(not mock.mock_calls for mock in storage)


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_token_valido_permite_acceso(storage, api_token, scheme):
    collection, _ = storage
    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = []
    with TestClient(api.app) as client:
        response = client.get("/documents", headers={"Authorization": f"{scheme} {api_token}"})
    assert response.status_code == 200
    assert response.json() == []


def test_token_es_sensible_a_mayusculas_y_no_se_registra(storage, api_token, caplog):
    with TestClient(api.app) as client, caplog.at_level(logging.INFO):
        response = client.get("/documents", headers={"Authorization": f"Bearer {api_token.upper()}"})
    assert response.status_code == 401
    assert api_token not in response.text + caplog.text
    assert api_token.upper() not in response.text + caplog.text


def test_rechaza_dos_cabeceras_authorization(storage, api_token):
    with TestClient(api.app) as client:
        response = client.get("/documents", headers=[
            ("Authorization", f"Bearer {api_token}"),
            ("Authorization", "Bearer otro"),
        ])
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/health", "/health/live", "/health/ready", "/docs", "/redoc", "/openapi.json"])
def test_sondas_y_documentacion_no_exigen_token(storage, path):
    with TestClient(api.app) as client:
        assert client.get(path).status_code == 200


def test_openapi_declara_bearer_en_todas_las_operaciones_de_documentos(storage):
    with TestClient(api.app) as client:
        spec = client.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["DocumentsBearer"]["scheme"] == "bearer"
    for path, operations in spec["paths"].items():
        for operation in operations.values():
            if path.startswith("/documents"):
                assert operation["security"] == [{"DocumentsBearer": []}]
                assert "401" in operation["responses"]
            else:
                assert not operation.get("security")


@pytest.mark.parametrize("token", [None, "", "corto", "x" * 31, " " + "x" * 32, "x" * 513])
def test_sin_secreto_valido_no_arranca_ni_contacta_mongo(monkeypatch, storage, token):
    if token is None:
        monkeypatch.delenv("DOCUMENTS_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DOCUMENTS_API_TOKEN", token)
    with pytest.raises(ValueError, match="DOCUMENTS_API_TOKEN"):
        with TestClient(api.app):
            pass
    collection, mongo = storage
    collection.create_index.assert_not_called()
    mongo.admin.command.assert_not_called()
    mongo.close.assert_called_once()
    assert api.app.state.api_token is None


def test_auth_se_comprueba_antes_del_limite_de_concurrencia(storage, monkeypatch):
    from threading import BoundedSemaphore

    limiter = BoundedSemaphore(1)
    limiter.acquire()
    monkeypatch.setattr(dependencies, "admission", limiter)
    with TestClient(api.app) as client:
        assert client.get("/documents").status_code == 401
        assert client.get("/health/live").status_code == 200
    limiter.release()


def test_sin_configuracion_nunca_se_permite_acceso(monkeypatch, storage):
    with TestClient(api.app) as client:
        monkeypatch.setattr(api.app.state, "api_token", None)
        assert client.get("/documents").status_code == 503
