from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checksum: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    content: str
    page_count: int = Field(gt=0, le=2**63 - 1, strict=True)
    filename: str | None = Field(default=None, max_length=255)

    @field_validator("checksum")
    @classmethod
    def normalize_checksum(cls, value: str) -> str:
        return value.lower()

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre del archivo no puede estar vacío")

        return cleaned


class DocumentResponse(DocumentCreate):
    filename: str = Field(max_length=255)
    id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_milliseconds(cls, value: datetime) -> datetime:
        # BSON almacena fechas UTC con precisión de milisegundos.
        utc = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc.replace(microsecond=(utc.microsecond // 1000) * 1000)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre del archivo no puede estar vacío")
        return cleaned


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    request_id: str
    errors: list[dict] | None = None
