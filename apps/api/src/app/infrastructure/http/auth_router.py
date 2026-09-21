from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.application.auth.models import CurrentMember, LoginCommand, LoginResult
from app.domain.actor import Actor
from app.domain.errors import UnauthenticatedError
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.http.dependencies.auth import build_require_actor
from app.infrastructure.http.responses.api_response import error_body, success_body


class LoginBody(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginUseCase(Protocol):
    def execute(self, command: LoginCommand) -> LoginResult: ...


class GetCurrentMemberUseCase(Protocol):
    def execute(self, actor: Actor) -> CurrentMember: ...


def build_auth_router(
    *,
    login: LoginUseCase,
    get_current_member: GetCurrentMemberUseCase,
    jwt_service: JwtService,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    require_actor = build_require_actor(jwt_service)

    @router.post("/auth/login")
    def auth_login(body: LoginBody) -> JSONResponse:
        try:
            result = login.execute(LoginCommand(email=body.email, password=body.password))
        except UnauthenticatedError:
            return JSONResponse(
                error_body("INVALID_CREDENTIALS", "Invalid email or password"),
                status_code=401,
            )
        token = jwt_service.create_access_token(
            user_id=result.user_id, tenant_id=result.tenant_id
        )
        return JSONResponse(success_body({"access_token": token}), status_code=200)

    @router.get("/me")
    def me(actor: Actor = Depends(require_actor)) -> JSONResponse:
        member = get_current_member.execute(actor)
        return JSONResponse(
            success_body(
                {
                    "user_id": member.user_id,
                    "tenant_id": member.tenant_id,
                    "email": member.email,
                }
            ),
            status_code=200,
        )

    return router
