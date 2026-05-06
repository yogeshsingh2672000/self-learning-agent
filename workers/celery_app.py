"""
Celery application instance.
All agent background tasks are registered here as workers.
"""
from celery import Celery

from core.config import settings


celery_app = Celery(
    "agent_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Ensures tasks are re-queued if the worker crashes mid-execution.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
