from app.application.documents.process_document import ProcessOutcome
from app.domain.actor import Actor
from app.infrastructure.ops_log import correlation_id_from_headers, log_ingestion_job
from app.infrastructure.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.infrastructure.worker.tasks.process_document",
    max_retries=None,
)
def process_document(self, tenant_id: str, user_id: str, document_id: str) -> None:
    from app.bootstrap.worker import build_process_document

    outcome = build_process_document().execute(
        Actor(tenant_id=tenant_id, user_id=user_id),
        document_id,
    )
    if outcome is ProcessOutcome.DEFERRED:
        raise self.retry(countdown=5)
    if outcome is ProcessOutcome.READY or outcome is ProcessOutcome.FAILED:
        log_ingestion_job(
            correlation_id=correlation_id_from_headers(self.request.headers),
            tenant_id=tenant_id,
            document_id=document_id,
            status=outcome.value,
        )
