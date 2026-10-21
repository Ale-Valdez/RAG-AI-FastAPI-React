from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from contextvars import ContextVar, Token

OPS_LOGGER_NAME = "app.ops"
CORRELATION_HEADER = "ai_rag_correlation_id"

_correlation_id: ContextVar[str | None] = ContextVar(CORRELATION_HEADER, default=None)
_OPS = logging.getLogger(OPS_LOGGER_NAME)
_OPS.setLevel(logging.INFO)


def current_correlation_id() -> str | None:
    return _correlation_id.get()


def bind_correlation_id(correlation_id: str) -> Token[str | None]:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id.reset(token)


def install_ops_stderr_handler() -> None:
    """Emit the JSON message as-is when the process has not configured logging."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)


def correlation_id_from_headers(headers: object) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    value = headers.get(CORRELATION_HEADER)
    if isinstance(value, str) and value:
        return value
    return None


def log_http_request(
    *,
    correlation_id: str,
    tenant_id: str | None,
    route: str,
    status_code: int,
) -> None:
    _emit(
        {
            "event": "http.request",
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "route": route,
            "status_code": status_code,
        }
    )


def log_ingestion_job(
    *,
    correlation_id: str | None,
    tenant_id: str,
    document_id: str,
    status: str,
) -> None:
    _emit(
        {
            "event": "ingestion.job",
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "status": status,
        }
    )


def _emit(payload: Mapping[str, object]) -> None:
    _OPS.info("%s", json.dumps(payload))
