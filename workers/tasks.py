"""
Background task definitions.

Phase 1: health-check stub only.
Phase 4+: coding_agent, testing_agent tasks will be added here.
"""
from workers.celery_app import celery_app


@celery_app.task(name="workers.tasks.worker_health_check", bind=True)
def worker_health_check(self) -> dict:
    """Verify the Celery worker is running and reachable."""
    return {"status": "worker healthy", "task_id": self.request.id}
