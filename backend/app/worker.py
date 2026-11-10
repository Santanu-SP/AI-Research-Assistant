"""Run the background worker without the HTTP API.

    python -m app.worker

Useful when the API runs with ``WORKER_ENABLED=false`` (for example several
API replicas sharing one worker container).
"""

import signal
import threading

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory
from app.services.jobs.worker import JobWorker


def main() -> None:
    configure_logging(settings.log_level, json_logs=settings.log_json)
    engine = create_db_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
    )
    worker = JobWorker(create_session_factory(engine), settings)
    stopped = threading.Event()

    def _stop(*_: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    worker.start()
    stopped.wait()
    worker.stop()
    engine.dispose()


if __name__ == "__main__":
    main()
