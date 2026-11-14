"""In-process background worker for ingestion, multimodal, embedding, and research jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import threading
from time import monotonic
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.domain.documents import DocumentStatus
from app.domain.states import ProjectStatus
from app.models.document import Document
from app.models.research import Research
from app.services.auth import sessions as auth_sessions
from app.services.documents import records as document_records
from app.services.documents.storage import storage_for_settings
from app.services.ingestion.pipeline import process_document, reembed_document
from app.services.jobs import queue as job_queue

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Processing was interrupted before it finished. Retry the document."
RETRY_BACKOFF_SECONDS = 30.0

JobHandler = Callable[[Session, UUID, Settings], None]


def _run_ingestion(session: Session, document_id: UUID, settings: Settings) -> None:
    document = session.get(Document, document_id)
    if document is None or document.status == DocumentStatus.INDEXED:
        return
    storage = storage_for_settings(settings)
    process_document(session, document, storage.path_for(document.stored_name), settings)


def _run_reembedding(session: Session, document_id: UUID, settings: Settings) -> None:
    document = session.get(Document, document_id)
    if document is None:
        return
    reembed_document(session, document, settings)


def _run_research(session: Session, research_id: UUID, settings: Settings) -> None:
    from app.services.rag import query as rag_query

    record = session.get(Research, research_id)
    if record is None or record.user_id is None:
        return
    if record.project_status in (ProjectStatus.REPORT_READY, ProjectStatus.PROCESSING_FAILED):
        return
    rag_query.execute_research(session, research_id, record.user_id, settings)


def _fail_target(session: Session, kind: str, target_id: UUID) -> None:
    if kind in job_queue.ALL_INGEST_KINDS:
        document_records.mark_interrupted(session, target_id, INTERRUPTED_MESSAGE)
    elif kind == job_queue.RUN_RESEARCH:
        from app.services.research import runs as research_runs

        record = session.get(Research, target_id)
        if record is not None and record.project_status != ProjectStatus.REPORT_READY:
            research_runs.mark_research_failed(session, target_id)


def default_job_handlers() -> dict[str, JobHandler]:
    return {
        job_queue.INGEST_DOCUMENT: _run_ingestion,
        job_queue.INGEST_AUDIO: _run_ingestion,
        job_queue.INGEST_VIDEO: _run_ingestion,
        job_queue.INGEST_URL: _run_ingestion,
        job_queue.GENERATE_EMBEDDINGS: _run_reembedding,
        job_queue.RUN_RESEARCH: _run_research,
    }


class JobWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        handlers: dict[str, JobHandler] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.handlers = handlers or default_job_handlers()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._last_maintenance = 0.0
        self._maintenance_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        for index in range(self.settings.worker_threads):
            thread = threading.Thread(
                target=self._loop, name=f"job-worker-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        logger.info("Background worker started", extra={"threads": len(self._threads)})

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads.clear()

    def wake(self) -> None:
        self._wake.set()

    # -- work ----------------------------------------------------------------

    def _loop(self) -> None:
        if self.settings.model_warmup_on_startup:
            self._warm_up()
        while not self._stop.is_set():
            try:
                self.run_maintenance_if_due()
                if self.run_once():
                    continue
            except Exception:  # pragma: no cover - keep the worker alive
                logger.exception("Background worker loop error")
            self._wake.wait(self.settings.worker_poll_seconds)
            self._wake.clear()

    def run_once(self) -> bool:
        """Claim and run one job. Returns False when the queue is empty."""
        with self.session_factory() as session:
            claimed = job_queue.claim_next(session)
            if claimed is None:
                return False
            self._execute(session, claimed)
            return True

    def run_job_by_id(self, job_id: UUID) -> bool:
        """Claim and run a specific job by ID (used by Celery workers)."""
        with self.session_factory() as session:
            claimed = job_queue.claim_by_id(session, job_id)
            if claimed is None:
                return False
            self._execute(session, claimed)
            return True

    def run_until_empty(self, limit: int = 100) -> int:
        processed = 0
        while processed < limit and self.run_once():
            processed += 1
        return processed

    def _execute(self, session: Session, job: job_queue.ClaimedJob) -> None:
        handler = self.handlers.get(job.kind)
        started = monotonic()
        if handler is None:
            job_queue.mark_failed(session, job.id, f"Unknown job kind {job.kind}")
            return
        try:
            handler(session, job.target_id, self.settings)
        except AppError as exc:
            session.rollback()
            job_queue.mark_failed(session, job.id, f"{exc.code}: {exc.message}")
            logger.info(
                "Background job finished with an application error",
                extra={"job_id": str(job.id), "kind": job.kind, "code": exc.code},
            )
            return
        except Exception as exc:
            session.rollback()
            if job.attempts < self.settings.job_max_attempts:
                job_queue.mark_failed(
                    session, job.id, repr(exc), retry_in_seconds=RETRY_BACKOFF_SECONDS * job.attempts
                )
            else:
                job_queue.mark_failed(session, job.id, repr(exc))
                _fail_target(session, job.kind, job.target_id)
            logger.exception(
                "Background job crashed",
                extra={"job_id": str(job.id), "kind": job.kind, "attempt": job.attempts},
            )
            return
        duration_ms = round((monotonic() - started) * 1000, 1)
        job_queue.mark_succeeded(session, job.id)
        logger.info(
            "Background job succeeded",
            extra={
                "job_id": str(job.id),
                "kind": job.kind,
                "duration_ms": duration_ms,
            },
        )

    # -- maintenance -------------------------------------------------------

    def run_maintenance_if_due(self) -> None:
        now = monotonic()
        with self._maintenance_lock:
            if self._last_maintenance and now - self._last_maintenance < self.settings.maintenance_interval_seconds:
                return
            self._last_maintenance = now
        self.run_maintenance()

    def run_maintenance(self) -> dict[str, int]:
        with self.session_factory() as session:
            requeued, failed = self._recover_stale_jobs(session)
            orphaned = self._fail_orphaned_documents(session)
            sessions_removed, states_removed = auth_sessions.purge_expired(session)
        summary = {
            "jobs_requeued": requeued,
            "jobs_failed": failed,
            "documents_unstuck": orphaned,
            "sessions_purged": sessions_removed,
            "oauth_states_purged": states_removed,
        }
        if any(summary.values()):
            logger.info("Maintenance pass finished", extra=summary)
        return summary

    def _recover_stale_jobs(self, session: Session) -> tuple[int, int]:
        requeued = failed = 0
        for job in job_queue.stale_running_jobs(session, self.settings.job_stale_after_seconds):
            if job.attempts < self.settings.job_max_attempts:
                job_queue.mark_failed(session, job.id, "Worker stopped mid-run", retry_in_seconds=0)
                requeued += 1
            else:
                job_queue.mark_failed(session, job.id, "Worker stopped mid-run too many times")
                _fail_target(session, job.kind, job.target_id)
                failed += 1
        return requeued, failed

    def _fail_orphaned_documents(self, session: Session) -> int:
        """Fail documents left in ``processing`` by a crashed inline request."""
        cutoff = utc_now() - timedelta(seconds=self.settings.job_stale_after_seconds)
        stuck = session.scalars(
            select(Document.id).where(
                Document.status == DocumentStatus.PROCESSING,
                Document.updated_at <= cutoff,
            )
        ).all()
        count = 0
        for document_id in stuck:
            if job_queue.has_active_job(session, job_queue.ALL_INGEST_KINDS, document_id):
                continue
            document_records.mark_interrupted(session, document_id, INTERRUPTED_MESSAGE)
            count += 1
        waiting = session.scalars(
            select(Document.id).where(
                Document.status == DocumentStatus.UPLOADED,
                Document.updated_at <= cutoff,
            )
        ).all()
        for document_id in waiting:
            if job_queue.has_active_job(session, job_queue.ALL_INGEST_KINDS, document_id):
                continue
            if self.settings.ingestion_mode == "background":
                job_queue.enqueue(session, job_queue.INGEST_DOCUMENT, document_id)
            else:
                document_records.mark_interrupted(session, document_id, INTERRUPTED_MESSAGE)
            count += 1
        return count

    def _warm_up(self) -> None:
        from app.providers.router import get_cached_router_for_settings
        from app.services.rag.embeddings import embedding_service_for
        from app.services.rag.reranking import reranker_service_for

        started = monotonic()
        try:
            if self.settings.embedding_enabled:
                embedding_service_for(self.settings)
            if self.settings.generation_runtime == "router":
                get_cached_router_for_settings(self.settings)
            reranker = reranker_service_for(self.settings)
            if hasattr(reranker, "_load_model"):
                reranker._load_model()
            logger.info(
                "Model warm-up finished",
                extra={"duration_ms": round((monotonic() - started) * 1000, 1)},
            )
        except Exception:
            logger.exception("Model warm-up failed; models will load on first use")
