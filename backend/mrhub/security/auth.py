"""Local-first password authentication and opaque expiring sessions."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from mrhub.infrastructure.database import TaskRepository

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    username: str


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )


class AuthService:
    """Single-owner local authentication with hashed session tokens."""

    def __init__(self, repository: TaskRepository, session_ttl_hours: int = 12) -> None:
        self.repository = repository
        self.session_ttl_hours = session_ttl_hours

    def initialize_owner(self, password: str) -> None:
        if len(password) < 14:
            raise ValueError("Bootstrap password must contain at least 14 characters")
        if self.repository.auth_user_exists():
            return
        salt = secrets.token_bytes(16)
        digest = _password_digest(password, salt)
        self.repository.create_auth_user(
            "local-owner",
            "owner",
            salt.hex(),
            digest.hex(),
        )

    def login(self, username: str, password: str) -> tuple[str, AuthenticatedUser] | None:
        record = self.repository.get_auth_user(username)
        if record is None:
            # Perform a comparable KDF for unknown users to reduce timing leakage.
            _password_digest(password, b"\x00" * 16)
            return None
        candidate = _password_digest(password, bytes.fromhex(record["salt"]))
        if not hmac.compare_digest(candidate.hex(), record["password_hash"]):
            return None

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(hours=self.session_ttl_hours)
        self.repository.create_auth_session(
            str(uuid4()),
            record["user_id"],
            token_hash,
            expires_at.isoformat(),
        )
        user = AuthenticatedUser(user_id=record["user_id"], username=record["username"])
        return raw_token, user

    def authenticate(self, raw_token: str) -> AuthenticatedUser | None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        record = self.repository.get_auth_session(token_hash)
        if record is None:
            return None
        if datetime.fromisoformat(record["expires_at"]) <= datetime.now(UTC):
            self.repository.delete_auth_session(token_hash)
            return None
        return AuthenticatedUser(user_id=record["user_id"], username=record["username"])

    def logout(self, raw_token: str) -> None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.repository.delete_auth_session(token_hash)



class LoginAttemptLimiter:
    """Bound repeated failed logins per client address in this single-process app."""

    MAX_TRACKED_CLIENTS = 1024

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        if max_attempts < 1 or window_seconds < 1:
            raise ValueError("Login limiter bounds must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, failures: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()

    def retry_after(self, client_key: str) -> int:
        now = time.monotonic()
        with self._lock:
            failures = self._failures.get(client_key)
            if failures is None:
                return 0
            self._prune(failures, now)
            if not failures:
                self._failures.pop(client_key, None)
                return 0
            if len(failures) < self.max_attempts:
                return 0
            return max(1, int(self.window_seconds - (now - failures[0]) + 0.999))

    def record_failure(self, client_key: str) -> None:
        now = time.monotonic()
        with self._lock:
            failures = self._failures.get(client_key)
            if failures is None:
                if len(self._failures) >= self.MAX_TRACKED_CLIENTS:
                    oldest_key = next(iter(self._failures))
                    self._failures.pop(oldest_key, None)
                failures = deque()
                self._failures[client_key] = failures
            self._prune(failures, now)
            failures.append(now)

    def reset(self, client_key: str) -> None:
        with self._lock:
            self._failures.pop(client_key, None)
