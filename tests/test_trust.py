"""Trust boundaries and secret classification (SPEC 18.1)."""

import os

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_server_only_reads_on_the_server():
    db = ui.server_only("postgres://secret", label="DATABASE_URL")
    assert db.get() == "postgres://secret"
    assert "DATABASE_URL" in repr(db)


def test_secret_reads_environment():
    os.environ["VIREL_TEST_KEY"] = "sk-live-123"
    key = ui.secret("VIREL_TEST_KEY")
    assert key.get() == "sk-live-123"
    assert ui.secret("VIREL_MISSING", default="none").get() == "none"


def test_secret_in_a_handler_is_a_build_error():
    key = ui.server_only("sk-123", label="STRIPE_KEY")

    @ui.page("/h")
    def h():
        msg = ui.state("")

        def leak():
            msg.set(key)

        return ui.Page(ui.Button("go", on_click=leak))

    with pytest.raises(VirelCompileError, match="server-only"):
        compile_page(active_registry().pages["/h"])


def test_secret_in_reactive_text_is_a_build_error():
    key = ui.server_only("sk-123", label="STRIPE_KEY")

    @ui.page("/r")
    def r():
        return ui.Page(ui.Text(f"Key: {key}"))

    with pytest.raises(VirelCompileError):
        compile_page(active_registry().pages["/r"])


def test_secret_in_a_client_function_is_a_build_error():
    key = ui.server_only("sk-123", label="STRIPE_KEY")

    @ui.client
    def bad(x):
        return key

    with pytest.raises(VirelCompileError, match="server-only"):
        bad.js_definition()


def test_secret_in_a_worker_is_a_build_error():
    key = ui.server_only("sk-123", label="API_KEY")

    @ui.worker
    def bad(x):
        return key

    with pytest.raises(VirelCompileError, match="server-only"):
        bad.js_definition()


def test_server_action_may_read_a_secret_and_send_derived_data():
    key = ui.server_only("sk-live-abcdef", label="STRIPE_KEY")

    @ui.server
    async def masked() -> str:
        # Reads the secret on the server; only the masked prefix leaves.
        return key.get()[:3] + "***"

    @ui.page("/ok")
    def ok():
        result = ui.state("")
        return ui.Page(
            ui.Button("check", on_click=lambda: masked.call({},
                                                            into=result)),
            ui.Text(f"{result}"),
        )

    # Compiles cleanly: the secret never crosses the boundary.
    compiled = compile_page(active_registry().pages["/ok"])
    assert "sk-live" not in compiled.js
    assert "sk-live" not in compiled.html


def test_guards_may_read_secrets():
    token = ui.server_only("guard-token", label="SESSION_KEY")

    def guard(request: ui.Request):
        # Reading on the server side is fine.
        assert token.get() == "guard-token"
        return None

    @ui.page("/guarded", guard=guard)
    def guarded():
        return ui.Page(ui.Text("ok"))

    # The page itself references no secret, so it compiles.
    compile_page(active_registry().pages["/guarded"])
