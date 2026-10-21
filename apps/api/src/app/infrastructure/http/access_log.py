from __future__ import annotations

from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.infrastructure.ops_log import bind_correlation_id, log_http_request, reset_correlation_id


class AccessLogMiddleware:
    """One JSON line per finished `/api/v1` request. Does not read the body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_product_path(scope.get("path")):
            await self.app(scope, receive, send)
            return

        correlation_id = str(uuid4())
        token = bind_correlation_id(correlation_id)
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                log_http_request(
                    correlation_id=correlation_id,
                    tenant_id=_tenant_id(scope),
                    route=_route_label(scope),
                    status_code=status_code,
                )
            finally:
                reset_correlation_id(token)


def _is_product_path(path: object) -> bool:
    return isinstance(path, str) and path.startswith("/api/v1")


def _tenant_id(scope: Scope) -> str | None:
    state = scope.get("state")
    if not isinstance(state, dict):
        return None
    tenant_id = state.get("tenant_id")
    if isinstance(tenant_id, str) and tenant_id:
        return tenant_id
    return None


def _route_label(scope: Scope) -> str:
    method = scope.get("method")
    method_label = method if isinstance(method, str) else ""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str) or not template:
        path = scope.get("path")
        template = path if isinstance(path, str) else ""
    return f"{method_label} {template}"
