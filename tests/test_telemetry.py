"""Observability: tracing core, trace-context propagation, and the
OpenTelemetry bridge (SPEC 19)."""

import sys
import types

import pytest

from virel import telemetry, ui
from virel.server import create_asgi_app
from virel.telemetry import (TraceContext, current_trace, parse_traceparent,
                             recent_spans, span)

from conftest import asgi_request


# --- W3C trace context ----------------------------------------------------

def test_traceparent_roundtrip():
    ctx = TraceContext("0af7651916cd43dd8448eb211c80319c",
                       "b7ad6b7169203331", True)
    header = ctx.traceparent()
    assert header == ("00-0af7651916cd43dd8448eb211c80319c-"
                      "b7ad6b7169203331-01")
    assert parse_traceparent(header) == ctx


def test_parse_traceparent_rejects_malformed():
    assert parse_traceparent(None) is None
    assert parse_traceparent("") is None
    assert parse_traceparent("garbage") is None
    assert parse_traceparent("00-tooshort-b7ad6b7169203331-01") is None
    assert parse_traceparent("99-" + "a" * 32 + "-" + "b" * 16 + "-01") is None
    # all-zero ids are invalid
    assert parse_traceparent("00-" + "0" * 32 + "-" + "b" * 16 + "-01") is None


def test_parse_traceparent_unsampled():
    ctx = parse_traceparent("00-" + "a" * 32 + "-" + "b" * 16 + "-00")
    assert ctx is not None and ctx.sampled is False


def test_start_trace_continues_incoming():
    header = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    ctx, token = telemetry.start_trace(header)
    try:
        assert ctx.trace_id == "a" * 32
        assert current_trace().trace_id == "a" * 32
    finally:
        telemetry.end_trace(token)
    assert current_trace() is None


def test_start_trace_generates_when_absent():
    ctx, token = telemetry.start_trace(None)
    try:
        assert len(ctx.trace_id) == 32
        assert len(ctx.span_id) == 16
    finally:
        telemetry.end_trace(token)


# --- spans ----------------------------------------------------------------

def test_span_records_duration_and_buffers():
    with span("unit.work", kind="internal", **{"virel.detail": "x"}) as sp:
        pass
    assert sp.duration_ms >= 0.0
    assert sp in recent_spans()
    assert sp.attributes["virel.detail"] == "x"


def test_span_parent_child_linkage():
    with span("parent") as parent:
        with span("child") as child:
            assert child.parent_id == parent.span_id
            assert child.trace_id == parent.trace_id


def test_span_records_exception_status():
    with pytest.raises(ValueError):
        with span("boom") as sp:
            raise ValueError("nope")
    assert sp.status == "error"
    assert any(name == "exception" for name, _ in sp.events)


def test_span_scrubs_sensitive_attributes():
    with span("login", **{"password": "hunter2", "body": {"a": 1},
                          "virel.action": "login", "count": 3}) as sp:
        pass
    assert "password" not in sp.attributes
    assert "body" not in sp.attributes
    assert sp.attributes["virel.action"] == "login"
    assert sp.attributes["count"] == 3


# --- configuration --------------------------------------------------------

def test_disabled_by_default():
    telemetry.reset()
    assert telemetry.is_enabled() is False
    assert telemetry._config.sinks == []


def test_configure_without_otel_has_no_sink():
    # OpenTelemetry is not a dependency; enabling without it still works.
    telemetry.configure(enabled=True, service_name="svc")
    assert telemetry.is_enabled()
    assert telemetry._config.sinks == []


def test_custom_sink_receives_finished_spans():
    telemetry.reset()
    captured = []
    telemetry._config.sinks.append(captured.append)
    with span("sunk", **{"virel.n": 1}):
        pass
    assert captured and captured[-1].name == "sunk"
    telemetry.reset()


# --- OpenTelemetry bridge (via a stub module) -----------------------------

def _install_fake_otel(monkeypatch):
    """A minimal fake opentelemetry.trace so the inline bridge can be
    exercised without the real package installed. Spans are context
    managers (start_as_current_span), which is what lets library spans
    nest under Virel spans."""
    recorded = []

    class FakeSpan:
        def __init__(self, name, kind):
            self.name = name
            self.kind = kind
            self.attributes = {}
            self.events = []
            self.status = None
            self.exited = False

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def add_event(self, name, attributes=None):
            self.events.append((name, attributes or {}))

        def set_status(self, status):
            self.status = status

    class FakeSpanCM:
        def __init__(self, span):
            self.span = span

        def __enter__(self):
            return self.span

        def __exit__(self, *exc):
            self.span.exited = True
            return False

    class FakeTracer:
        def start_as_current_span(self, name, kind=None):
            s = FakeSpan(name, kind)
            recorded.append(s)
            return FakeSpanCM(s)

    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.SpanKind = types.SimpleNamespace(
        SERVER="server", CLIENT="client", PRODUCER="producer",
        CONSUMER="consumer", INTERNAL="internal")
    trace_mod.Status = lambda code: ("status", code)
    trace_mod.StatusCode = types.SimpleNamespace(ERROR="error")
    trace_mod.get_tracer = lambda *a, **k: FakeTracer()
    trace_mod.set_tracer_provider = lambda p: None

    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = trace_mod

    monkeypatch.setitem(sys.modules, "opentelemetry", otel_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_mod)
    return recorded


