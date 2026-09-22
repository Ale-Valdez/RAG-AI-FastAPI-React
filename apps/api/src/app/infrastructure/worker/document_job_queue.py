from __future__ import annotations

from app.infrastructure.worker.celery_app import celery_app


class CeleryDocumentJobQueue:
    def enqueue(self, *, tenant_id: str, user_id: str, document_id: str) -> None:
        celery_app.send_task(
            "app.infrastructure.worker.tasks.process_document",
            kwargs={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "document_id": document_id,
            },
        )
