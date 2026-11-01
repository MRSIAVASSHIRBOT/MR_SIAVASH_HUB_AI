"""Explicit CLI entry point for the pull-driven worker process."""
from __future__ import annotations

import argparse
import logging
import signal
from threading import Event

from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MR_SIAVASH_HUB_AI worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="claim at most one eligible task and exit",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
        help="idle polling interval from 0.2 to 60 seconds (default: 1)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 0.2 <= args.poll_seconds <= 60:
        raise SystemExit("--poll-seconds must be between 0.2 and 60")
    logging.basicConfig(level=get_settings().log_level)
    settings = get_settings()
    worker = WorkerEngine(TaskRepository(settings.database_path))
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    while not stop.is_set():
        task = worker.run_once()
        if task is not None:
            logger.info(
                "worker task finished: task_id=%s status=%s",
                task.task_id,
                task.status.value,
            )
        if args.once:
            break
        if task is None:
            stop.wait(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
