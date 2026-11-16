"""Loopback-only OpenRouter credential broker for scheduled OpenCode runs.

The provider credential is held by this trusted process only. OpenCode receives a
non-secret local broker token and can reach only the two required OpenRouter API
routes through a loopback listener. No request headers, bodies, or credentials are
written to logs.
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DEFAULT_PORT = 8765
BROKER_TOKEN = "mrhub-local-broker"
UPSTREAM_HOST = "openrouter.ai"
ALLOWED_MODEL_ID = "cohere/north-mini-code:free"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 90
_ALLOWED_ROUTES = {
    ("GET", "/api/v1/models"),
    ("POST", "/api/v1/chat/completions"),
}
_ALLOWED_ACCEPT = {"application/json", "text/event-stream", "*/*"}


def validate_request(
    method: str,
    target: str,
    authorization: str | None,
    content_length: str | None,
    content_type: str | None,
) -> tuple[int, str | None]:
    """Return an HTTP rejection status, or 200 for an allowed request."""
    if authorization != f"Bearer {BROKER_TOKEN}":
        return 401, "broker_auth_required"

    parsed = urlsplit(target)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path != target
    ):
        return 404, "route_not_found"

    if (method, parsed.path) not in _ALLOWED_ROUTES:
        if any(path == parsed.path for _, path in _ALLOWED_ROUTES):
            return 405, "method_not_allowed"
        return 404, "route_not_found"

    if method == "POST":
        if content_type is None or content_type.split(";", 1)[0].strip().lower() != "application/json":
            return 415, "json_required"
        if content_length is None or not content_length.isascii() or not content_length.isdecimal():
            return 411, "content_length_required"
        if len(content_length) > 10 or int(content_length) > MAX_REQUEST_BYTES:
            return 413, "request_too_large"

    return 200, None


def build_upstream_headers(
    api_key: str,
    *,
    accept: str | None,
    has_body: bool,
) -> dict[str, str]:
    """Construct minimal upstream headers; never forward caller credentials."""
    if not api_key or not api_key.strip():
        raise ValueError("OpenRouter credential is unavailable")
    normalized_accept = (accept or "").split(";", 1)[0].strip().lower()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": normalized_accept if normalized_accept in _ALLOWED_ACCEPT else "application/json",
        "User-Agent": "mrhub-opencode-credential-broker/1",
    }
    if has_body:
        headers["Content-Type"] = "application/json"
    return headers


def open_upstream_request(
    method: str,
    path: str,
    body: bytes | None,
    api_key: str,
    *,
    accept: str | None,
    connection_factory=None,
):
    """Open one fixed-host HTTPS request without redirects or caller-controlled headers."""
    factory = connection_factory or http.client.HTTPSConnection
    connection = factory(
        UPSTREAM_HOST,
        timeout=UPSTREAM_TIMEOUT_SECONDS,
        context=ssl.create_default_context(),
    )
    headers = build_upstream_headers(api_key, accept=accept, has_body=body is not None)
    try:
        connection.request(method, path, body=body, headers=headers)
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


class BrokerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, api_key: str, connection_factory=None):
        self.api_key = api_key
        self.connection_factory = connection_factory
        super().__init__(address, handler)


class BrokerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: BrokerHTTPServer

    def do_GET(self) -> None:
        self._handle_proxy("GET")

    def do_POST(self) -> None:
        self._handle_proxy("POST")

    def _send_json_error(self, status: int, code: str) -> None:
        payload = json.dumps({"error": {"code": code}}, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def _handle_proxy(self, method: str) -> None:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._send_json_error(403, "loopback_only")
            return

        content_length = self.headers.get("Content-Length")
        rejection, code = validate_request(
            method,
            self.path,
            self.headers.get("Authorization"),
            content_length,
            self.headers.get("Content-Type"),
        )
        if rejection != 200:
            self._send_json_error(rejection, code or "request_rejected")
            return

        body = None
        if method == "POST":
            try:
                length = int(content_length or "0")
                body = self.rfile.read(length)
                request_payload = json.loads(body)
                if len(body) != length or not isinstance(request_payload, dict):
                    raise ValueError("invalid JSON request")
                if request_payload.get("model") != ALLOWED_MODEL_ID:
                    self._send_json_error(403, "model_not_allowed")
                    return
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
                self._send_json_error(400, "invalid_json_request")
                return

        try:
            connection, upstream = open_upstream_request(
                method,
                self.path,
                body,
                self.server.api_key,
                accept=self.headers.get("Accept"),
                connection_factory=self.server.connection_factory,
            )
        except (OSError, http.client.HTTPException, ValueError):
            self._send_json_error(502, "upstream_unavailable")
            return

        try:
            status = int(upstream.status)
            if 300 <= status < 400:
                self._send_json_error(502, "upstream_redirect_rejected")
                return
            response_length = upstream.getheader("Content-Length")
            if (
                response_length
                and response_length.isdecimal()
                and int(response_length) > MAX_RESPONSE_BYTES
            ):
                self._send_json_error(502, "upstream_response_too_large")
                return

            self.send_response(status)
            content_type = upstream.getheader("Content-Type")
            if (
                content_type
                and len(content_type) <= 120
                and "\r" not in content_type
                and "\n" not in content_type
            ):
                self.send_header("Content-Type", content_type)
            retry_after = upstream.getheader("Retry-After")
            if retry_after and retry_after.isdecimal() and int(retry_after) <= 3600:
                self.send_header("Retry-After", retry_after)
            request_id = upstream.getheader("X-Request-Id")
            if request_id and len(request_id) <= 128 and request_id.isascii() and all(
                character.isalnum() or character in "-_" for character in request_id
            ):
                self.send_header("X-Request-Id", request_id)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            total = 0
            while True:
                chunk = upstream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError, http.client.HTTPException):
            # The client disconnected or the upstream stream failed. Never log payloads.
            pass
        finally:
            connection.close()
            self.close_connection = True

    def log_message(self, _format: str, *_args) -> None:
        """Suppress access logs so request metadata and model content are not retained."""


def create_server(api_key: str, *, port: int = DEFAULT_PORT, connection_factory=None):
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("OPENROUTER_API_KEY is required")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Broker port is invalid")
    return BrokerHTTPServer(
        ("127.0.0.1", port),
        BrokerHandler,
        api_key=api_key,
        connection_factory=connection_factory,
    )


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key.strip():
        print("OpenRouter credential is missing; broker was not started.", file=sys.stderr)
        return 2
    try:
        server = create_server(api_key)
    except (OSError, ValueError):
        print("OpenRouter credential broker could not start.", file=sys.stderr)
        return 2
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
