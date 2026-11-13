"""Celery + Redis integration for distributed background job execution.

When ``QUEUE_BACKEND=celery`` (and ``celery``/``redis`` are installed), jobs
created in ``background_jobs`` are also dispatched to Redis queues (`ingestion`,
`multimodal`, `embeddings`, `research`). Each Celery task executes idempotently
through :class:`app.services.jobs.worker.JobWorker` so database state, retries,
and status polling stay 100% unified.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.config import Settings, settings
from app.db.session import create_db_engine, create_session_factory
from app.services.jobs import queue as job_queue
from app.services.jobs.worker import JobWorker

logger = logging.getLogger(__name__)

QUEUE_ROUTING: dict[str, str] = {
    job_queue.INGEST_DOCUMENT: "ingestion",
    job_queue.INGEST_AUDIO: "multimodal",
    job_queue.INGEST_VIDEO: "multimodal",
    job_queue.INGEST_URL: "multimodal",
    job_queue.GENERATE_EMBEDDINGS: "embeddings",
    job_queue.RUN_RESEARCH: "research",
}


def execute_queued_job(job_id: str | UUID, active_settings: Settings | None = None) -> bool:
    """Execute one database-tracked background job idempotently."""
    cfg = active_settings or settings
    parsed_id = UUID(str(job_id))
    engine = create_db_engine(
        cfg.database_url,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        pool_timeout=cfg.db_pool_timeout_seconds,
        pool_recycle=cfg.db_pool_recycle_seconds,
        pool_use_lifo=cfg.db_pool_use_lifo,
    )
    try:
        session_factory = create_session_factory(engine)
        worker = JobWorker(session_factory, cfg)
        return worker.run_job_by_id(parsed_id)
    finally:
        engine.dispose()


def create_celery_app(active_settings: Settings | None = None) -> Any:
    """Build a Celery application if the ``celery`` package is installed."""
    cfg = active_settings or settings
    try:
        from celery import Celery  # type: ignore[import-not-found]
    except ImportError:
        return None

    app = Celery(
        "ai_research_assistant",
        broker=cfg.effective_celery_broker_url,
        backend=cfg.effective_celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=cfg.celery_task_time_limit_seconds,
        task_soft_time_limit=cfg.celery_task_soft_time_limit_seconds,
        worker_concurrency=cfg.worker_threads,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
    )

    @app.task(
        name="ara.execute_job",
        bind=True,
        max_retries=cfg.job_max_attempts,
        default_retry_delay=30,
    )
    def _celery_execute_job(self: Any, job_id: str, kind: str, target_id: str) -> dict[str, Any]:
        del self
        ran = execute_queued_job(job_id, cfg)
        return {"job_id": job_id, "kind": kind, "target_id": target_id, "executed": ran}

    return app


celery_app = create_celery_app()


def dispatch_celery_job(
    job_id: UUID,
    kind: str,
    target_id: UUID,
    *,
    settings: Settings | None = None,
) -> bool:
    """Send a job to the appropriate Redis queue via Celery if available."""
    app = celery_app or create_celery_app(settings)
    if app is None:
        logger.debug("Celery library not installed; using in-process/DB worker queue")
        return False
    queue_name = QUEUE_ROUTING.get(kind, "default")
    app.send_task(
        "ara.execute_job",
        args=[str(job_id), kind, str(target_id)],
        queue=queue_name,
    )
    return True

