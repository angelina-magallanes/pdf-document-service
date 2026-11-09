import os


def positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


max_body_bytes = positive_int("DOCUMENTS_MAX_BODY_BYTES", 4 * 1024 * 1024)
max_list_bytes = positive_int("DOCUMENTS_MAX_LIST_BYTES", 8 * 1024 * 1024)
body_timeout_seconds = positive_int("DOCUMENTS_BODY_TIMEOUT_SECONDS", 15)
