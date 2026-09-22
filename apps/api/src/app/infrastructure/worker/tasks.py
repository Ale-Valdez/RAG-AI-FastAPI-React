from app.infrastructure.worker.celery_app import celery_app


@celery_app.task(name="app.infrastructure.worker.tasks.process_document")
def process_document(tenant_id: str, user_id: str, document_id: str) -> None:
    """No-op placeholder; story 2.2 replaces the body. Leaves documents pending."""
    return None
