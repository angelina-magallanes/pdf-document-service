from functools import wraps

from pymongo.errors import DocumentTooLarge as MongoDocumentTooLarge
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from app.models.errors import DocumentTooLarge, DuplicateDocument, PersistenceUnavailable


def storage_operation(operation):
    @wraps(operation)
    def translated(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except DuplicateKeyError:
            raise DuplicateDocument from None
        except MongoDocumentTooLarge:
            raise DocumentTooLarge from None
        except OperationFailure as exc:
            if exc.code == 10334:
                raise DocumentTooLarge from None
            raise PersistenceUnavailable from None
        except PyMongoError:
            raise PersistenceUnavailable from None
    return translated
