from dataclasses import asdict, replace
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.domain import Document, DocumentNotFound, DuplicateDocument, InvalidDocumentId


class MongoDocumentRepository:
    def __init__(self, collection):
        self.collection = collection

    def initialize(self):
        self.collection.create_index("checksum", unique=True, name="uq_documents_checksum")

    @staticmethod
    def _id(value: str):
        try:
            return ObjectId(value)
        except InvalidId:
            raise InvalidDocumentId from None

    @staticmethod
    def _document(record):
        if record is None:
            raise DocumentNotFound
        return Document(
            id=str(record["_id"]), checksum=record["checksum"], content=record["content"],
            page_count=record["page_count"], filename=record.get("filename") or "document.pdf",
            created_at=record["created_at"],
        )

    def insert(self, document: Document) -> Document:
        data = asdict(document)
        data.pop("id")
        try:
            result = self.collection.insert_one(data)
        except DuplicateKeyError:
            raise DuplicateDocument from None
        return replace(document, id=str(result.inserted_id))

    def get_by_checksum(self, checksum: str) -> Document:
        return self._document(self.collection.find_one({"checksum": checksum.lower()}))

    def get_by_id(self, document_id: str) -> Document:
        return self._document(self.collection.find_one({"_id": self._id(document_id)}))

    def list(self, skip: int, limit: int) -> list[Document]:
        cursor = self.collection.find().sort("_id", 1).skip(skip).limit(limit)
        return [self._document(record) for record in cursor]

    def rename(self, document_id: str, filename: str) -> Document:
        record = self.collection.find_one_and_update(
            {"_id": self._id(document_id)}, {"$set": {"filename": filename}},
            return_document=ReturnDocument.AFTER,
        )
        return self._document(record)

    def delete(self, document_id: str) -> None:
        result = self.collection.delete_one({"_id": self._id(document_id)})
        if result.deleted_count == 0:
            raise DocumentNotFound
