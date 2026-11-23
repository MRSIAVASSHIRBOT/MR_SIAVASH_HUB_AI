"""Validated retry policy primitives for safe, idempotent worker tasks."""

from dataclasses import dataclass


MAX_RETRY_ATTEMPTS = 10
MAX_RETRY_DELAY_SECONDS = 86_400


def validate_retry_error_code(value: str) -> str:
    """Validate a bounded, non-sensitive identifier used for retry classification."""
    valid = (
        isinstance(value, str)
        and 1 <= len(value) <= 80
        and "a" <= value[0] <= "z"
        and all(
            "a" <= char <= "z" or "0" <= char <= "9" or char == "_"
            for char in value
        )
    )
    if not valid:
        raise ValueError("Retry error code must be a lowercase ASCII identifier")
    return value


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff and allow-list of retryable error classes."""

    max_attempts: int = 3
    base_delay_seconds: int = 5
    max_delay_seconds: int = 60
    retryable_error_codes: frozenset[str] = frozenset(
        {
            "transient_worker_error",
            "upstream_timeout",
            "rate_limited",
            "service_unavailable",
        }
    )

    def __post_init__(self) -> None:
        bounds = (
            ("max_attempts", self.max_attempts, MAX_RETRY_ATTEMPTS),
            ("base_delay_seconds", self.base_delay_seconds, MAX_RETRY_DELAY_SECONDS),
            ("max_delay_seconds", self.max_delay_seconds, MAX_RETRY_DELAY_SECONDS),
        )
        for name, value, upper_bound in bounds:
            if type(value) is not int or not 1 <= value <= upper_bound:
                raise ValueError(
                    f"{name} must be an integer between 1 and {upper_bound}"
                )
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds cannot be below base_delay_seconds")
        if not isinstance(self.retryable_error_codes, frozenset):
            raise TypeError("retryable_error_codes must be an immutable frozenset")
        if not self.retryable_error_codes:
            raise ValueError("At least one retryable error code must be declared")
        for error_code in self.retryable_error_codes:
            validate_retry_error_code(error_code)

    def delay_seconds(
        self,
        *,
        attempt_number: int,
        retry_after_seconds: int | None = None,
    ) -> int:
        """Return bounded exponential backoff, honoring a bounded Retry-After hint."""
        if type(attempt_number) is not int or attempt_number < 1:
            raise ValueError("attempt_number must be a positive integer")
        exponent = min(attempt_number - 1, 30)
        backoff = min(
            self.base_delay_seconds * (2**exponent),
            self.max_delay_seconds,
        )
        if retry_after_seconds is None:
            return backoff
        if (
            type(retry_after_seconds) is not int
            or retry_after_seconds < 0
            or retry_after_seconds > 86_400
        ):
            raise ValueError("Retry-After must be an integer between 0 and 86400")
        return min(max(backoff, retry_after_seconds), self.max_delay_seconds)
