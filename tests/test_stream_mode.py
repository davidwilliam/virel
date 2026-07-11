"""Progressive rendering: render="stream" (SPEC 9.6)."""

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def _slow_data():
    @ui.server
    async def slow_report() -> list[dict]:
        return [{"name": "atlas", "score": 0.9}]
    return slow_report


def test_stream_page_compiles_with_deferred_resources():
    action = _slow_data()

    @ui.page("/report", render="stream")
    def report():
        data = ui.resource(action, server_render=True)
        return ui.Page(ui.Suspense(
            data,
            content=ui.Each(data.value,
                            render=lambda item: ui.Text(item.name)),
            fallback=ui.Skeleton(),
        ))

    result = compile_page(active_registry().pages["/report"])
    assert result.render_mode == "stream"
    assert result.needs_request_render
    assert result.streamed_resources[0]["action"] == "slow_report"
    assert 'ssr: "streamed"' in result.js
    # The shell renders the loading state; data is not in the initial HTML.
    assert "atlas" not in result.html
    assert "v-skeleton" in result.html


def test_stream_page_flushes_shell_then_data_blocks():
    action = _slow_data()

    @ui.page("/report", render="stream")
    def report():
        data = ui.resource(action, server_render=True)
        return ui.Page(ui.Each(data.value,
                               render=lambda item: ui.Text(item.name)))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/report")
    assert response.status == 200
    # Chunked: shell first, then the data block, then the closing tags.
    assert len(response.chunks) >= 3
    shell = response.chunks[0].decode()
    assert "</head>" in shell
    assert "atlas" not in shell
    body = response.text
    assert 'data-virel-stream="r1"' in body
    assert '"score": 0.9' in body
    assert body.rstrip().endswith("</html>")
    # Script-context safety in the data block.
    assert "</script><script>" not in body.split("data-virel-stream")[1]


def test_streamed_resource_errors_flush_as_error_blocks():
    @ui.server
    def broken() -> list:
        raise RuntimeError("db down")

    @ui.page("/report", render="stream")
    def report():
        data = ui.resource(broken, server_render=True)
        return ui.Page(ui.Suspense(
            data, content=ui.Each(data.value,
                                  render=lambda item: ui.Text(item.name))))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/report")
    assert '"error":' in response.text
    assert "db down" in response.text
