from celery import Celery

from app.infrastructure.config.settings import load_settings

settings = load_settings()
celery_app = Celery(
    "ai_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.infrastructure.worker.tasks"],
)
# One child, and it exits after each PDF. A warm Docling process holds
# the layout models (several GB) for the life of the process; on a laptop
# that resident set has to be given back to the OS between documents.
celery_app.conf.update(
    task_default_queue="ai-rag-ingestion",
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1,
)
