"""Observability: distributed tracing with an OpenTelemetry bridge
(SPEC 19).

Virel ships zero runtime dependencies, so the tracing core here is
self-contained: it propagates W3C trace context, measures span
durations, and records spans to an in-memory ring buffer that the dev
tools read. When the ``opentelemetry`` API is installed and telemetry is
enabled, every span is *also* emitted as a real OpenTelemetry span with
the same name, attributes, and parent — so the framework's own tracing
and an OTel backend see one consistent trace.

Correlation without leaking payloads: the server continues (or starts) a
trace per request, threads the trace id to the browser, and reads client
spans back through a beacon. Span attributes are scrubbed to scalar
metadata (names, sizes, durations, status) — request and response bodies
never become attributes.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

# --- configuration --------------------------------------------------------

@dataclass
class _Config:
    enabled: bool = False
    service_name: str = "virel-app"
    propagate: bool = True
    # Extra sinks a host installs. Each is called with a finished Span.
    sinks: list[Callable[["Span"], None]] = field(default_factory=list)
    # OpenTelemetry, when installed and enabled. Spans run *inline* as the
    # OTel current span so third-party library spans (e.g. database spans)
    # nest under them (SPEC 19).
    otel_mod: Any = None
    otel_tracer: Any = None
    otel_propagator: Any = None


_config = _Config()


def configure(*, enabled: bool = True, service_name: str = "virel-app",
              propagate: bool = True,
              exporter: Any = None) -> None:
    """Enable telemetry (SPEC 19). When the OpenTelemetry API is importable,
    spans are also emitted to OpenTelemetry as real spans that become the
    current context for their block, so spans from OTel-instrumented
    libraries nest under them; otherwise tracing still runs, feeding the
    in-memory buffer and the dev tools. ``exporter`` is an optional OTel
    SpanExporter to install on a fresh tracer provider."""
    _config.enabled = enabled
    _config.service_name = service_name
    _config.propagate = propagate
    _config.sinks = []
    _config.otel_mod = None
    _config.otel_tracer = None
    _config.otel_propagator = None
    if enabled:
        _install_otel(service_name, exporter)


def _install_otel(service_name: str, exporter: Any) -> None:
    """Wire up OpenTelemetry if present. Each capability is guarded
    independently so a partial or older install still degrades cleanly."""
    try:
        from opentelemetry import trace as otel_trace
    except Exception:
        return
    _config.otel_mod = otel_trace
    if exporter is not None:
        try:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider = TracerProvider(
                resource=Resource.create({"service.name": service_name}))
            provider.add_span_processor(BatchSpanProcessor(exporter))
            otel_trace.set_tracer_provider(provider)
        except Exception:
            pass
    try:
        _config.otel_tracer = otel_trace.get_tracer("virel", "1")
    except Exception:
        _config.otel_tracer = None
    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator)
        _config.otel_propagator = TraceContextTextMapPropagator()
    except Exception:
        _config.otel_propagator = None


def is_enabled() -> bool:
    return _config.enabled


def reset() -> None:
    """Test helper: return telemetry to its default (disabled) state."""
    _config.enabled = False
    _config.service_name = "virel-app"
    _config.propagate = True
    _config.sinks = []
    _config.otel_mod = None
    _config.otel_tracer = None
    _config.otel_propagator = None
    _recent.clear()


# --- W3C trace context ----------------------------------------------------

@dataclass(frozen=True)
class TraceContext:
    """A W3C trace context: a 32-hex trace id, a 16-hex span id (the
    current parent for children), and a sampled flag."""

    trace_id: str
    span_id: str
    sampled: bool = True

    def traceparent(self) -> str:
        flags = "01" if self.sampled else "00"
        return f"00-{self.trace_id}-{self.span_id}-{flags}"

    def child(self, span_id: str) -> "TraceContext":
        return TraceContext(self.trace_id, span_id, self.sampled)


def _rand_hex(nbytes: int) -> str:
    return os.urandom(nbytes).hex()


def new_trace_id() -> str:
    return _rand_hex(16)


def new_span_id() -> str:
    return _rand_hex(8)


def parse_traceparent(value: str | None) -> TraceContext | None:
    """Parse a W3C ``traceparent`` header. Returns ``None`` for anything
    malformed so a bad header can never crash a request."""
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, flags = parts
    if version != "00" or len(trace_id) != 32 or len(span_id) != 16:
        return None
    if not _is_hex(trace_id) or not _is_hex(span_id):
        return None
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    try:
        sampled = bool(int(flags, 16) & 0x01)
    except ValueError:
        return None
    return TraceContext(trace_id, span_id, sampled)


def _is_hex(text: str) -> bool:
    try:
        int(text, 16)
        return True
    except ValueError:
        return False


# --- the current trace ----------------------------------------------------

_current: contextvars.ContextVar[TraceContext | None] = \
    contextvars.ContextVar("virel_trace", default=None)


def current_trace() -> TraceContext | None:
    return _current.get()


def current_traceparent() -> str | None:
    ctx = _current.get()
    return ctx.traceparent() if ctx else None


def start_trace(traceparent: str | None) -> tuple[TraceContext, Any]:
    """Continue an incoming trace or start a new one. Returns the context
    and an opaque token to pass to :func:`end_trace`. When OpenTelemetry is
    active, the incoming trace is also seeded into the OTel context so OTel
    spans continue the browser's trace and share its id."""
    incoming = parse_traceparent(traceparent)
    if incoming is not None:
        ctx = incoming
    else:
        ctx = TraceContext(new_trace_id(), new_span_id(), True)
    token = _current.set(ctx)
    otel_token = None
    if _config.otel_propagator is not None and traceparent:
        try:
            from opentelemetry.context import attach
            otel_ctx = _config.otel_propagator.extract(
                {"traceparent": traceparent})
            otel_token = attach(otel_ctx)
        except Exception:
            otel_token = None
    return ctx, (token, otel_token)


