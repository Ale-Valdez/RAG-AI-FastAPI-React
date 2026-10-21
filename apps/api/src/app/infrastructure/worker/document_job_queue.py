from __future__ import annotations

from app.infrastructure.ops_log import CORRELATION_HEADER, current_correlation_id
from app.infrastructure.worker.celery_app import celery_app


class CeleryDocumentJobQueue:
    def enqueue(self, *, tenant_id: str, user_id: str, document_id: str) -> None:
        correlation_id = current_correlation_id()
        headers = {CORRELATION_HEADER: correlation_id} if correlation_id is not None else None
        celery_app.send_task(
            "app.infrastructure.worker.tasks.process_document",
            kwargs={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "document_id": document_id,
            },
            headers=headers,
        )
