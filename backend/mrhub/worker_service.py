"""Explicit pull-worker process for queued MR SIAVASH AI HUB jobs.

Run with python -m mrhub.worker_service from the repository root after
configuring the database path and workflow payload encryption key. The API does
not silently start background execution; operators opt into this process.
"""
from __future__ import annotations

import os
import signal
import sqlite3
import time
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid4

from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine, WorkerError


def main() -> None:
    settings = get_settings()
    repository = TaskRepository(settings.database_path)
    repository.initialize()
    worker = WorkerEngine(repository)
    stop = Event()
    heartbeat_stop = Event()
    instance_id = str(uuid4())
    stamp = datetime.now(UTC).isoformat()
    with sqlite3.connect(settings.database_path, timeout=5.0) as connection:
        connection.execute(
            """INSERT INTO worker_instances
               (instance_id, process_id, started_at, heartbeat_at, stopped_at, status)
               VALUES (?, ?, ?, ?, NULL, 'running')""",
            (instance_id, os.getpid(), stamp, stamp),
        )

    def heartbeat_loop() -> None:
        while not heartbeat_stop.wait(3.0):
            try:
                with sqlite3.connect(settings.database_path, timeout=5.0) as connection:
                    connection.execute(
                        "UPDATE worker_instances SET heartbeat_at = ? WHERE instance_id = ? AND status = 'running'",
                        (datetime.now(UTC).isoformat(), instance_id),
                    )
            except sqlite3.Error:
                # A missed heartbeat fails readiness closed; never log secrets.
                continue

    heartbeat_thread = Thread(target=heartbeat_loop, name="mrhub-worker-heartbeat", daemon=True)
    heartbeat_thread.start()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        while not stop.is_set():
            try:
                result = worker.run_once()
            except (WorkerError, sqlite3.Error, RuntimeError, ValueError):
                # Persisted failure state is sanitized; never log payload-bearing
                # exception text from model providers or external tools.
                time.sleep(1.0)
                continue
            if result is None:
                stop.wait(0.5)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=4.0)
        stamp = datetime.now(UTC).isoformat()
        with sqlite3.connect(settings.database_path, timeout=5.0) as connection:
            connection.execute(
                "UPDATE worker_instances SET status = 'stopped', stopped_at = ?, heartbeat_at = ? WHERE instance_id = ?",
                (stamp, stamp, instance_id),
            )


if __name__ == "__main__":
    main()
