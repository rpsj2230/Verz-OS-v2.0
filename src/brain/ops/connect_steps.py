"""One step of connecting a source: its words, where it happens, and a picture of that screen.

The owner asked on 2026-09-29 for Connect Lark as screens an administrator walks through one at a
time, each with a picture, and then for every other connector the same way. The words of each step
already lived on the server (`brain.ops.lark_connect.steps_for`), so a vendor renaming a menu is
mended once. This module is the shape every connector's steps now share, so the console draws one
flow for all of them and the steps, their pictures and their links stay in one place per source.

**A picture is a description the console draws, not an image file.** A `Sketch` names what the
screen is (the place in its address bar), its left menu with the one item to press marked, the
page's heading and tabs, a few rows, and the one button to press. The console turns it into SVG in
the product's own colours. Three things follow and each was the reason:

- **It survives a vendor restyle.** A screenshot is wrong the day the vendor moves a button, and it
  cannot be taken without the owner's logins. An outline says where to look (the menu entry, the
  button's words) and nothing about how it is painted, so it goes stale only when the words do,
  and the words are the step's own text, reviewed together.
- **It carries no vendor artwork.** No logo, no copied illustration, nothing to license: boxes,
  lines and the words a person reads on the vendor's screen.
- **It is data a test can read.** A marked menu item and a marked button are fields, so a test
  holds that the picture of "add the permissions" marks the permissions page, which no test could
  say about a PNG. And the console may render no raw HTML (`scripts/check-boundaries.mjs`), which
  rules out serving an SVG document to be pasted in.

Rejected: SVG files beside the console, one per step. The picture and the step's words would live
in two trees, and a step reworded here would keep an old picture there.

**A step says which values it collects and nothing about how they are typed.** `asks` names the
fields a screen gathers (an App ID, a key, a setting); the console owns the inputs and the secret
field, and the route that receives them judges them. So a step definition can never become a
second validator.

Task ids: M11.9.4, M27.11.9
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

# ------------------------------------------------------------------ written-down reasons

#: Why a step's picture is an outline and not a screenshot.
A_PICTURE_IS_AN_OUTLINE_THAT_NAMES_WHERE_TO_PRESS: Final = (
    "Each step's picture is a simplified outline of the screen it happens on: the menu with the "
    "item to open marked, the page's heading and the button to press marked. It is drawn from "
    "the step's own definition in the product's colours, carries no vendor artwork, and goes "
    "stale only when the words a person reads on that screen change."
)

#: The longest text a picture's element holds. A picture labels, it does not explain.
MAX_SKETCH_WORDS: Final = 48


class LineKind(enum.StrEnum):
    """What one row inside a picture is."""

    #: A labelled box holding a value, such as an App ID with a copy icon.
    FIELD = "field"
    #: A switch, on or off.
    TOGGLE = "toggle"
    #: A ticked or unticked item in a list, such as one permission.
    ITEM = "item"
    #: A line of plain text on the page.
    TEXT = "text"


@dataclass(frozen=True)
class SketchLine:
    """One row of a picture. `mark` draws it as the thing to look at."""

    kind: LineKind
    label: str
    value: str = ""
    mark: bool = False

    def __post_init__(self) -> None:
        for one in (self.label, self.value):
            if len(one) > MAX_SKETCH_WORDS:
                msg = f"a picture's row says {one!r}, which is a sentence and not a label"
                raise ValueError(msg)


@dataclass(frozen=True)
class Sketch:
    """A simplified outline of the screen a step happens on. See the module docstring.

    `place` is what the window's address bar shows, in words rather than a host, so a picture is
    the same on every platform. At most one menu item, one tab and one button are marked, and a
    marked menu item or tab names one that is drawn.
    """

    place: str
    heading: str
    menu: tuple[str, ...] = ()
    menu_mark: str = ""
    tabs: tuple[str, ...] = ()
    tab_mark: str = ""
    lines: tuple[SketchLine, ...] = ()
    button: str = ""

    def __post_init__(self) -> None:
        if self.menu_mark and self.menu_mark not in self.menu:
            msg = f"the picture marks {self.menu_mark!r}, which is not in its menu"
            raise ValueError(msg)
        if self.tab_mark and self.tab_mark not in self.tabs:
            msg = f"the picture marks the tab {self.tab_mark!r}, which is not drawn"
            raise ValueError(msg)
        for one in (self.place, self.heading, self.button, *self.menu, *self.tabs):
            if len(one) > MAX_SKETCH_WORDS:
                msg = f"a picture says {one!r}, which is a sentence and not a label"
                raise ValueError(msg)

    def marks(self) -> tuple[str, ...]:
        """Every element the picture marks, in reading order: the menu item, tab, rows, button."""
        rows = tuple(one.label for one in self.lines if one.mark)
        return tuple(
            one for one in (self.menu_mark, self.tab_mark, *rows, self.button) if one.strip()
        )


@dataclass(frozen=True)
class GuideStep:
    """One screen of a connect flow.

    `key` is stable and is what a test's verdict names when it sends somebody back; `link` opens
    the vendor's own page for this step where the vendor has one, and is empty otherwise; `asks`
    names the values this screen collects, in the order they are drawn.
    """

    key: str
    title: str
    text: str
    sketch: Sketch
    link: str = ""
    link_label: str = ""
    asks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (self.key.strip() and self.title.strip() and self.text.strip()):
            msg = "a step needs a key, a title and what to do"
            raise ValueError(msg)
        if self.link and not self.link.startswith("https://"):
            msg = f"step {self.key!r} links to {self.link!r}, which is not an https address"
            raise ValueError(msg)
        if bool(self.link) != bool(self.link_label.strip()):
            msg = f"step {self.key!r} must say what its link opens, and only when it has one"
            raise ValueError(msg)


def keyed(steps: tuple[GuideStep, ...]) -> tuple[GuideStep, ...]:
    """The steps, refused when two share a key, because a test sends a person back by key."""
    keys = [one.key for one in steps]
    if len(keys) != len(set(keys)):
        msg = f"two steps share a key: {sorted(one for one in keys if keys.count(one) > 1)}"
        raise ValueError(msg)
    return steps
