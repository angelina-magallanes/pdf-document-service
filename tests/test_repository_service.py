from unittest.mock import Mock

import pytest

from app.domain import Document, DocumentConflict, DocumentNotFound, DuplicateDocument
from app.service import DocumentService


def document():
    return Document.new("a" * 64, "# Texto", 1, None)


def test_servicio_devuelve_original_si_el_checksum_ya_existe():
    repo = Mock()
    original = document()
    repo.insert.side_effect = DuplicateDocument
    repo.get_by_checksum.return_value = original
    result, created = DocumentService(repo).create(document())
    assert result is original
    assert created is False
    repo.get_by_checksum.assert_called_once_with(original.checksum)


def test_servicio_informa_conflicto_si_duplicado_se_elimina():
    repo = Mock()
    repo.insert.side_effect = DuplicateDocument
    repo.get_by_checksum.side_effect = DocumentNotFound
    with pytest.raises(DocumentConflict):
        DocumentService(repo).create(document())
