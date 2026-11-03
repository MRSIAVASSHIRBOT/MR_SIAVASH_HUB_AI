"""Real-process smoke test for the API/worker boundary.

Unlike TestClient-only workflow tests, this launches the API and pull worker as
separate OS processes sharing only the configured SQLite database and payload key.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def _request(base_url: str, path: str, *, method: str = "GET", body=None, token=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    with urlopen(request, timeout=2.0) as response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None


def test_api_and_worker_execute_queued_workflow_in_separate_processes(tmp_path: Path) -> None:
    # Ask the OS for a free local port, then release it before uvicorn binds.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "runtime-smoke.sqlite3"
    env = os.environ.copy()
    env.update(
        {
            "MRH_DATABASE_PATH": str(database),
            "MRH_WORKFLOW_PAYLOAD_KEY": base64.urlsafe_b64encode(
                b"runtime-smoke-key-material-32byt"
            ).decode("ascii"),
            "MRH_ENVIRONMENT": "test",
            "PYTHONPATH": str(root / "backend")
            + os.pathsep
            + env.get("PYTHONPATH", ""),
        }
    )
    base_url = f"http://127.0.0.1:{port}"
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mrhub.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    worker = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if api.poll() is not None:
                raise AssertionError(f"API process exited during startup: {api.returncode}")
            try:
                status, _ = _request(base_url, "/health")
                if status == 200:
                    break
            except (URLError, TimeoutError, OSError):
                time.sleep(0.2)
        else:
            raise AssertionError("API did not become healthy within 20 seconds")

        status, _ = _request(
            base_url,
            "/auth/setup",
            method="POST",
            body={"password": "runtime-smoke-password-2026-strong"},
        )
        assert status == 201
        status, login = _request(
            base_url,
            "/auth/login",
            method="POST",
            body={
                "username": "owner",
                "password": "runtime-smoke-password-2026-strong",
            },
        )
        assert status == 200
        token = login["access_token"]

        # The worker is a separate process; API requests only enqueue work.
        worker = subprocess.Popen(
            [sys.executable, "-m", "mrhub.worker_service"],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        status, queued = _request(
            base_url,
            "/agent/workflows",
            method="POST",
            token=token,
            body={
                "goal": "Verify API-to-worker execution across process boundaries",
                "tools": [{"name": "text.echo", "payload": {"text": "runtime-smoke"}}],
            },
        )
        assert status == 200
        assert queued["queued"] is True
        workflow_id = queued["workflow"]["workflow_id"]
        assert queued["workflow"]["status"] == "queued"
        assert queued["execution"] is None

        deadline = time.monotonic() + 20
        latest = queued["workflow"]
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                raise AssertionError(f"worker process exited unexpectedly: {worker.returncode}")
            _, latest = _request(
                base_url,
                f"/agent/workflows/{workflow_id}",
                token=token,
            )
            if latest["status"] in {"succeeded", "failed", "cancelled", "recovery_required"}:
                break
            time.sleep(0.25)

        assert latest["status"] == "succeeded", (
            f"separate-process workflow did not succeed; final state: {latest!r}"
        )

        # Exercise the durable emergency-stop gate through the real API and worker
        # processes. Stop before queueing so this assertion is independent of polling
        # timing and proves that queued work is not claimed while the switch is latched.
        status, stopped = _request(
            base_url,
            "/jobs/emergency-stop",
            method="POST",
            token=token,
            body={"reason": "runtime smoke test maintenance window"},
        )
        assert status == 200
        assert stopped["stopped"] is True

        status, waiting = _request(
            base_url,
            "/agent/workflows",
            method="POST",
            token=token,
            body={
                "goal": "Remain queued while emergency stop is active",
                "tools": [{"name": "text.echo", "payload": {"text": "after-stop"}}],
            },
        )
        assert status == 200
        assert waiting["queued"] is True
        waiting_id = waiting["workflow"]["workflow_id"]
        assert waiting["workflow"]["status"] == "queued"

        # Allow several worker polling intervals; it must not dispatch this workflow.
        time.sleep(1.5)
        _, held = _request(
            base_url,
            f"/agent/workflows/{waiting_id}",
            token=token,
        )
        assert held["status"] == "queued"
        assert worker.poll() is None

        status, resumed = _request(
            base_url,
            "/jobs/resume",
            method="POST",
            token=token,
        )
        assert status == 200
        assert resumed["stopped"] is False

        deadline = time.monotonic() + 20
        latest = held
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                raise AssertionError(f"worker process exited after resume: {worker.returncode}")
            _, latest = _request(
                base_url,
                f"/agent/workflows/{waiting_id}",
                token=token,
            )
            if latest["status"] in {"succeeded", "failed", "cancelled", "recovery_required"}:
                break
            time.sleep(0.25)
        assert latest["status"] == "succeeded", (
            f"workflow did not resume after emergency stop was cleared: {latest!r}"
        )
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        if api.poll() is None:
            api.terminate()
            try:
                api.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait(timeout=5)
