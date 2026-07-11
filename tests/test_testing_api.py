"""The pytest component-testing API (ui.test.render)."""

import pytest

from virel import ui


def counter_page():
    count = ui.state(0)
    return ui.Page(
        ui.Text(f"Count: {count}"),
        ui.Button("Increment", on_click=lambda: count.update(lambda c: c + 1),
                  intent="primary"),
        ui.When(count >= 3, then=ui.Alert("High!", intent="primary")),
    )


def test_click_updates_bound_text():
    view = ui.test.render(counter_page)
    assert "Count: 0" in view.query_text()
    view.get_by_role("button", name="Increment").click()
    view.get_by_role("button", name="Increment").click()
    assert "Count: 2" in view.query_text()


def test_when_visibility_tracks_state():
    view = ui.test.render(counter_page)
    alert = view.get_by_text("High!")
    assert not alert.is_visible()
    button = view.get_by_role("button", name="Increment")
    for _ in range(3):
        button.click()
    assert view.get_by_text("High!").is_visible()


def test_fill_drives_two_way_binding_and_derived():
    def search_page():
        query = ui.state("")
        normalized = ui.derived(lambda: query.strip().lower())
        return ui.Page(
            ui.TextField(query, label="Query"),
            ui.Text(f"Normalized: {normalized}"),
        )

    view = ui.test.render(search_page)
    view.get_by_label("Query").fill("  HeLLo ")
    assert "Normalized: hello" in view.query_text()


def test_form_flow_with_real_server_action():
    @ui.server
    def invite(email: str, role: str) -> str:
        if "@" not in email:
            raise ValueError("invalid email")
        return f"Invited {email} as {role}."

    def invite_page():
        email = ui.state("")
        role = ui.state("viewer")
        result = ui.state("")
        error = ui.state("")

        def submit():
            result.set("")
            error.set("")
            if len(email.strip()) == 0:
                error.set("Email required.")
            else:
                invite.call({"email": email, "role": role},
                            into=result, error_into=error)

        return ui.Page(
            ui.TextField(email, label="Email"),
            ui.Select(role, label="Role", options=["viewer", "editor"]),
            ui.Button("Send", on_click=submit, intent="primary"),
            ui.When(result != "", then=ui.Alert(result, intent="success")),
            ui.When(error != "", then=ui.Alert(error, intent="danger")),
        )

    view = ui.test.render(invite_page)

    # Client-side guard branch
    view.get_by_role("button", name="Send").click()
    assert view.get_by_text("Email required.").is_visible()

    # Server rejection surfaces through error_into
    view.get_by_label("Email").fill("nope")
    view.get_by_role("button", name="Send").click()
    assert "invalid email" in view.query_text()

    # Success path, including the select
    view.get_by_label("Email").fill("ada@example.com")
    view.get_by_label("Role").select("editor")
    view.get_by_role("button", name="Send").click()
    assert view.get_by_text("Invited ada@example.com as editor.").is_visible()


def test_streaming_action_collects_chunks():
    @ui.server(stream=True)
    def logs(n: int = 2):
        for i in range(n):
            yield f"line {i};"

    def stream_page():
        log = ui.state("")
        running = ui.state(False)

        def start():
            log.set("")
            running.set(True)
            logs.stream({"n": 3}, into=log, done_set=(running, False))

        return ui.Page(
            ui.Button("Run", on_click=start),
            ui.When(log != "", then=ui.Code(log, block=True)),
        )

    view = ui.test.render(stream_page)
    view.get_by_role("button", name="Run").click()
    assert "line 0;line 1;line 2;" in view.query_text()
    assert view.state("s2") is False  # running reset by done_set


def test_disabled_button_cannot_be_clicked():
    def page():
        email = ui.state("")
        done = ui.state(False)
        return ui.Page(
            ui.TextField(email, label="Email"),
            ui.Button("Send", on_click=lambda: done.set(True),
                      disabled=ui.length(email) == 0),
        )

    view = ui.test.render(page)
    with pytest.raises(AssertionError, match="disabled"):
        view.get_by_role("button", name="Send").click()
    view.get_by_label("Email").fill("x@y.z")
    view.get_by_role("button", name="Send").click()


def test_hidden_element_cannot_be_interacted_with():
    def page():
        show = ui.state(False)
        clicked = ui.state(False)
        return ui.Page(
            ui.Button("Reveal", on_click=lambda: show.set(True)),
            ui.When(show, then=ui.Button("Hidden action",
                                         on_click=lambda: clicked.set(True))),
        )

    view = ui.test.render(page)
    with pytest.raises(AssertionError, match="not visible"):
        view.get_by_role("button", name="Hidden action").click()
    view.get_by_role("button", name="Reveal").click()
    view.get_by_role("button", name="Hidden action").click()


def test_missing_element_error_lists_candidates():
    view = ui.test.render(counter_page)
    with pytest.raises(AssertionError, match="button:Increment"):
        view.get_by_role("button", name="Nope")
