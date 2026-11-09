import os

from pymongo import MongoClient


from app.settings import positive_int


timeout_ms = positive_int("MONGODB_TIMEOUT_MS", 1500)
pool_size = positive_int("MONGODB_POOL_SIZE", 16)
wait_queue_ms = positive_int("MONGODB_WAIT_QUEUE_MS", 200)
max_inflight = positive_int("DOCUMENTS_MAX_IN_FLIGHT", 16)

client = MongoClient(
    os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
    serverSelectionTimeoutMS=timeout_ms,
    connectTimeoutMS=timeout_ms,
    socketTimeoutMS=timeout_ms,
    waitQueueTimeoutMS=wait_queue_ms,
    timeoutMS=timeout_ms,
    maxPoolSize=pool_size,
    appname="pdf-document-service",
)

database = client[os.getenv("MONGODB_DATABASE", "pdf_extractext")]
documents = database["documents"]
