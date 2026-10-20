import pytest
from pydantic import ValidationError

from app.schemas import DocumentCreate, DocumentUpdate


def test_normaliza_checksum():
    document = DocumentCreate(
        checksum="A" * 64,
        content="# Prueba",
        page_count=1,
    )

    assert document.checksum == "a" * 64


@pytest.mark.parametrize("checksum", ["abc", "z" * 64])
def test_rechaza_checksum_invalido(checksum):
    with pytest.raises(ValidationError):
        DocumentCreate(
            checksum=checksum,
            content="# Prueba",
            page_count=1,
        )


@pytest.mark.parametrize("page_count", [0, -1, "2", True])
def test_rechaza_cantidad_de_paginas_invalida(page_count):
    with pytest.raises(ValidationError):
        DocumentCreate(
            checksum="a" * 64,
            content="# Prueba",
            page_count=page_count,
        )


def test_actualizacion_limpia_nombre():
    update = DocumentUpdate(filename="  informe.pdf  ")

    assert update.filename == "informe.pdf"


def test_actualizacion_rechaza_nombre_vacio():
    with pytest.raises(ValidationError):
        DocumentUpdate(filename="   ")


def test_actualizacion_rechaza_cambiar_contenido():
    with pytest.raises(ValidationError):
        DocumentUpdate(
            filename="informe.pdf",
            content="Contenido modificado",
        )