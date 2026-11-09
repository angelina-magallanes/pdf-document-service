from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class Document:
    checksum: str
    content: str
    page_count: int
    filename: str
    created_at: datetime
    id: str | None = None

    @classmethod
    def new(cls, checksum: str, content: str, page_count: int, filename: str | None):
        return cls(checksum, content, page_count, filename or "document.pdf", datetime.now(timezone.utc))


class DocumentNotFound(Exception):
    pass


class InvalidDocumentId(Exception):
    pass


class DuplicateDocument(Exception):
    pass


class DocumentConflict(Exception):
    pass


class PersistenceUnavailable(Exception):
    pass


class DocumentTooLarge(Exception):
    pass


class PageTooLarge(Exception):
    pass


class DocumentRepository(Protocol):
    def insert(self, document: Document) -> Document: ...
    def get_by_checksum(self, checksum: str) -> Document: ...
    def get_by_id(self, document_id: str) -> Document: ...
    def list(self, skip: int, limit: int) -> list[Document]: ...
    def rename(self, document_id: str, filename: str) -> Document: ...
    def delete(self, document_id: str) -> None: ...
