import pytest


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    import app.main as api

    token = "test-only-documents-token-0123456789"
    monkeypatch.setenv("DOCUMENTS_API_TOKEN", token)
    monkeypatch.setattr(api.app.state, "api_token", token)
    return token
