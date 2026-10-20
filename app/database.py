import os

from pymongo import MongoClient

client = MongoClient(
    os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
    serverSelectionTimeoutMS=5000,
)

database = client[
    os.getenv("MONGODB_DATABASE", "pdf_extractext")
]
documents = database["documents"]
