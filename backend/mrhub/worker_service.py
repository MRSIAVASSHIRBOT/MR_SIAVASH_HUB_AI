"""Explicit pull-worker process for queued MR SIAVASH AI HUB jobs.

Run with python -m mrhub.worker_service from the repository root after
configuring the database path and workflow payload encryption key. The API does
not silently start background execution; operators opt into this process.
"""
from __future__ import annotations

import signal
import time
from threading import Event

from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine


def main() -> None:
    settings = get_settings()
    repository = TaskRepository(settings.database_path)
    repository.initialize()
    worker = WorkerEngine(repository)
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    while not stop.is_set():
        try:
            result = worker.run_once()
        except Exception:
            # Persisted failure state is sanitized; never log payload-bearing
            # exception text from model providers or external tools.
            time.sleep(1.0)
            continue
        if result is None:
            stop.wait(0.5)


if __name__ == "__main__":
    main()
