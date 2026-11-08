from app.domain import Document, DocumentConflict, DocumentNotFound, DocumentRepository, DuplicateDocument


class DocumentService:
    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    def create(self, document: Document) -> tuple[Document, bool]:
        try:
            return self.repository.insert(document), True
        except DuplicateDocument:
            return self._get_duplicate(document), False

    def _get_duplicate(self, document: Document) -> Document:
        try:
            return self.repository.get_by_checksum(document.checksum)
        except DocumentNotFound:
            raise DocumentConflict from None

    def get_by_checksum(self, checksum: str) -> Document:
        return self.repository.get_by_checksum(checksum)

    def get_by_id(self, document_id: str) -> Document:
        return self.repository.get_by_id(document_id)

    def list(self, skip: int, limit: int) -> list[Document]:
        return self.repository.list(skip, limit)

    def rename(self, document_id: str, filename: str) -> Document:
        return self.repository.rename(document_id, filename)

    def delete(self, document_id: str) -> None:
        self.repository.delete(document_id)
