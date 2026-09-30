"""The shape one screen of a connect flow is served in, for every source that has one.

`brain.ops.connect_steps` holds the step and its picture; this is the same thing as the API sends
it, so Connect Lark and every other connector's flow are one schema and the console draws them with
one component. A field here is a field there and nothing else: the picture stays a description the
console draws (see `brain.ops.connect_steps.A_PICTURE_IS_AN_OUTLINE_THAT_NAMES_WHERE_TO_PRESS`).

Task ids: M11.9.4, M27.11.9, M10.5.6
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from brain.ops.connect_steps import GuideStep, Sketch


class SketchLineView(BaseModel):
    """One row of a step's picture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    label: str
    value: str
    mark: bool


class SketchView(BaseModel):
    """A simplified outline of the screen a step happens on, drawn by the console."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    place: str
    heading: str
    menu: list[str]
    menu_mark: str
    tabs: list[str]
    tab_mark: str
    lines: list[SketchLineView]
    button: str


class ChoiceView(BaseModel):
    """One path a step offers: its key, and the words on its button."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str


class GuideStepView(BaseModel):
    """One screen of a connect flow: its key, its words, its picture, its link, what it asks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    title: str
    text: str
    sketch: SketchView
    #: The vendor's own page for this step, or empty where it has none.
    link: str
    link_label: str
    #: The values this screen collects, by the names the route that receives them judges.
    asks: list[str]
    #: A text to paste into the vendor whole, and its button's words; empty when none.
    copy_text: str = ""
    copy_label: str = ""
    #: The path this step belongs to where the steps branch; empty for every path.
    path: str = ""
    #: The paths this step offers, each a key and its button's words.
    choices: list[ChoiceView] = []


def sketch_view(sketch: Sketch) -> SketchView:
    return SketchView(
        place=sketch.place,
        heading=sketch.heading,
        menu=list(sketch.menu),
        menu_mark=sketch.menu_mark,
        tabs=list(sketch.tabs),
        tab_mark=sketch.tab_mark,
        lines=[
            SketchLineView(kind=one.kind.value, label=one.label, value=one.value, mark=one.mark)
            for one in sketch.lines
        ],
        button=sketch.button,
    )


def step_view(step: GuideStep) -> GuideStepView:
    return GuideStepView(
        key=step.key,
        title=step.title,
        text=step.text,
        sketch=sketch_view(step.sketch),
        link=step.link,
        link_label=step.link_label,
        asks=list(step.asks),
        copy_text=step.copy_text,
        copy_label=step.copy_label,
        path=step.path,
        choices=[ChoiceView(key=key, label=label) for key, label in step.choices],
    )
