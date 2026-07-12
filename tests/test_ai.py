"""AI product components (SPEC 12.4)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.nodes import template_html
from virel.registry import active_registry


def test_streaming_response_view():
    @ui.page("/ai-response")
    def page():
        answer = ui.state("Hello")
        busy = ui.state(True)
        return ui.Page(ui.ai.Response(answer, streaming=busy))

    compiled = compile_page(active_registry().pages["/ai-response"])
    assert 'role="region"' in compiled.html
    assert "v-ai-cursor" in compiled.html
    assert "$.bindShow" in compiled.js  # the cursor follows streaming


def test_prompt_editor_submits_and_binds():
    @ui.page("/ai-prompt")
    def page():
        prompt = ui.state("")
        sent = ui.state("")

        def send():
            sent.set(f"sent: {prompt}")
            prompt.set("")

        return ui.Page(
            ui.ai.PromptEditor(prompt, on_submit=send),
            ui.Text(f"{sent}"),
        )

    view = ui.test.render(page)
    view.get_by_label("Prompt").fill("Summarize the report")
    view.get_by_role("button", name="Send").click()
    assert "sent: Summarize the report" in view.query_text()
    assert "$.prompt_editor(" in compile_page(
        active_registry().pages["/ai-prompt"]).js


def test_timeline_renders_roles_and_updates():
    @ui.page("/ai-timeline")
    def page():
        messages = ui.state([
            {"role": "user", "content": "What is our refund policy?"},
            {"role": "assistant", "content": "Thirty days, no questions."},
        ])
        return ui.Page(ui.ai.Timeline(messages,
                                      key=lambda m: m["content"]))

    compiled = compile_page(active_registry().pages["/ai-timeline"])
    assert 'role="log"' in compiled.html
    assert 'data-role="user"' in compiled.html
    view = ui.test.render(page)
    assert "Thirty days" in view.query_text()


def test_tool_call_display():
    node = ui.ai.ToolCall("search_docs", {"query": "refunds"},
                          result={"hits": 3}, status="done")
    html = template_html([node], {})
    assert "<details" in html and "search_docs" in html
    assert "&quot;query&quot;" in html and "&quot;hits&quot;" in html
    with pytest.raises(VirelCompileError, match="status"):
        ui.ai.ToolCall("x", {}, status="exploded")


def test_citations_check_url_schemes():
    node = ui.ai.Citations([
        {"title": "Policy", "url": "/docs/policy", "snippet": "30 days"},
        {"title": "No link"},
    ])
    html = template_html([node], {})
    assert 'href="/docs/policy"' in html and "30 days" in html
    assert 'rel="noreferrer noopener"' in html
    with pytest.raises(VirelCompileError, match="blocked scheme"):
        ui.ai.Citations([{"title": "x", "url": "javascript:alert(1)"}])


def test_token_meter_computes_cost_reactively():
    @ui.page("/ai-meter")
    def page():
        tokens_in = ui.state(1_000_000)
        tokens_out = ui.state(0)
        return ui.Page(ui.ai.TokenMeter(
            tokens_in, tokens_out, input_price=3.0, output_price=15.0,
            budget=2_000_000))

    compiled = compile_page(active_registry().pages["/ai-meter"])
    assert "$3" in compiled.html          # one million input tokens at $3
    assert "<progress" in compiled.html
    assert "Math.round" in compiled.js    # cost recomputes in the browser


def test_parameters_and_model_select():
    @ui.page("/ai-controls")
    def page():
        model = ui.state("atlas-large")
        temp = ui.state(0.7)
        return ui.Page(
            ui.ai.ModelSelect(model, models=["atlas-large", "atlas-small"]),
            ui.ai.Parameters(
                ui.ai.Param("temperature", temp, min=0.0, max=2.0,
                            step=0.1)),
            ui.Text(f"t={temp}"),
        )

    view = ui.test.render(page)
    view.get_by_label("Model").select("atlas-small")
    assert view.state("s1") == "atlas-small"
    view.get_by_label("temperature").fill(1.2)
    assert "t=1.2" in view.query_text()
    with pytest.raises(VirelCompileError, match="at least one"):
        ui.ai.Parameters()


def test_trace_waterfall_scales_spans():
    node = ui.ai.Trace([
        {"name": "plan", "start_ms": 0, "duration_ms": 100},
        {"name": "search", "start_ms": 100, "duration_ms": 300,
         "depth": 1, "status": "failed"},
    ])
    html = template_html([node], {})
    assert "width: 25.00%" in html        # 100 of 400 total
    assert "margin-inline-start: 25.00%" in html
    assert "v-ai-span-failed" in html
    assert 'role="img"' in html


def test_feedback_thumbs_write_state():
    @ui.page("/ai-feedback")
    def page():
        rating = ui.state("")
        return ui.Page(ui.ai.Feedback(rating), ui.Text(f"rating: {rating}"))

    view = ui.test.render(page)
    view.get_by_role("button", name="Thumbs up").click()
    assert "rating: up" in view.query_text()
    view.get_by_role("button", name="Thumbs down").click()
    assert "rating: down" in view.query_text()
    html = compile_page(active_registry().pages["/ai-feedback"]).html
    assert 'aria-pressed' in html


def test_approval_step_requires_explicit_choice():
    @ui.page("/ai-approval")
    def page():
        decision = ui.state("pending")
        return ui.Page(
            ui.ai.Approval(
                title="Send 3 emails?",
                description="The draft goes to the launch list.",
                on_approve=lambda: decision.set("approved"),
                on_reject=lambda: decision.set("rejected"),
                destructive=True),
            ui.Text(f"decision: {decision}"),
        )

    view = ui.test.render(page)
    view.get_by_role("button", name="Reject").click()
    assert "decision: rejected" in view.query_text()
    view.get_by_role("button", name="Approve").click()
    assert "decision: approved" in view.query_text()
    assert "v-btn-danger" in compile_page(
        active_registry().pages["/ai-approval"]).html


def test_job_progress_tracks_status_and_percent():
    @ui.page("/ai-job")
    def page():
        status = ui.state("running")
        pct = ui.state(40)
        return ui.Page(ui.ai.JobProgress(status=status, progress=pct,
                                         label="Batch run"))

    compiled = compile_page(active_registry().pages["/ai-job"])
    assert "<progress" in compiled.html
    view = ui.test.render(page)
    assert view.get_by_text("running").is_visible()
    assert not view.get_by_text("failed").is_visible()


def test_eval_table_is_a_configured_grid():
    rows = [{"run": "r1", "score": 0.9}, {"run": "r2", "score": 0.7}]
    node = ui.ai.EvalTable(rows, key="run")
    html = template_html([node], {})
    assert "v-datagrid" in html and "v-grid-export" in html


def test_recorder_wraps_a_file_field():
    @ui.page("/ai-rec")
    def page():
        voice = ui.FileField(label="Audio note", accept="audio/*")
        return ui.Page(ui.ai.Recorder(voice))

    compiled = compile_page(active_registry().pages["/ai-rec"])
    assert "$.recorder(" in compiled.js
    assert 'accept="audio/*"' in compiled.html
    with pytest.raises(VirelCompileError, match="FileField"):
        ui.ai.Recorder("not-a-field")


def test_image_viewer_lightbox():
    node = ui.ai.ImageViewer("/public/plot.png", alt="Loss curve",
                             caption="Training loss")
    html = template_html([node], {})
    assert 'aria-label="View Loss curve full size"' in html
    assert "Training loss" in html
