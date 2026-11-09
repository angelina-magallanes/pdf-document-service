from contextlib import asynccontextmanager
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app.auth import load_api_token
from app.database import client, documents, max_inflight
from app.repository import MongoDocumentRepository
from app.service import DocumentService
from app.storage_errors import storage_operation

admission = BoundedSemaphore(max_inflight)


def get_service():
    return DocumentService(MongoDocumentRepository(documents))


@storage_operation
def check_database():
    client.admin.command("ping")


def initialize_database():
    client.admin.command("ping")
    MongoDocumentRepository(documents).initialize()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.api_token = load_api_token()
        await run_in_threadpool(initialize_database)
        yield
    finally:
        app.state.api_token = None
        await run_in_threadpool(client.close)
