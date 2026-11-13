"""Process-level MCP acceptance using the official Streamable HTTP client."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_listener(process: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f"MCP service exited before accepting connections (code {process.returncode})"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("MCP service did not bind its loopback listener in time")


def test_mcp_service_accepts_real_streamable_http_client_over_loopback(tmp_path):
    port = _free_loopback_port()
    environment = os.environ.copy()
    environment.update(
        {
            "MRH_MCP_ENABLED": "true",
            "MRH_MCP_HOST": "127.0.0.1",
            "MRH_MCP_PORT": str(port),
            "MRH_DATABASE_PATH": str(tmp_path / "mcp-acceptance.sqlite3"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "mrhub.mcp_service"],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_listener(process, port)

        async def exercise_host() -> None:
            async with (
                streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                assert {item.name for item in tools.tools} == {
                    "hub.list_tools",
                    "hub.invoke_tool",
                }
                result = await session.call_tool(
                    "hub.invoke_tool",
                    {
                        "name": "text.echo",
                        "payload": {"text": "loopback acceptance"},
                    },
                )
                assert not result.is_error
                response = json.loads(result.content[0].text)
                assert response == {
                    "ok": True,
                    "result": {
                        "text": "loopback acceptance",
                        "character_count": 19,
                    },
                }

        asyncio.run(exercise_host())
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)



def test_mcp_service_accepts_modern_2026_protocol_client_over_loopback(tmp_path):
    """The current SDK client must negotiate the stateless 2026-07-28 protocol."""
    from mcp import Client

    port = _free_loopback_port()
    environment = os.environ.copy()
    environment.update(
        {
            "MRH_MCP_ENABLED": "true",
            "MRH_MCP_HOST": "127.0.0.1",
            "MRH_MCP_PORT": str(port),
            "MRH_DATABASE_PATH": str(tmp_path / "mcp-modern-acceptance.sqlite3"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "mrhub.mcp_service"],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_listener(process, port)

        async def exercise_host() -> None:
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                assert client.protocol_version == "2026-07-28"
                tools = await client.list_tools()
                assert {item.name for item in tools.tools} == {
                    "hub.list_tools",
                    "hub.invoke_tool",
                }
                result = await client.call_tool(
                    "hub.invoke_tool",
                    {
                        "name": "text.echo",
                        "payload": {"text": "modern stateless acceptance"},
                    },
                )
                assert not result.is_error
                response = json.loads(result.content[0].text)
                assert response == {
                    "ok": True,
                    "result": {
                        "text": "modern stateless acceptance",
                        "character_count": 27,
                    },
                }

        asyncio.run(exercise_host())
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
