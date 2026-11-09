"""Credencial compartida para las llamadas HTTP a Documents."""

import os
import re
from secrets import compare_digest

from fastapi.security import HTTPBearer


bearer_scheme = HTTPBearer(
    scheme_name="DocumentsBearer", auto_error=False,
    description="Token compartido configurado en DOCUMENTS_API_TOKEN.",
)
PUBLIC_PATHS = frozenset({
    "/health", "/health/live", "/health/ready", "/docs",
    "/docs/oauth2-redirect", "/redoc", "/openapi.json",
})


def load_api_token() -> str:
    token = os.getenv("DOCUMENTS_API_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9._~+/-]{32,512}={0,2}", token):
        raise ValueError(
            "DOCUMENTS_API_TOKEN es obligatorio: usar un secreto aleatorio "
            "de al menos 32 caracteres sin espacios"
        )
    return token


def authorized(headers, expected: str) -> bool:
    # Cabeceras repetidas o credenciales ambiguas se rechazan.
    values = headers.getlist("authorization")
    if len(values) != 1:
        return False
    parts = values[0].split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return False
    return compare_digest(parts[1].encode("utf-8"), expected.encode("utf-8"))
