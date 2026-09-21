from celery import Celery

from app.infrastructure.config.settings import load_settings

settings = load_settings()
celery_app = Celery(
    "ai_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_default_queue = "ai-rag-ingestion"
