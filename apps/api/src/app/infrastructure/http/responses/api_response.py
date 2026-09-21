from __future__ import annotations

from typing import Any


def success_body(data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "error": None}


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"data": None, "error": {"code": code, "message": message}}
