from dataclasses import dataclass
from datetime import datetime, timezone


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

