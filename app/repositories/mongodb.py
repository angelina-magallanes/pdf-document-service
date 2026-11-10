from dataclasses import asdict, replace
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
import json

from app import settings
from app.storage_errors import storage_operation

from app.models.document import Document
from app.models.errors import DocumentNotFound, InvalidDocumentId, PageTooLarge


class MongoDocumentRepository:
    def __init__(self, collection):
        self.collection = collection

    @storage_operation
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

    @storage_operation
    def insert(self, document: Document) -> Document:
        data = asdict(document)
        data.pop("id")
        result = self.collection.insert_one(data)
        return replace(document, id=str(result.inserted_id))

    @storage_operation
    def get_by_checksum(self, checksum: str) -> Document:
        return self._document(self.collection.find_one({"checksum": checksum.lower()}))

    @storage_operation
    def get_by_id(self, document_id: str) -> Document:
        return self._document(self.collection.find_one({"_id": self._id(document_id)}))

    @storage_operation
    def list(self, skip: int, limit: int) -> list[Document]:
        cursor = self.collection.find().sort("_id", 1).skip(skip).limit(limit)
        cursor.batch_size(1)
        try:
            return self._bounded_page(cursor)
        finally:
            cursor.close()

    def _bounded_page(self, cursor):
        page, size = [], 2
        for record in cursor:
            document = self._document(record)
            # ensure_ascii overestimates UTF-8 responses, including escaped controls.
            size += len(json.dumps(asdict(document), default=str, ensure_ascii=True)) + 1
            if size > settings.max_list_bytes:
                raise PageTooLarge
            page.append(document)
        return page

    @storage_operation
    def rename(self, document_id: str, filename: str) -> Document:
        record = self.collection.find_one_and_update(
            {"_id": self._id(document_id)}, {"$set": {"filename": filename}},
            return_document=ReturnDocument.AFTER,
        )
        return self._document(record)

    @storage_operation
    def delete(self, document_id: str) -> None:
        result = self.collection.delete_one({"_id": self._id(document_id)})
        if result.deleted_count == 0:
            raise DocumentNotFound
