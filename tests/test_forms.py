"""Model-driven forms: field derivation, browser attributes, submit flow,
server revalidation, and structured errors. Covers both dataclasses and
Pydantic models."""

import json
from dataclasses import dataclass
from typing import Literal

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request

try:
    import pydantic  # noqa: F401
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


@dataclass
class SignupInput:
    email: str
    plan: Literal["free", "pro"] = "free"
    seats: int = 1


def _signup_page(action):
    def page():
        form = ui.form(SignupInput, submit=action)
        return ui.Page(
            ui.Form(
                ui.TextField(form.email, label="Email"),
                ui.Select(form.plan, label="Plan"),
                ui.NumberField(form.seats, label="Seats"),
                ui.FormActions(ui.SubmitButton("Sign up", form=form)),
                ui.When(form.succeeded,
                        then=ui.Alert(form.result, intent="success")),
                form=form,
            ),
        )
    return page


def _signup_action():
    @ui.server
    def signup(data: SignupInput) -> str:
        return f"Signed up {data.email} on {data.plan} with {data.seats} seat(s)."
    return signup


def test_fields_derive_states_and_browser_attributes():
    signup = _signup_action()
    ui.page("/")(_signup_page(signup))
    result = compile_page(active_registry().pages["/"])
    # email: required + type=email from the model (str field named email)
    assert 'type="email"' in result.html
    assert "required" in result.html
    # plan options come from the Literal
    assert '<option value="free">' in result.html
    assert '<option value="pro">' in result.html
    # submit goes through the form handler with preventDefault
    assert "ev.preventDefault();" in result.js
    assert '$.action("signup"' in result.js
    assert "e.fieldErrors" in result.js


def test_submit_flow_success_in_component_test():
    signup = _signup_action()
    view = ui.test.render(_signup_page(signup))
    view.get_by_label("Email").fill("ada@example.com")
    view.get_by_label("Plan").select("pro")
    view.get_by_label("Seats").fill(4)
    view.get_by_role("form").submit()
    assert "Signed up ada@example.com on pro with 4 seat(s)." in view.query_text()


def test_submit_flow_validation_errors_render_per_field():
    signup = _signup_action()
    view = ui.test.render(_signup_page(signup))
    view.get_by_label("Email").fill("not-an-email")
    view.get_by_role("form").submit()
    assert "Enter a valid email address." in view.query_text()
    # Fixing the field clears the error on the next submit
    view.get_by_label("Email").fill("ada@example.com")
    view.get_by_role("form").submit()
    assert "Enter a valid email address." not in view.query_text()
    assert "Signed up ada@example.com" in view.query_text()


def test_server_rejects_invalid_model_payload_with_field_errors():
    signup = _signup_action()
    ui.page("/")(_signup_page(signup))
    app = create_asgi_app(dev=True)
    response = asgi_request(app, "POST", "/_virel/action/signup",
                            body=json.dumps({"data": {"email": "", "plan": "free",
                                                      "seats": 1}}).encode())
    assert response.status == 400
    assert response.json["field_errors"]["email"] == "This field is required."

    response = asgi_request(app, "POST", "/_virel/action/signup",
                            body=json.dumps({"data": {"email": "a@b.co",
                                                      "plan": "enterprise",
                                                      "seats": 1}}).encode())
    assert response.status == 400
    assert "Must be one of" in response.json["field_errors"]["plan"]


def test_server_accepts_valid_model_payload():
    signup = _signup_action()
    ui.page("/")(_signup_page(signup))
    app = create_asgi_app(dev=True)
    response = asgi_request(app, "POST", "/_virel/action/signup",
                            body=json.dumps({"data": {"email": "a@b.co",
                                                      "plan": "pro",
                                                      "seats": 2}}).encode())
    assert response.status == 200
    assert response.json["result"] == "Signed up a@b.co on pro with 2 seat(s)."


def test_dataclass_results_are_serialized():
    @dataclass
    class Member:
        email: str
        role: str

    @ui.server
    def get_member() -> Member:
        return Member(email="a@b.co", role="admin")

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "POST", "/_virel/action/get_member", body=b"{}")
    assert response.json == {"result": {"email": "a@b.co", "role": "admin"}}


def test_form_rejects_action_without_matching_signature():
    @ui.server
    def unrelated(name: str) -> str:
        return name

    def page():
        form = ui.form(SignupInput, submit=unrelated)
        return ui.Page(ui.Form(form=form))

    with pytest.raises(ui.VirelCompileError, match="does not accept"):
        ui.test.render(page)


@pytest.mark.skipif(not HAS_PYDANTIC, reason="pydantic not installed")
def test_pydantic_model_validation_and_field_errors():
    from pydantic import BaseModel, Field

    class ProjectInput(BaseModel):
        name: str = Field(min_length=3)
        priority: int = 1

    @ui.server
    def create_project(data: ProjectInput) -> str:
        return f"Created {data.name} at priority {data.priority}."

    def page():
        form = ui.form(ProjectInput, submit=create_project)
        return ui.Page(
            ui.Form(
                ui.TextField(form.name, label="Name"),
                ui.NumberField(form.priority, label="Priority"),
                ui.FormActions(ui.SubmitButton("Create", form=form)),
                ui.When(form.succeeded, then=ui.Alert(form.result)),
                form=form,
            ),
        )

    view = ui.test.render(page)
    view.get_by_label("Name").fill("ab")
    view.get_by_role("form").submit()
    assert "at least 3 characters" in view.query_text()

    view.get_by_label("Name").fill("atlas")
    view.get_by_role("form").submit()
    assert "Created atlas at priority 1." in view.query_text()
