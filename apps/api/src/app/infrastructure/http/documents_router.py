from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse, Response

from app.application.documents.get_document_file import DocumentFile
from app.application.documents.models import UploadDocumentCommand
from app.domain.actor import Actor
from app.domain.documents import Document
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.auth.oidc import OidcTokenVerifier
from app.infrastructure.http.dependencies.auth import build_require_actor
from app.infrastructure.http.responses.api_response import success_body


class UploadDocumentUseCase(Protocol):
    def execute(self, actor: Actor, command: UploadDocumentCommand) -> Document: ...


class ListDocumentsUseCase(Protocol):
    def execute(self, actor: Actor) -> list[Document]: ...


class DeleteDocumentUseCase(Protocol):
    def execute(self, actor: Actor, document_id: str) -> str: ...


class ReingestDocumentUseCase(Protocol):
    def execute(self, actor: Actor, document_id: str) -> Document: ...


class GetDocumentFileUseCase(Protocol):
    def execute(self, actor: Actor, document_id: str) -> DocumentFile: ...


def _document_payload(document: Document) -> dict[str, str]:
    return {
        "id": document.id,
        "filename": document.filename,
        "status": document.status.value,
    }


def _inline_disposition(filename: str) -> str:
    cleaned = filename.replace('"', "").replace("\r", "").replace("\n", "")
    try:
        cleaned.encode("latin-1")
    except UnicodeEncodeError:
        fallback = cleaned.encode("latin-1", errors="replace").decode("latin-1")
        encoded = quote(cleaned, safe="")
        return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
    return f'inline; filename="{cleaned}"'


def build_documents_router(
    *,
    upload_document: UploadDocumentUseCase,
    list_documents: ListDocumentsUseCase,
    delete_document: DeleteDocumentUseCase,
    reingest_document: ReingestDocumentUseCase,
    get_document_file: GetDocumentFileUseCase,
    jwt_service: JwtService,
    oidc_verifier: OidcTokenVerifier | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    require_actor = build_require_actor(jwt_service, oidc_verifier)

    @router.post("/documents")
    def documents_upload(
        actor: Actor = Depends(require_actor),
        file: UploadFile = File(...),
    ) -> JSONResponse:
        content = file.file.read()
        document = upload_document.execute(
            actor,
            UploadDocumentCommand(filename=file.filename or "", content=content),
        )
        return JSONResponse(success_body(_document_payload(document)), status_code=201)

    @router.get("/documents")
    def documents_list(actor: Actor = Depends(require_actor)) -> JSONResponse:
        documents = list_documents.execute(actor)
        return JSONResponse(
            success_body({"documents": [_document_payload(item) for item in documents]}),
            status_code=200,
        )

    @router.delete("/documents/{document_id}")
    def documents_delete(
        document_id: str,
        actor: Actor = Depends(require_actor),
    ) -> JSONResponse:
        deleted_id = delete_document.execute(actor, document_id)
        return JSONResponse(success_body({"id": deleted_id}), status_code=200)

    @router.post("/documents/{document_id}/reingest")
    def documents_reingest(
        document_id: str,
        actor: Actor = Depends(require_actor),
    ) -> JSONResponse:
        document = reingest_document.execute(actor, document_id)
        return JSONResponse(success_body(_document_payload(document)), status_code=200)

    @router.get("/documents/{document_id}/file")
    def documents_file(
        document_id: str,
        actor: Actor = Depends(require_actor),
    ) -> Response:
        document_file = get_document_file.execute(actor, document_id)
        return Response(
            content=document_file.content,
            media_type="application/pdf",
            headers={"Content-Disposition": _inline_disposition(document_file.filename)},
        )

    return router
