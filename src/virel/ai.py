"""AI product components (SPEC 12.4), as ``ui.ai``.

Sixteen UI primitives for AI products, not an agent framework: they
compose Virel's existing machinery (streaming server actions, states,
uploads, the data grid) and hold no model opinions. Everything here is
typed, accessible, and testable from pytest like any other component.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .datagrid import Column, DataGrid
from .elements import (Badge, Button, Code, Progress, Row, Select, Slider,
                       Spinner, Text, Textarea)
from .expr import Expr, VirelCompileError, cond, lift
from .icons import Icon
from .nodes import BindText, Element, Node, TextNode, When, normalize_children

_INTENT_BY_STATUS = {"running": "primary", "done": "success",
                     "failed": "danger", "pending": "neutral"}


# ---------------------------------------------------------------------------
# Conversation surface
# ---------------------------------------------------------------------------

def Response(text: Any, *, streaming: Any = None,
             label: str = "Assistant response") -> Element:
    """The streaming response view: text arrives token by token into a
    state (``action.stream(into=text)``), whitespace is preserved, and
    a cursor pulses while ``streaming`` is truthy."""
    children: list[Node] = [Element(
        "span", [BindText(lift(text))], attrs={"class": "v-ai-text"})]
    if streaming is not None:
        children.append(When(streaming, then=Element(
            "span", attrs={"class": "v-ai-cursor", "aria-hidden": "true"})))
    return Element("div", children,
                   attrs={"class": "v-ai-response", "role": "region",
                          "aria-label": label})


def PromptEditor(state: Any, *, on_submit: Callable[[], None],
                 label: str = "Prompt",
                 placeholder: str = "Send a message…",
                 submit_label: str = "Send",
                 accessory: Any = None) -> Element:
    """The prompt editor: a labeled textarea bound to state, submitted
    by the button or Ctrl/Cmd+Enter. ``accessory=`` slots multimodal
    input next to the send button (typically a ui.FileField)."""
    field = Textarea(state, label=label, placeholder=placeholder)
    controls: list[Node] = []
    if accessory is not None:
        controls.append(accessory)
    controls.extend([
        Element("span", [TextNode("Ctrl+Enter to send")],
                attrs={"class": "v-ai-hint"}),
        Button(submit_label, on_click=on_submit, intent="primary"),
    ])
    return Element("div", [field, Row(*controls, gap=3, justify="end")],
                   attrs={"class": "v-ai-prompt v-stack",
                          "style": "gap: calc(var(--v-space) * 3)"},
                   runtime_binding="prompt_editor")


def Timeline(messages: Any, *, key: Callable[[Any], Any] | None = None,
             label: str = "Conversation") -> Node:
    """The message timeline over a list state of ``{"role", "content"}``
    dicts: user messages align to the end, everything else to the
    start, with the role announced on each entry."""
    from .elements import Each

    def bubble(item: Any) -> Element:
        return Element("div", [
            Element("span", [BindText(item["role"])],
                    attrs={"class": "v-ai-role"}),
            Element("div", [BindText(item["content"])],
                    attrs={"class": "v-ai-bubble"}),
        ], attrs={"class": "v-ai-message", "data-role": item["role"]})

    return Element("div", [Each(messages, render=bubble, key=key, gap=3)],
                   attrs={"class": "v-ai-timeline", "role": "log",
                          "aria-label": label})


def ToolCall(name: str, args: dict, *, result: Any = None,
             status: str = "done") -> Element:
    """The structured tool-call display: name, arguments, and result,
    collapsible on the native details element."""
    if status not in _INTENT_BY_STATUS:
        raise VirelCompileError(
            f"ToolCall status must be one of {', '.join(_INTENT_BY_STATUS)}.")
    body: list[Node] = [Code(json.dumps(args, indent=2), block=True,
                             language="json")]
    if result is not None:
        body.append(Text("Result", muted=True, size="sm"))
        result_text = result if isinstance(result, str) \
            else json.dumps(result, indent=2)
        body.append(Code(result_text, block=True, language="json"))
    summary = Element("summary", [
        Icon("settings", size=14),
        Element("code", [TextNode(str(name))],
                attrs={"class": "v-code-inline"}),
        Badge(status, intent=_INTENT_BY_STATUS[status]),
    ], attrs={"class": "v-ai-tool-summary"})
    return Element("details", [summary, Element(
        "div", body, attrs={"class": "v-ai-tool-body v-stack",
                            "style": "gap: calc(var(--v-space) * 2)"})],
        attrs={"class": "v-ai-tool"})


def Citations(sources: list[dict], *, label: str = "Sources") -> Element:
    """The citation panel: numbered sources with scheme-checked links
    and optional snippets."""
    if not sources:
        raise VirelCompileError("Citations needs at least one source.")
    from .security import is_safe_url
    items: list[Node] = []
    for source in sources:
        title = str(source.get("title", source.get("url", "Source")))
        url = source.get("url")
        head: Node
        if url is not None:
            if not is_safe_url(str(url)):
                raise VirelCompileError(
                    f"Citation URL {url!r} uses a blocked scheme.")
            head = Element("a", [TextNode(title)], attrs={
                "href": str(url), "class": "v-link",
                "target": "_blank", "rel": "noreferrer noopener"})
        else:
            head = Element("span", [TextNode(title)])
        entry: list[Node] = [head]
        if source.get("snippet"):
            entry.append(Element("p", [TextNode(str(source["snippet"]))],
                                 attrs={"class": "v-ai-snippet"}))
        items.append(Element("li", entry))
    return Element("nav", [Element("ol", items,
                                   attrs={"class": "v-ai-citations"})],
                   attrs={"aria-label": label})


# ---------------------------------------------------------------------------
# Controls and meters
# ---------------------------------------------------------------------------

def TokenMeter(input_tokens: Any, output_tokens: Any, *,
               input_price: float | None = None,
               output_price: float | None = None,
               budget: int | None = None) -> Element:
    """The token and cost meter. Token counts may be reactive; prices
    are per million tokens, and cost recomputes in the browser as the
    counts stream."""
    parts: list[Node] = [
        _meter("Input", input_tokens), _meter("Output", output_tokens)]
    if input_price is not None and output_price is not None:
        cost = (lift(input_tokens) * (input_price / 1_000_000)
                + lift(output_tokens) * (output_price / 1_000_000))
        parts.append(Element("div", [
            Element("span", [TextNode("Cost")], attrs={"class": "v-ai-meter-label"}),
            Element("strong", [BindText(lift("$") + _round4(cost))]),
        ], attrs={"class": "v-ai-meter"}))
    stack: list[Node] = [Row(*parts, gap=6, wrap=True)]
    if budget is not None:
        total = lift(input_tokens) + lift(output_tokens)
        stack.append(Progress(total, max=budget, label="Token budget"))
    return Element("div", stack,
                   attrs={"class": "v-ai-tokenmeter v-stack",
                          "style": "gap: calc(var(--v-space) * 2)"})


def _round4(value: Any) -> Expr:
    from .expr import BinOp, Cast, Lit
    scaled = Cast("round", BinOp("*", lift(value), Lit(10000)))
    return Cast("str", BinOp("/", scaled, Lit(10000)))


def _meter(label: str, value: Any) -> Element:
    return Element("div", [
        Element("span", [TextNode(label)], attrs={"class": "v-ai-meter-label"}),
        Element("strong", [BindText(lift(value))]),
    ], attrs={"class": "v-ai-meter"})


def ModelSelect(state: Any, *, models: list[str],
                label: str = "Model") -> Element:
    """The model selector over the identifiers the product offers."""
    if not models:
        raise VirelCompileError("ModelSelect needs at least one model.")
    return Select(state, label=label, options=models)


class Param:
    """One sampling parameter: a state plus its range."""

    def __init__(self, name: str, state: Any, *, min: float, max: float,
                 step: float = 1.0) -> None:
        self.name = name
        self.state = state
        self.min = min
        self.max = max
        self.step = step


def Parameters(*params: Param) -> Element:
    """The parameter controls: labeled sliders with live values."""
    if not params:
        raise VirelCompileError("Parameters needs at least one Param.")
    rows: list[Node] = []
    for param in params:
        if not isinstance(param, Param):
            raise VirelCompileError("Parameters takes ui.ai.Param entries.")
        rows.append(Element("div", [
            Slider(param.state, label=param.name, min=param.min,
                   max=param.max, step=param.step),
            Element("span", [BindText(lift(param.state))],
                    attrs={"class": "v-ai-param-value"}),
        ], attrs={"class": "v-ai-param"}))
    return Element("div", rows, attrs={
        "class": "v-ai-params v-stack",
        "style": "gap: calc(var(--v-space) * 3)"})


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

def Recorder(field: Any, *, label: str = "Record audio") -> Element:
    """The audio recorder: records through the microphone and delivers
    the take into the given ui.FileField's input, so the existing
    upload flow (``ui.upload(files=field)``) carries it to the server
    unchanged:

        voice = ui.FileField(label="Audio note", accept="audio/*")
        ui.ai.Recorder(voice)
    """
    if not isinstance(field, Element):
        raise VirelCompileError(
            "Recorder takes the ui.FileField element it records into.")
    return Element("div", [
        Element("div", [field], attrs={"class": "v-ai-rec-field"}),
        Row(
            Element("button", [Icon("mic", size=15),
                               Element("span", [TextNode("Record")])],
                    attrs={"type": "button",
                           "class": "v-btn v-btn-neutral v-btn-sm "
                                    "v-ai-rec-toggle"}),
            Element("span", attrs={"class": "v-ai-rec-time",
                                   "role": "status"}),
            gap=3,
        ),
    ], attrs={"class": "v-ai-recorder"}, runtime_binding="recorder")


def ImageViewer(src: str, *, alt: str, caption: str | None = None) -> Element:
    """The image viewer: click (or Enter) opens a full-size lightbox on
    the native dialog; Escape closes it."""
    from .elements import Image
    image = Image(src, alt)
    children: list[Node] = [Element(
        "button", [image],
        attrs={"type": "button", "class": "v-ai-image-open",
               "aria-label": f"View {alt} full size"})]
    if caption:
        children.append(Element("figcaption", [TextNode(caption)],
                                attrs={"class": "v-figure-caption"}))
    return Element("figure", children,
                   attrs={"class": "v-ai-image"},
                   runtime_binding="lightbox")


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def EvalTable(rows: Any, *, key: str, columns: list[Column] | None = None,
              page_size: int | None = 20) -> Element:
    """The evaluation table: the data grid preconfigured for eval runs
    (filterable, exportable, selectable by run)."""
    return DataGrid(rows, columns=columns, key=key, filterable=True,
                    selectable=True, export=True, page_size=page_size)


def Trace(spans: list[dict], *, label: str = "Trace") -> Element:
    """The trace viewer: a waterfall of spans with durations and
    status. Spans are ``{"name", "start_ms", "duration_ms", "status"?,
    "depth"?}`` and render as positioned bars, no JavaScript."""
    if not spans:
        raise VirelCompileError("Trace needs at least one span.")
    total = max(span.get("start_ms", 0) + span.get("duration_ms", 0)
                for span in spans) or 1
    rows: list[Node] = []
    for span in spans:
        start = float(span.get("start_ms", 0))
        duration = float(span.get("duration_ms", 0))
        status = str(span.get("status", "done"))
        depth = int(span.get("depth", 0))
        left = 100 * start / total
        width = max(0.75, 100 * duration / total)
        rows.append(Element("div", [
            Element("span", [TextNode(str(span.get("name", "span")))],
                    attrs={"class": "v-ai-span-name",
                           "style": f"padding-inline-start: {depth * 16}px"}),
            Element("div", [Element("div", attrs={
                "class": f"v-ai-span-bar v-ai-span-{status}",
                "style": f"margin-inline-start: {left:.2f}%; "
                         f"width: {width:.2f}%",
                "title": f"{span.get('name')}: {duration:g} ms",
            })], attrs={"class": "v-ai-span-track"}),
            Element("span", [TextNode(f"{duration:g} ms")],
                    attrs={"class": "v-ai-span-ms"}),
        ], attrs={"class": "v-ai-span"}))
    return Element("div", rows, attrs={"class": "v-ai-trace",
                                       "role": "img", "aria-label": label})


def Feedback(state: Any, *, label: str = "Rate this response") -> Element:
    """The feedback controls: thumbs writing "up" or "down" into state,
    with aria-pressed tracking the value reactively."""
    from .expr import Compare, Handler, Lit, SetOp

    def thumb(value: str, icon: str) -> Element:
        return Element("button", [Icon(icon, size=15)], attrs={
            "type": "button",
            "class": "v-btn v-btn-neutral v-btn-sm v-ai-thumb",
            "aria-label": f"Thumbs {value}",
            "aria-pressed": cond(Compare("==", lift(state), Lit(value)),
                                 "true", "false"),
        }, events={"click": Handler([SetOp(state.name, Lit(value))])})

    return Element("div", [
        Element("span", [TextNode(label)], attrs={"class": "v-ai-hint"}),
        thumb("up", "thumbs-up"),
        thumb("down", "thumbs-down"),
    ], attrs={"class": "v-ai-feedback", "role": "group",
              "aria-label": label})


def Approval(*, title: str, on_approve: Callable[[], None],
             on_reject: Callable[[], None], description: str | None = None,
             approve_label: str = "Approve", reject_label: str = "Reject",
             destructive: bool = False) -> Element:
    """The human approval step: an explicit gate before an action runs.
    Nothing is preselected, and a destructive approval renders as
    danger."""
    body: list[Node] = [Element("strong", [TextNode(title)])]
    if description:
        body.append(Text(description, muted=True, size="sm"))
    body.append(Row(
        Button(reject_label, on_click=on_reject),
        Button(approve_label, on_click=on_approve,
               intent="danger" if destructive else "primary"),
        gap=3, justify="end",
    ))
    return Element("div", body, attrs={
        "class": "v-ai-approval v-card v-stack",
        "style": "gap: calc(var(--v-space) * 3)",
        "role": "group", "aria-label": title})


def JobProgress(*, status: Any, progress: Any = None,
                label: str = "Job") -> Element:
    """Long-running job progress: a status ("pending", "running",
    "done", "failed") plus an optional percentage, both typically fed
    by a streaming action or subscription."""
    badges: list[Node] = []
    for value, intent in _INTENT_BY_STATUS.items():
        badges.append(When(Compare_eq(status, value),
                           then=Badge(value, intent=intent)))
    children: list[Node] = [Row(
        Element("span", [TextNode(label)], attrs={"class": "v-ai-hint"}),
        *badges,
        When(Compare_eq(status, "running"), then=Spinner()),
        gap=3,
    )]
    if progress is not None:
        children.append(Progress(progress, max=100,
                                 label=f"{label} progress"))
    return Element("div", children, attrs={
        "class": "v-ai-job v-stack",
        "style": "gap: calc(var(--v-space) * 2)"})


def Compare_eq(state: Any, value: str):
    from .expr import Compare, Lit
    return Compare("==", lift(state), Lit(value))
