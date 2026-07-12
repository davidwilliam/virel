"""Animation API (SPEC 10.8)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError
from virel.theme import build_stylesheet


def test_spring_compiles_to_css_linear_easing():
    spring = ui.spring(stiffness=170, damping=24)
    assert spring.css.startswith("linear(0, ")
    assert spring.css.endswith(", 1)")
    assert spring.natural_duration and 200 < spring.natural_duration < 3000
    # A stiffer spring settles faster.
    stiff = ui.spring(stiffness=600, damping=40)
    assert stiff.natural_duration < spring.natural_duration
    # An underdamped spring overshoots past 1.
    bouncy = ui.spring(stiffness=300, damping=12)
    assert any(float(v) > 1.01 for v in
               bouncy.css.removeprefix("linear(").removesuffix(")").split(", "))
    with pytest.raises(VirelCompileError, match="positive"):
        ui.spring(stiffness=-1)


def test_keyframes_compile_and_deduplicate():
    pulse = ui.keyframes({"0%": {"opacity": 1}, "50%": {"opacity": 0.4},
                          "100%": {"opacity": 1}})
    again = ui.keyframes({"0%": {"opacity": 1}, "50%": {"opacity": 0.4},
                          "100%": {"opacity": 1}})
    assert pulse.name == again.name
    assert pulse.css in build_stylesheet()
    slide = ui.keyframes({"from": {"transform": "translateY(8px)"},
                          "to": {"transform": "translateY(0)"}})
    assert "transform: translateY(8px)" in slide.css


def test_keyframes_are_validated():
    with pytest.raises(VirelCompileError, match="stop"):
        ui.keyframes({"150%": {"opacity": 0}})
    with pytest.raises(VirelCompileError, match="Unknown keyframe property"):
        ui.keyframes({"0%": {"position": "fixed"}})
    with pytest.raises(VirelCompileError, match="not allowed"):
        ui.keyframes({"0%": {"transform": "translateX(0); position: fixed"}})


def test_animation_and_transition_style_properties():
    pulse = ui.keyframes({"from": {"opacity": 1}, "to": {"opacity": 0.4}})
    s = ui.style(
        transition=ui.transition("transform", "box-shadow", duration=180),
        animation=ui.animation(pulse, duration=1200, easing="in-out",
                               iterations="infinite"),
    )
    assert "transition: transform 180ms" in s.css
    assert f"infinite normal both {pulse.name}" in s.css
    with pytest.raises(VirelCompileError, match="Cannot transition"):
        ui.transition("display")
    with pytest.raises(VirelCompileError, match="raw string"):
        ui.style(transition="all 200ms")
    with pytest.raises(VirelCompileError, match="raw string"):
        ui.style(animation="spin 1s infinite")


def test_essential_animations_survive_reduced_motion():
    pulse = ui.keyframes({"from": {"opacity": 1}, "to": {"opacity": 0.4}})
    s = ui.style(animation=ui.animation(pulse, duration=900, essential=True))
    assert "@media (prefers-reduced-motion: reduce)" in s.css
    assert "animation-duration: 900ms !important" in s.css


def test_spring_supplies_its_natural_duration():
    spring = ui.spring()
    value = ui.transition("transform", easing=spring)
    assert f"transform {spring.natural_duration}ms linear(" in value.css


def test_motion_presets_compile_enter_and_exit_classes():
    motion = ui.Motion(enter="fade-up", exit="fade", layout=True,
                       duration=240)
    config = motion.config()
    assert config["enter"].startswith("vm-")
    assert config["exit"].startswith("vm-")
    assert config["flip"] is True and config["flipDuration"] == 240
    css = build_stylesheet()
    assert f".{config['enter']}" in css
    assert "reverse both" in css  # exits play their frames reversed
    with pytest.raises(VirelCompileError, match="preset"):
        ui.Motion(enter="teleport")
    with pytest.raises(VirelCompileError, match="enter="):
        ui.Motion()


def test_motion_reduced_none_removes_the_animation():
    motion = ui.Motion(enter="fade", reduced="none")
    css = build_stylesheet()
    assert (f".{motion.config()['enter']} {{ animation: none !important; }}"
            in css)


def test_when_animate_emits_motion_config():
    from virel.compiler import compile_page
    from virel.registry import active_registry

    @ui.page("/motion")
    def motion_page():
        show = ui.state(True)
        return ui.Page(
            ui.Button("Toggle", on_click=lambda: show.set(False)),
            ui.When(show, then=ui.Text("Panel"),
                    animate=ui.Motion(enter="fade-up", exit="fade")),
        )

    result = compile_page(active_registry().pages["/motion"])
    assert '"enter": "vm-' in result.js
    assert '"exit": "vm-' in result.js
    when_ir = result.ir["tree"]["children"][-1]
    assert when_ir["kind"] == "when" and "motion" in when_ir


def test_each_animate_emits_motion_config():
    from virel.compiler import compile_page
    from virel.registry import active_registry

    @ui.page("/list-motion")
    def list_page():
        items = ui.state([{"id": 1, "name": "a"}])
        return ui.Page(
            ui.Button("Clear", on_click=lambda: items.set([])),
            ui.Each(items, render=lambda item: ui.Text(item["name"]),
                    key=lambda item: item["id"],
                    animate=ui.Motion(enter="slide-right", exit="fade",
                                      layout=True)),
        )

    result = compile_page(active_registry().pages["/list-motion"])
    assert '"flip": true' in result.js
    assert "$.bindList(" in result.js


def test_animate_accepts_preset_shorthand():
    node = ui.When(True, then=ui.Text("x"), animate="scale")
    assert node.motion.enter_class and node.motion.exit_class
    with pytest.raises(VirelCompileError, match="animate="):
        ui.When(True, then=ui.Text("x"), animate=42)


def test_swipeable_markup_and_handler():
    captured = {}

    @ui.page("/swipe-markup")
    def swipe_markup():
        dismissed = ui.state(False)
        card = ui.Swipeable(ui.Text("row"),
                            on_dismiss=lambda: dismissed.set(True),
                            direction="left", threshold=0.4)
        captured["card"] = card
        return ui.Page(card)

    ui.test.render(swipe_markup)
    card = captured["card"]
    assert card.attrs["data-direction"] == "left"
    assert card.attrs["data-threshold"] == "0.4"
    assert card.attrs["tabindex"] == "0"
    assert "virel-dismiss" in card.events
    assert card.runtime_binding == "swipeable"

    @ui.page("/swipe-bad")
    def swipe_bad():
        dismissed = ui.state(False)
        return ui.Page(ui.Swipeable(
            ui.Text("x"), on_dismiss=lambda: dismissed.set(True),
            direction="up"))

    with pytest.raises(VirelCompileError, match="direction"):
        ui.test.render(swipe_bad)


def test_swipe_dismiss_executes_in_python_tests():
    @ui.page("/swipe")
    def swipe_page():
        gone = ui.state(False)
        return ui.Page(
            ui.When(ui.not_(gone), then=ui.Swipeable(
                ui.Text("Swipe me"), on_dismiss=lambda: gone.set(True))),
            ui.When(gone, then=ui.Text("Dismissed")),
        )

    view = ui.test.render(swipe_page)
    view.get_by_text("Swipe me")  # present before the gesture
    view.get_by_role("group").emit("virel-dismiss")
    view.get_by_text("Dismissed")
