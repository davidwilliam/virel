"""Data-structure adapters (SPEC 12.1)."""

import dataclasses
import datetime
import enum
from typing import Literal, NamedTuple, TypedDict

import pytest

from virel import ui
from virel.expr import VirelCompileError


@dataclasses.dataclass
class Run:
    model: str
    score: float
    started: datetime.date


class Verdict(enum.Enum):
    PASSED = "passed"
    FAILED = "failed"


class RunDict(TypedDict):
    model: str
    score: float


class RunTuple(NamedTuple):
    model: str
    score: float


def test_records_from_dataclasses_with_enum_and_date_values():
    @dataclasses.dataclass
    class Result:
        model: str
        verdict: Verdict
        day: datetime.date

    rows = ui.records([Result("atlas", Verdict.PASSED,
                              datetime.date(2026, 7, 10))])
    assert rows == [{"model": "atlas", "verdict": "passed",
                     "day": "2026-07-10"}]


def test_records_from_typed_dict_named_tuple_and_generators():
    assert ui.records([RunDict(model="a", score=1.0)]) == [
        {"model": "a", "score": 1.0}]
    assert ui.records([RunTuple("a", 1.0)]) == [{"model": "a", "score": 1.0}]
    assert ui.records(RunTuple(m, s) for m, s in [("a", 1.0)]) == [
        {"model": "a", "score": 1.0}]
    with pytest.raises(VirelCompileError, match="sequence of records"):
        ui.records({"model": "a"})
    with pytest.raises(VirelCompileError, match="Cannot convert"):
        ui.records([object()])


def test_records_from_pandas_with_inferred_columns():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"model": ["a", "b"], "score": [0.9, 0.7],
                       "started": ["2026-07-01", "2026-07-02"]})
    rows = ui.records(df)
    assert rows[0]["model"] == "a" and rows[1]["score"] == 0.7

    from virel.data import infer_columns
    columns = {c.key: c for c in infer_columns(df)}
    assert columns["score"].kind == "number"
    assert columns["started"].kind == "date"
    assert columns["model"].kind == "text"
    assert columns["model"].label == "Model"


def test_records_from_polars_and_arrow():
    pl = pytest.importorskip("polars")
    assert ui.records(pl.DataFrame({"x": [1, 2]})) == [{"x": 1}, {"x": 2}]
    pa = pytest.importorskip("pyarrow")
    table = pa.table({"x": [1, 2]})
    assert ui.records(table) == [{"x": 1}, {"x": 2}]


def test_records_from_numpy_structured_array():
    np = pytest.importorskip("numpy")
    array = np.array([("a", 0.9), ("b", 0.7)],
                     dtype=[("model", "U8"), ("score", "f8")])
    rows = ui.records(array)
    assert rows == [{"model": "a", "score": 0.9},
                    {"model": "b", "score": 0.7}]
    assert type(rows[0]["score"]) is float  # numpy scalar unwrapped
    with pytest.raises(VirelCompileError, match="structured dtype"):
        ui.records(np.array([1.0, 2.0]))


def test_datagrid_accepts_any_record_shape_and_infers_columns():
    grid = ui.DataGrid([Run("atlas", 0.93, datetime.date(2026, 7, 10)),
                        Run("base", 0.71, datetime.date(2026, 7, 8))],
                       key="model")
    from virel.nodes import template_html
    html = template_html([grid], {})
    assert ">Model<" in html and ">Score<" in html and ">Started<" in html
    assert 'data-kind="number"' in html
    assert 'data-kind="date"' in html
    with pytest.raises(VirelCompileError, match="empty data"):
        ui.DataGrid([])


def test_chart_series_accepts_numpy_and_pandas_values():
    np = pytest.importorskip("numpy")
    chart = ui.Chart("line", [ui.Series("s", points=np.array([1.0, 2.5]))])
    from virel.nodes import template_html
    assert "<title>s: 2.5</title>" in template_html([chart], {})
    pd = pytest.importorskip("pandas")
    ui.Chart("bar", [ui.Series("s", points=pd.Series([1, 2, 3]))])


def test_forms_accept_typed_dict_models():
    class Invite(TypedDict):
        email: str
        role: Literal["viewer", "editor"]

    from virel.forms import analyze_model, validate_model
    specs = {spec.name: spec for spec in analyze_model(Invite)}
    assert specs["email"].input_type == "email"
    assert specs["role"].options == ["viewer", "editor"]
    instance, errors = validate_model(
        Invite, {"email": "a@b.co", "role": "editor"})
    assert errors == {} and instance == {"email": "a@b.co", "role": "editor"}
    _, errors = validate_model(Invite, {"email": "a@b.co"})
    assert "role" in errors


def test_forms_accept_enum_fields():
    @dataclasses.dataclass
    class Review:
        verdict: Verdict

    from virel.forms import analyze_model, validate_model
    spec = analyze_model(Review)[0]
    assert spec.input_type == "select"
    assert spec.options == ["passed", "failed"]
    instance, errors = validate_model(Review, {"verdict": "failed"})
    assert errors == {} and instance.verdict is Verdict.FAILED
    _, errors = validate_model(Review, {"verdict": "maybe"})
    assert "verdict" in errors


def test_typed_dict_form_renders_and_submits():
    class Feedback(TypedDict):
        comment: str
        verdict: Literal["up", "down"]

    @ui.server
    def send_feedback(data: Feedback) -> str:
        return f"{data['verdict']}: {data['comment']}"

    @ui.page("/feedback")
    def feedback_page():
        form = ui.form(Feedback, submit=send_feedback)
        return ui.Page(
            ui.Form(ui.TextField(form.comment, label="Comment"),
                    ui.Select(form.verdict, label="Verdict"),
                    ui.FormActions(ui.SubmitButton("Send", form=form)),
                    ui.When(form.succeeded, then=ui.Text(form.result)),
                    form=form),
        )

    view = ui.test.render(feedback_page)
    view.get_by_label("Comment").fill("solid")
    view.get_by_label("Verdict").select("up")
    view.get_by_role("form").submit()
    assert "up: solid" in view.query_text()