def end_trace(token: Any) -> None:
    my_token, otel_token = token if isinstance(token, tuple) else (token, None)
    _current.reset(my_token)
    if otel_token is not None:
        try:
            from opentelemetry.context import detach
            detach(otel_token)
        except Exception:
            pass


# --- spans ----------------------------------------------------------------

# Attribute keys that must never carry a value, and a size cap on strings,
# so a payload can't sneak into a span as an attribute (SPEC 19: no
# sensitive payloads).
_BLOCKED_KEYS = frozenset({"body", "payload", "args", "result", "data",
                           "password", "token", "secret", "cookie",
                           "authorization"})
_MAX_ATTR_STR = 256


def _scrub(attributes: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        # Match the last dotted segment so "virel.password" is blocked too.
        if key.rsplit(".", 1)[-1].lower() in _BLOCKED_KEYS:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            clean[key] = value[:_MAX_ATTR_STR]
        else:
            # Dicts, lists, and objects are payload-shaped: record only
            # that something was present, never its contents.
            clean[key] = f"<{type(value).__name__}>"
    return clean


@dataclass
class Span:
    """A finished or in-progress span. Durations are milliseconds."""

    name: str
    kind: str = "internal"
    trace_id: str = ""
    span_id: str = ""
    parent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    status: str = "ok"
    duration_ms: float = 0.0
    _start: float = 0.0

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes.update(_scrub({key: value}))

    def add_event(self, name: str, **attributes: Any) -> None:
        self.events.append((name, _scrub(attributes)))

    def record_exception(self, exc: BaseException) -> None:
        self.status = "error"
        self.add_event("exception", type=type(exc).__name__)


# Recent finished spans for the dev tools / inspector (SPEC 19 dev tools).
_recent: deque[Span] = deque(maxlen=256)


def recent_spans(limit: int | None = None) -> list[Span]:
    spans = list(_recent)
    if limit is not None:
        spans = spans[-limit:]
    return spans


@contextlib.contextmanager
def span(name: str, *, kind: str = "internal",
         **attributes: Any) -> Iterator[Span]:
    """Record a span around a block. Cheap and always safe to call: when
    telemetry is disabled it still measures duration and buffers the span
    for the dev tools. When OpenTelemetry is active the block also runs as
    the OTel current span, so spans from OTel-instrumented libraries (for
    example database spans) nest under it. Parent/trace ids come from the
    current trace context."""
    parent = _current.get()
    span_id = new_span_id()
    record = Span(
        name=name,
        kind=kind,
        trace_id=parent.trace_id if parent else new_trace_id(),
        span_id=span_id,
        parent_id=parent.span_id if parent else None,
        attributes=_scrub(attributes),
    )
    record._start = time.perf_counter()
    # Children of this span see it as their parent.
    child_ctx = (parent.child(span_id) if parent
                 else TraceContext(record.trace_id, span_id, True))
    token = _current.set(child_ctx)
    otel_cm, otel_span = _otel_span_begin(name, kind)
    exc_info: tuple[Any, Any, Any] = (None, None, None)
    try:
        yield record
    except BaseException as exc:  # noqa: BLE001 - re-raised below
        record.record_exception(exc)
        exc_info = (type(exc), exc, exc.__traceback__)
        raise
    finally:
        record.duration_ms = (time.perf_counter() - record._start) * 1000.0
        _current.reset(token)
        _otel_span_end(otel_cm, otel_span, record, exc_info)
        _emit(record)


def _emit(record: Span) -> None:
    _recent.append(record)
    for sink in _config.sinks:
        try:
            sink(record)
        except Exception:
            # A telemetry backend failure must never break a request.
            pass


# --- OpenTelemetry inline bridge ------------------------------------------

def _otel_span_begin(name: str, kind: str) -> tuple[Any, Any]:
    """Start an OTel span as the current context, or ``(None, None)``."""
    tracer = _config.otel_tracer
    if tracer is None:
        return None, None
    try:
        otel_cm = tracer.start_as_current_span(name, kind=_otel_kind(kind))
        return otel_cm, otel_cm.__enter__()
    except Exception:
        return None, None


def _otel_span_end(otel_cm: Any, otel_span: Any, record: "Span",
                   exc_info: tuple[Any, Any, Any]) -> None:
    if otel_span is not None:
        try:
            for key, value in record.attributes.items():
                otel_span.set_attribute(
                    key if "." in key else f"virel.{key}", value)
            otel_span.set_attribute("virel.duration_ms", record.duration_ms)
            for event_name, event_attrs in record.events:
                otel_span.add_event(event_name, attributes=event_attrs)
            if record.status == "error":
                from opentelemetry.trace import Status, StatusCode
                otel_span.set_status(Status(StatusCode.ERROR))
        except Exception:
            pass
    if otel_cm is not None:
        try:
            otel_cm.__exit__(*exc_info)
        except Exception:
            pass


def _otel_kind(kind: str) -> Any:
    from opentelemetry.trace import SpanKind
    return {
        "server": SpanKind.SERVER,
        "client": SpanKind.CLIENT,
        "producer": SpanKind.PRODUCER,
        "consumer": SpanKind.CONSUMER,
        "internal": SpanKind.INTERNAL,
    }.get(kind, SpanKind.INTERNAL)