def test_otel_span_runs_inline_for_nesting(monkeypatch):
    recorded = _install_fake_otel(monkeypatch)
    telemetry.reset()
    telemetry.configure(enabled=True, service_name="svc")
    assert telemetry._config.otel_tracer is not None
    with span("action echo", kind="server", **{"virel.action": "echo"}):
        # Inside the block the OTel span is open (current context), so a
        # library span created here would nest under it.
        assert recorded and recorded[-1].exited is False
    otel_span = recorded[-1]
    assert otel_span.name == "action echo"
    assert otel_span.kind == "server"
    assert otel_span.attributes["virel.action"] == "echo"
    assert "virel.duration_ms" in otel_span.attributes
    assert otel_span.exited, "the OTel span must be closed after the block"
    telemetry.reset()


def test_otel_span_marks_errors(monkeypatch):
    recorded = _install_fake_otel(monkeypatch)
    telemetry.reset()
    telemetry.configure(enabled=True)
    with pytest.raises(RuntimeError):
        with span("boom", kind="server"):
            raise RuntimeError("x")
    assert recorded[-1].status is not None
    assert recorded[-1].exited
    telemetry.reset()


# --- server integration ---------------------------------------------------

def _traced_app():
    ui.use_telemetry(service_name="demo")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hi"))

    @ui.server
    def echo(value: str) -> str:
        return value

    return create_asgi_app(dev=True)


def _action(app, name, body, tp=None):
    headers = [(b"content-type", b"application/json"),
               (b"origin", b"http://testserver"), (b"host", b"testserver")]
    if tp:
        headers.append((b"traceparent", tp.encode()))
    return asgi_request(app, "POST", f"/_virel/action/{name}", body=body,
                        headers=headers)


def test_action_response_carries_trace_and_timing():
    app = _traced_app()
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    r = _action(app, "echo", b'{"value":"x"}', tp=tp)
    assert r.status == 200
    # request id equals the trace id (correlation)
    assert r.headers["x-request-id"] == "0af7651916cd43dd8448eb211c80319c"
    assert r.headers["traceparent"].startswith(
        "00-0af7651916cd43dd8448eb211c80319c-")
    timing = r.headers["server-timing"]
    assert "action;dur=" in timing and "serialize;dur=" in timing


def test_action_span_inherits_incoming_trace():
    app = _traced_app()
    tp = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"
    _action(app, "echo", b'{"value":"y"}', tp=tp)
    action_spans = [s for s in recent_spans() if s.name == "action echo"]
    assert action_spans and action_spans[-1].trace_id == "c" * 32


def test_page_render_emits_render_span():
    app = _traced_app()
    asgi_request(app, "GET", "/")
    render = [s for s in recent_spans() if s.name == "server.render"]
    assert render
    assert "virel.render_mode" in render[-1].attributes


def test_no_traceparent_still_gets_request_id():
    app = _traced_app()
    r = _action(app, "echo", b'{"value":"z"}')
    assert len(r.headers["x-request-id"]) == 32


def test_page_injects_telemetry_meta_when_enabled():
    app = _traced_app()
    r = asgi_request(app, "GET", "/")
    assert '<meta name="virel-telemetry" content="on">' in r.text


def test_page_omits_meta_when_disabled():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hi"))

    app = create_asgi_app(dev=False)  # telemetry not enabled
    r = asgi_request(app, "GET", "/")
    assert "virel-telemetry" not in r.text


# --- client beacon --------------------------------------------------------

def _beacon(app, payload, tp=None):
    headers = [(b"content-type", b"application/json")]
    if tp:
        headers.append((b"traceparent", tp.encode()))
    return asgi_request(app, "POST", "/_virel/telemetry", body=payload,
                        headers=headers)


def test_beacon_records_client_span_and_correlates():
    app = _traced_app()
    tp = "00-" + "e" * 32 + "-" + "f" * 16 + "-01"
    r = _beacon(app, b'{"kind":"vitals","lcp":1200,"cls":0.02}', tp=tp)
    assert r.status == 204
    spans = [s for s in recent_spans() if s.name == "client.vitals"]
    assert spans
    assert spans[-1].trace_id == "e" * 32
    assert spans[-1].attributes["virel.lcp"] == 1200


def test_beacon_scrubs_sensitive_fields():
    app = _traced_app()
    _beacon(app, b'{"kind":"error","message":"x","password":"secret"}')
    spans = [s for s in recent_spans() if s.name == "client.error"]
    assert spans and spans[-1].status == "error"
    assert "virel.password" not in spans[-1].attributes


def test_beacon_rejects_get():
    app = _traced_app()
    r = asgi_request(app, "GET", "/_virel/telemetry")
    assert r.status == 405


def test_beacon_accepts_and_discards_when_disabled():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hi"))

    app = create_asgi_app(dev=False)
    before = len(recent_spans())
    r = _beacon(app, b'{"kind":"vitals","lcp":1}')
    assert r.status == 204
    assert len(recent_spans()) == before  # nothing recorded
