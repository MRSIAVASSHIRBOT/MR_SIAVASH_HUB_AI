"""Bounded, process-local HTTP request metrics for the authenticated operator API."""

from __future__ import annotations

import math
from threading import Lock
from typing import Any

METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000)
MAX_ROUTE_TEMPLATE_CHARS = 160


class RequestMetrics:
    """Maintain bounded counters and latency buckets without request-specific data."""

    def __init__(self, *, max_series: int = 256) -> None:
        if isinstance(max_series, bool) or not isinstance(max_series, int) or max_series < 1:
            raise ValueError("max_series must be a positive integer")
        self._max_series = max_series
        self._lock = Lock()
        self._series: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._overflow_key = ("OTHER", "other", "other")

    @staticmethod
    def _dimensions(
        method: str, route_template: str, status_code: int
    ) -> tuple[str, str, str]:
        """Accept only bounded method, registered route-template, and status dimensions."""
        safe_method = method.upper() if isinstance(method, str) else ""
        if safe_method not in METHODS:
            safe_method = "OTHER"

        safe_route = (
            route_template
            if isinstance(route_template, str)
            and route_template.startswith("/")
            and len(route_template) <= MAX_ROUTE_TEMPLATE_CHARS
            and "?" not in route_template
            and "#" not in route_template
            else "unmatched"
        )
        status_class = (
            f"{status_code // 100}xx"
            if isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and 100 <= status_code <= 599
            else "other"
        )
        return safe_method, safe_route, status_class

    @staticmethod
    def _new_series() -> dict[str, Any]:
        return {
            "count": 0,
            "duration_sum_ms": 0.0,
            "bucket_counts": [0 for _ in BUCKETS_MS],
        }

    def record(
        self, method: str, route_template: str, status_code: int, duration_ms: float
    ) -> None:
        """Record one completed request using route templates, never raw URLs or identities."""
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not math.isfinite(duration_ms)
        ):
            return
        duration = max(0.0, float(duration_ms))
        key = self._dimensions(method, route_template, status_code)
        with self._lock:
            if key not in self._series:
                if len(self._series) >= self._max_series:
                    key = self._overflow_key
                self._series.setdefault(key, self._new_series())
            metric = self._series[key]
            metric["count"] += 1
            metric["duration_sum_ms"] = round(
                metric["duration_sum_ms"] + duration, 3
            )
            for index, upper_bound in enumerate(BUCKETS_MS):
                if duration <= upper_bound:
                    metric["bucket_counts"][index] += 1

    def snapshot(self) -> dict[str, object]:
        """Return a bounded cumulative snapshot for this process since startup."""
        with self._lock:
            series = [
                {
                    "method": method,
                    "route_template": route,
                    "status_class": status_class,
                    "count": metric["count"],
                    "duration_sum_ms": metric["duration_sum_ms"],
                    "bucket_counts": list(metric["bucket_counts"]),
                }
                for (method, route, status_class), metric in sorted(self._series.items())
            ]
        return {
            "scope": "single_process",
            "temporality": "cumulative_since_process_start",
            "series_limit": self._max_series,
            "bucket_upper_bounds_ms": list(BUCKETS_MS),
            "series": series,
        }
