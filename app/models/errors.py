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

