import pytest


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    import app.main as api

    token = "test-only-documents-token-0123456789"
    monkeypatch.setenv("DOCUMENTS_API_TOKEN", token)
    # State stores attributes in a mapping; pytest 9.2 restores that mapping correctly.
    monkeypatch.setitem(api.app.state._state, "api_token", token)
    return token
