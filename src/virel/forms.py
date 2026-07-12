"""Model-driven forms (SPEC 8.9).

One model drives everything: field states, input types, native browser
constraint attributes (required, type=email, min/max), server revalidation,
and structured per-field error display. Pydantic models and dataclasses are
both supported; Pydantic is optional and detected at runtime.

    form = ui.form(InviteInput, submit=invite_member)

    ui.Form(
        ui.TextField(form.email, label="Email"),
        ui.Select(form.role, label="Role"),
        ui.FormActions(ui.SubmitButton("Send invitation", form=form)),
        form=form,
    )

The browser applies the derived constraint attributes immediately; the
server always revalidates against the model and returns field-scoped errors.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import typing
from typing import Any

from .expr import (
    Compare,
    DictExpr,
    Expr,
    Handler,
    Index,
    Lit,
    State,
    VirelCompileError,
    _run_coroutine,
    inspect_isawaitable,
)
from .nodes import BindText, Element, Node

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MISSING = object()


def _pydantic_base_model() -> type | None:
    try:
        from pydantic import BaseModel
        return BaseModel
    except ImportError:
        return None


def _is_typeddict(annotation: Any) -> bool:
    return typing.is_typeddict(annotation)


def is_model_type(annotation: Any) -> bool:
    if _is_typeddict(annotation):
        return True
    if not isinstance(annotation, type):
        return False
    if dataclasses.is_dataclass(annotation):
        return True
    base = _pydantic_base_model()
    return base is not None and issubclass(annotation, base)


# ---------------------------------------------------------------------------
# Model analysis
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FieldSpec:
    name: str
    annotation: Any
    required: bool
    default: Any
    input_type: str          # text | email | number | checkbox | select
    options: list[str] | None

    @property
    def initial(self) -> Any:
        if self.default is not _MISSING:
            return self.default
        if self.input_type == "checkbox":
            return False
        if self.input_type == "number":
            return 0
        if self.options:
            return self.options[0]
        return ""


def analyze_model(model: type) -> list[FieldSpec]:
    base = _pydantic_base_model()
    if base is not None and isinstance(model, type) and issubclass(model, base):
        return _analyze_pydantic(model)
    if dataclasses.is_dataclass(model):
        return _analyze_dataclass(model)
    if _is_typeddict(model):
        return _analyze_typeddict(model)
    raise VirelCompileError(
        f"ui.form requires a Pydantic model, dataclass, or TypedDict; got "
        f"{model!r}. Define the input shape as a class with typed fields."
    )


def _analyze_typeddict(model: type) -> list[FieldSpec]:
    hints = typing.get_type_hints(model)
    required_keys = getattr(model, "__required_keys__", frozenset(hints))
    return [
        _build_spec(name, annotation, name in required_keys, _MISSING)
        for name, annotation in hints.items()
    ]


def _analyze_pydantic(model: type) -> list[FieldSpec]:
    specs = []
    for name, info in model.model_fields.items():  # type: ignore[attr-defined]
        required = info.is_required()
        default = info.default if not required else _MISSING
        specs.append(_build_spec(name, info.annotation, required, default))
    return specs


def _analyze_dataclass(model: type) -> list[FieldSpec]:
    hints = typing.get_type_hints(model)
    specs = []
    for field in dataclasses.fields(model):
        if field.default is not dataclasses.MISSING:
            required, default = False, field.default
        elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            required, default = False, field.default_factory()
        else:
            required, default = True, _MISSING
        specs.append(_build_spec(field.name, hints.get(field.name, str),
                                 required, default))
    return specs


def _build_spec(name: str, annotation: Any, required: bool, default: Any) -> FieldSpec:
    options: list[str] | None = None
    input_type = "text"
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        options = [str(v) for v in typing.get_args(annotation)]
        input_type = "select"
    elif isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        options = [str(member.value) for member in annotation]
        input_type = "select"
    elif annotation is bool:
        input_type = "checkbox"
    elif annotation in (int, float):
        input_type = "number"
    elif _is_email_annotation(name, annotation):
        input_type = "email"
    return FieldSpec(name=name, annotation=annotation, required=required,
                     default=default, input_type=input_type, options=options)


def _is_email_annotation(name: str, annotation: Any) -> bool:
    if getattr(annotation, "__name__", "") == "EmailStr":
        return True
    return annotation is str and name == "email"


# ---------------------------------------------------------------------------
# Server-side validation
# ---------------------------------------------------------------------------

def validate_model(model: type, data: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """Build a model instance from a JSON dict, or return field errors."""
    base = _pydantic_base_model()
    if base is not None and isinstance(model, type) and issubclass(model, base):
        try:
            return model(**data), {}
        except Exception as error:
            return None, _pydantic_errors(error)
    return _validate_fields(model, data)


def _pydantic_errors(error: Any) -> dict[str, str]:
    field_errors: dict[str, str] = {}
    for item in getattr(error, "errors", lambda: [])():
        location = item.get("loc") or ()
        key = str(location[0]) if location else "_root"
        field_errors.setdefault(key, item.get("msg", "Invalid value"))
    return field_errors or {"_root": str(error)}


def _validate_fields(model: type, data: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """Shared validation for dataclasses and TypedDicts: both construct
    from keyword values once every field coerces."""
    specs = analyze_model(model)
    errors: dict[str, str] = {}
    values: dict[str, Any] = {}
    for spec in specs:
        raw = data.get(spec.name, _MISSING)
        if raw is _MISSING or raw is None or raw == "":
            if spec.required:
                errors[spec.name] = "This field is required."
            elif spec.default is not _MISSING:
                values[spec.name] = spec.default
            continue
        value, error = _coerce(spec, raw)
        if error:
            errors[spec.name] = error
        else:
            values[spec.name] = value
    unknown = set(data) - {s.name for s in specs}
    if unknown:
        errors["_root"] = f"Unknown field(s): {', '.join(sorted(unknown))}"
    if errors:
        return None, errors
    return model(**values), {}


def _coerce(spec: FieldSpec, raw: Any) -> tuple[Any, str | None]:
    annotation = spec.annotation
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        for member in annotation:
            if str(member.value) == str(raw):
                return member, None
        return None, f"Must be one of: {', '.join(spec.options or [])}."
    if spec.options is not None:
        if str(raw) not in spec.options:
            return None, f"Must be one of: {', '.join(spec.options)}."
        return str(raw), None
    if spec.annotation is bool:
        return bool(raw), None
    if spec.annotation is int:
        try:
            return int(raw), None
        except (TypeError, ValueError):
            return None, "Enter a whole number."
    if spec.annotation is float:
        try:
            return float(raw), None
        except (TypeError, ValueError):
            return None, "Enter a number."
    if spec.input_type == "email":
        if not _EMAIL_RE.match(str(raw)):
            return None, "Enter a valid email address."
        return str(raw), None
    return raw, None


# ---------------------------------------------------------------------------
# The reactive form object
# ---------------------------------------------------------------------------

class FieldRef:
    """A form field: its state plus the metadata field components use to
    derive input attributes and error display."""

    def __init__(self, form: "FormObject", spec: FieldSpec, state: State) -> None:
        self.form = form
        self.spec = spec
        self.state = state

    def input_attrs(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self.spec.required:
            attrs["required"] = True
        if self.spec.input_type == "email":
            attrs["type"] = "email"
        return attrs

    def error_expr(self) -> Expr:
        return Index(self.form.errors, Lit(self.spec.name))

    def error_node(self) -> Node:
        return Element("span", [BindText(self.error_expr())],
                       attrs={"class": "v-field-error", "role": "alert"})


class FormSubmitOp:
    """The compiled submit flow: clear errors, mark pending, call the
    action, route the result or the structured field errors."""

    def __init__(self, form: "FormObject") -> None:
        self.form = form

    def _args(self) -> DictExpr:
        fields = DictExpr({
            spec.name: field.state
            for spec, field in zip(self.form.specs, self.form.fields.values())
        })
        if self.form.model_param:
            return DictExpr({self.form.model_param: fields})
        return fields

    def js(self) -> str:
        f = self.form
        return (
            f"S.{f.errors.name}.set({{}}); "
            f"S.{f.submitting.name}.set(true); "
            f'$.action("{f.action.name}", {self._args().js()})'
            f".then((r) => {{ S.{f.result.name}.set(r); }})"
            f".catch((e) => {{ S.{f.errors.name}.set("
            f'e.fieldErrors || {{"_root": String(e.message || e)}}); }})'
            f".finally(() => S.{f.submitting.name}.set(false));"
        )

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        from .registry import (ActionArgumentError, ActionValidationError,
                               active_registry, to_jsonable)
        form = self.form
        action = active_registry().actions[form.action.name]
        env[form.errors.name] = {}
        env[form.submitting.name] = True
        try:
            payload = self._args().evaluate(env)
            kwargs = action.prepare(payload)
            result = action.fn(**kwargs)
            if inspect_isawaitable(result):
                result = _run_coroutine(result)
            env[form.result.name] = to_jsonable(result)
        except ActionValidationError as error:
            env[form.errors.name] = error.field_errors
        except ActionArgumentError as error:
            env[form.errors.name] = {"_root": str(error)}
        except Exception as error:
            env[form.errors.name] = {"_root": f"{type(error).__name__}: {error}"}
        finally:
            env[form.submitting.name] = False

    def to_ir(self) -> dict[str, Any]:
        return {"op": "form_submit", "action": self.form.action.name,
                "fields": [s.name for s in self.form.specs]}


class FormObject:
    def __init__(self, model: type, submit: Any) -> None:
        from .registry import ServerAction
        if not isinstance(submit, ServerAction):
            raise VirelCompileError(
                "ui.form(submit=...) must be a @ui.server action."
            )
        self.model = model
        self.action = submit
        self.specs = analyze_model(model)
        self.fields: dict[str, FieldRef] = {}
        for spec in self.specs:
            self.fields[spec.name] = FieldRef(self, spec, State(spec.initial))
        self.errors = State({})
        self.submitting = State(False)
        self.result = State(None)
        self.model_param = self._find_model_param()

    def _find_model_param(self) -> str | None:
        import inspect
        hints = self.action.type_hints()
        for name, annotation in hints.items():
            if name != "return" and annotation is self.model:
                return name
        # Flat mapping: action parameters named like the fields.
        params = self.action.signature.parameters
        field_names = {s.name for s in self.specs}
        unknown_fields = field_names - set(params)
        missing_required = {
            name for name, param in params.items()
            if param.default is inspect.Parameter.empty
            and name not in field_names
        }
        if not unknown_fields and not missing_required:
            return None
        raise VirelCompileError(
            f"Server action {self.action.name!r} does not accept "
            f"{self.model.__name__!r}. Give it a parameter annotated with "
            f"the model, or parameters matching the field names "
            f"({', '.join(sorted(field_names))})."
        )

    def __getattr__(self, name: str) -> FieldRef:
        fields = object.__getattribute__(self, "fields")
        if name in fields:
            return fields[name]
        raise AttributeError(
            f"Form for {self.model.__name__!r} has no field {name!r}. "
            f"Fields: {', '.join(fields)}."
        )

    @property
    def root_error(self) -> Expr:
        return Index(self.errors, Lit("_root"))

    @property
    def succeeded(self) -> Expr:
        return Compare("!=", self.result, Lit(None))

    def submit_handler(self) -> Handler:
        return Handler([FormSubmitOp(self)], prevent_default=True)


def form(model: type, *, submit: Any) -> FormObject:
    """Create a reactive form from a Pydantic model or dataclass."""
    return FormObject(model, submit)


# ---------------------------------------------------------------------------
# Form components
# ---------------------------------------------------------------------------

def Form(*children: Any, form: FormObject) -> Element:
    from .nodes import normalize_children
    root_error = Element("span", [BindText(form.root_error)],
                         attrs={"class": "v-field-error", "role": "alert"})
    return Element(
        "form",
        normalize_children(children) + [root_error],
        attrs={"class": "v-form v-stack"},
        events={"submit": form.submit_handler()},
    )


def SubmitButton(label: Any, *, form: FormObject, intent: str = "primary") -> Element:
    from .elements import Button
    button = Button(label, intent=intent, kind="submit",
                    disabled=form.submitting)
    return button


def FormActions(*children: Any) -> Element:
    from .nodes import normalize_children
    return Element("div", normalize_children(children),
                   attrs={"class": "v-row v-form-actions"})
