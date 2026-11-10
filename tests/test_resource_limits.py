import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app import dependencies, settings
from app.body_limit import LimitedReceive
from app.models.errors import PageTooLarge
from app.main import app
from app.repositories.mongodb import MongoDocumentRepository


@pytest.fixture
def collection(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(dependencies, "documents", collection)
    monkeypatch.setattr(settings, "max_body_bytes", 256)
    return collection


def test_declared_large_body_rejected_before_read_or_database(collection, api_token):
    client = TestClient(app)
    response = client.post('/documents', content=b'{}', headers={
        'Authorization': f'Bearer {api_token}', 'Content-Length': '257',
        'X-Request-ID': 'oversize',
    })
    assert response.status_code == 413
    assert response.json()['request_id'] == 'oversize'
    assert not collection.mock_calls


def test_unauthorized_large_body_still_returns_401(collection):
    response = TestClient(app).post('/documents', content=b'x' * 257)
    assert response.status_code == 401
    assert not collection.mock_calls


@pytest.mark.parametrize('length', ['-1', 'invalid', '1,2'])
def test_malformed_length_is_controlled(collection, api_token, length):
    response = TestClient(app).post('/documents', content=b'{}', headers={
        'Authorization': f'Bearer {api_token}', 'Content-Length': length,
    })
    assert response.status_code == 400
    assert not collection.mock_calls


def test_chunked_request_stops_at_limit_and_releases_admission(collection, api_token):
    consumed = []

    async def chunks():
        for i in range(10):
            consumed.append(i)
            yield b'x' * 128

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/documents', content=chunks(), headers={
                'Authorization': f'Bearer {api_token}', 'Content-Type': 'application/json',
            })
            assert response.status_code == 413
            assert response.headers['content-type'] == 'application/problem+json'
            assert (await client.get('/health/live')).status_code == 200
    asyncio.run(scenario())
    assert consumed == [0, 1, 2]
    assert not collection.mock_calls


def test_limit_counts_bytes_and_accepts_exact_boundary(monkeypatch):
    monkeypatch.setattr(settings, 'max_body_bytes', 4)
    receive = AsyncMock(side_effect=[{'type': 'http.request', 'body': 'éé'.encode()},
                                     {'type': 'http.request', 'body': b'x'}])

    async def scenario():
        limited = LimitedReceive(receive)
        assert (await limited())['body'] == 'éé'.encode()
        with pytest.raises(HTTPException) as error:
            await limited()
        assert error.value.status_code == 413
    asyncio.run(scenario())


def test_stalled_body_has_deadline_without_sleep(monkeypatch):
    from app import body_limit
    monkeypatch.setattr(body_limit, 'monotonic', lambda: 0)

    async def stalled():
        await asyncio.Future()

    async def scenario():
        limited = LimitedReceive(stalled)
        limited.deadline = 0
        with pytest.raises(HTTPException) as error:
            await limited()
        assert error.value.status_code == 408
    asyncio.run(scenario())


def record(content):
    return {'_id': ObjectId(), 'checksum': 'a' * 64, 'content': content,
            'page_count': 1, 'filename': 'a.pdf', 'created_at': datetime.now(timezone.utc)}


def test_large_page_stops_consuming_cursor_and_closes_it(monkeypatch):
    monkeypatch.setattr(settings, 'max_list_bytes', 1024)
    collection = MagicMock()
    cursor = collection.find.return_value.sort.return_value.skip.return_value.limit.return_value
    consumed = []

    def rows():
        for i in range(100):
            consumed.append(i)
            yield record('x' * 1100)
    cursor.__iter__.side_effect = rows
    with pytest.raises(PageTooLarge):
        MongoDocumentRepository(collection).list(0, 100)
    assert consumed == [0]
    cursor.batch_size.assert_called_once_with(1)
    cursor.close.assert_called_once()


def test_page_limit_has_http_error_and_smaller_page_keeps_contract(collection, api_token, monkeypatch):
    monkeypatch.setattr(settings, 'max_list_bytes', 1024)
    cursor = collection.find.return_value.sort.return_value.skip.return_value.limit.return_value
    cursor.__iter__.side_effect = lambda: iter([record('x' * 500)] * 2)
    client = TestClient(app, headers={'Authorization': f'Bearer {api_token}'})
    assert client.get('/documents').status_code == 413
    cursor.__iter__.side_effect = lambda: iter([record('x' * 500)])
    response = client.get('/documents?limit=1')
    assert response.status_code == 200
    assert response.json()[0]['content'] == 'x' * 500
    assert set(response.json()[0]) == {'id', 'checksum', 'content', 'page_count', 'filename', 'created_at'}


def test_metrics_require_auth_and_do_not_expose_identifiers(collection, api_token):
    client = TestClient(app)
    assert client.get('/metrics').status_code == 401
    client.get('/documents/private-document-identifier')
    response = client.get('/metrics', headers={'Authorization': f'Bearer {api_token}'})
    assert response.status_code == 200
    assert 'documents_http_requests_total' in response.text
    assert 'documents_http_request_duration_seconds_bucket' in response.text
    assert 'documents_requests_in_flight' in response.text
    assert 'private-document-identifier' not in response.text
    assert api_token not in response.text


def test_admission_is_held_until_response_finishes(monkeypatch):
    from threading import BoundedSemaphore
    from app.middleware import AdmissionMiddleware
    limiter = BoundedSemaphore(1)
    monkeypatch.setattr(dependencies, 'admission', limiter)

    async def application(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        assert not limiter.acquire(blocking=False)
        await send({'type': 'http.response.body', 'body': b'payload'})

    async def scenario():
        await AdmissionMiddleware(application)({'type': 'http', 'path': '/documents'}, AsyncMock(), AsyncMock())
    asyncio.run(scenario())
    assert limiter.acquire(blocking=False)
    limiter.release()
