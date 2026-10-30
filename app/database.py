import os

from pymongo import MongoClient

timeout_ms = int(os.getenv("MONGODB_TIMEOUT_MS", "1500"))
if timeout_ms <= 0:
    raise ValueError("MONGODB_TIMEOUT_MS debe ser mayor que cero")

client = MongoClient(
    os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
    serverSelectionTimeoutMS=timeout_ms,
    connectTimeoutMS=timeout_ms,
    socketTimeoutMS=timeout_ms,
    waitQueueTimeoutMS=timeout_ms,
    timeoutMS=timeout_ms,
    appname="pdf-document-service",
)

database = client[os.getenv("MONGODB_DATABASE", "pdf_extractext")]
documents = database["documents"]
