"""
In-process runtime metrics for the AI/ML tier.

Deliberately tiny and dependency-free: the admin panel needs to answer
"is the model healthy, which tier is serving replies, how often do we fall
back to data-only answers, and how slow is it?" without pulling in
Prometheus. Counters reset when the backend restarts, so the panel labels
them "since start" rather than pretending they are lifetime totals.
"""
import threading
from collections import deque

# Bounded latency window: enough for a stable average without unbounded growth.
_LATENCY_WINDOW = 200


class AIMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests = 0
        self._fallbacks = 0
        self._by_provider: dict[str, int] = {}
        self._by_role: dict[str, int] = {}
        self._latencies: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._last_error: str | None = None
        self._last_error_kind: str | None = None

    def record_reply(self, *, provider: str, fallback_used: bool, role: str, latency_ms: float) -> None:
        with self._lock:
            self._requests += 1
            if fallback_used:
                self._fallbacks += 1
            name = provider or "unknown"
            self._by_provider[name] = self._by_provider.get(name, 0) + 1
            self._by_role[role or "unknown"] = self._by_role.get(role or "unknown", 0) + 1
            self._latencies.append(float(latency_ms))

    def record_error(self, *, kind: str, detail: str | None = None) -> None:
        with self._lock:
            self._last_error_kind = kind
            self._last_error = detail

    def snapshot(self) -> dict:
        with self._lock:
            requests = self._requests
            fallbacks = self._fallbacks
            by_provider = dict(self._by_provider)
            by_role = dict(self._by_role)
            latencies = list(self._latencies)
            last_error = self._last_error
            last_error_kind = self._last_error_kind

        avg = round(sum(latencies) / len(latencies), 1) if latencies else None
        p95 = None
        if latencies:
            ordered = sorted(latencies)
            index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
            p95 = round(ordered[index], 1)

        most_common = max(by_provider.items(), key=lambda kv: kv[1])[0] if by_provider else None
        return {
            "requests": requests,
            "fallbacks": fallbacks,
            "fallback_rate_pct": round((fallbacks / requests) * 100, 1) if requests else 0.0,
            "by_provider": by_provider,
            "by_role": by_role,
            "served_mostly_by": most_common,
            "latency_avg_ms": avg,
            "latency_p95_ms": p95,
            "latency_samples": len(latencies),
            "last_error_kind": last_error_kind,
            "last_error": last_error,
        }

    def reset(self) -> None:
        with self._lock:
            self._requests = 0
            self._fallbacks = 0
            self._by_provider.clear()
            self._by_role.clear()
            self._latencies.clear()
            self._last_error = None
            self._last_error_kind = None


_metrics = AIMetrics()


def get_metrics() -> AIMetrics:
    """Process-wide singleton (one uvicorn worker per container)."""
    return _metrics
