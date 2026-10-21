"""The desktop runner container's entry point: one allowed application, driven through the
accessibility bus, behind the same line protocol and the same enforcer as a browser run.

Copied into the runner image at `/opt/desktop-runner/desktop_runner.py` by `ops/desktop/Dockerfile`
and not part of the `brain` package, because it imports PyGObject and Pillow, which the application
does not depend on, and it can only run where a display and an accessibility bus can be started.

**Written, never run.** Nothing on the machine this was written on can start a display, a bus or a
gVisor container, so this file is the intended behaviour and not a measured one. What is measured is
everything it leans on: `brain.browsing.runner.drive` (the loop, the enforcer, the once-only write),
`brain.browsing.desktop_app.accessibility_tree` (the toolkit's widgets read as the browser's tree)
and the sandbox it runs in. Until a launcher starts this image, nothing reaches it, and the Profile
still says computer use is not offered.

**What starts is the declared command and nothing a message names.** `--command` is checked against
the same pattern the declaration was (`desktop_app.COMMAND_RE`) before anything is launched, so a
runner given another path exits at once.

**Widgets are numbered by this process and the numbers are not reused.** Each distinct accessible
object is given the next number the first time it is seen; an application that destroys a button and
makes another presents a new number, and the old reference is refused as unknown, as a replaced
button is in the browser.

**A picture is taken after every editable widget's extent is painted over, or it is not taken.** If
the toolkit cannot say where such a widget is, `capture` raises rather than returning pixels it
cannot promise are masked, and the run ends on that.

Task ids: M19.8.1
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from typing import Any

from brain.browsing.desktop_app import (
    COMMAND_RE,
    MASKED_ROLES,
    ORIGIN_VARIABLE,
    VIRTUAL_DISPLAY,
    accessibility_tree,
    window_path,
)
from brain.browsing.runner import drive
from brain.browsing.targets import Verb

#: How long the application is given to show a window, in seconds.
STARTUP_SECONDS = 20.0


class AtspiDesktop:
    """`brain.browsing.runner.Browser` over one application's accessibility tree."""

    def __init__(self, atspi: Any, application: Any, origin: str) -> None:
        self.atspi = atspi
        self.application = application
        self.declared_origin = origin
        self.numbers: dict[int, int] = {}
        self.widgets: dict[int, Any] = {}

    def _number(self, widget: Any) -> int:
        key = hash(widget)
        if key not in self.numbers:
            self.numbers[key] = len(self.numbers) + 1
            self.widgets[self.numbers[key]] = widget
        return self.numbers[key]

    def _walk(self, widget: Any) -> list[Any]:
        found = [widget]
        for index in range(widget.get_child_count()):
            child = widget.get_child_at_index(index)
            if child is not None:
                found.extend(self._walk(child))
        return found

    def navigate(self, url: str) -> None:
        wanted = window_path(url).strip("/")
        for window in self._walk(self.application):
            if window.get_role_name() == "frame" and (not wanted or window.get_name() == wanted):
                self.atspi.Component.grab_focus(window)
                return
        msg = "the window a surface names is not open"
        raise RuntimeError(msg)

    def origin(self) -> str:
        return self.declared_origin

    def accessibility_tree(self) -> Mapping[str, Any]:
        entries = [
            (self._number(one), one.get_role_name(), one.get_name() or "")
            for one in self._walk(self.application)
        ]
        return accessibility_tree(entries)

    def act(self, verb: Verb, ref: str, text: str) -> None:
        widget = self.widgets[int(ref.removeprefix("n"))]
        if verb in (Verb.CLICK, Verb.SUBMIT):
            self.atspi.Action.do_action(widget, 0)
        elif verb is Verb.TYPE:
            self.atspi.Component.grab_focus(widget)
            self.atspi.EditableText.set_text_contents(widget, text)
        else:
            msg = f"{verb.value} is not an action on a widget"
            raise ValueError(msg)

    def capture(self) -> bytes:
        from PIL import ImageDraw, ImageGrab

        picture = ImageGrab.grab(xdisplay=VIRTUAL_DISPLAY)
        painter = ImageDraw.Draw(picture)
        for widget in self._walk(self.application):
            if widget.get_role_name() not in MASKED_ROLES:
                continue
            extents = self.atspi.Component.get_extents(widget, self.atspi.CoordType.SCREEN)
            if extents is None:
                msg = "an editable widget has no extent, so a picture cannot be masked"
                raise RuntimeError(msg)
            painter.rectangle(
                (extents.x, extents.y, extents.x + extents.width, extents.y + extents.height),
                fill="black",
            )
        out = io.BytesIO()
        picture.save(out, format="PNG")
        return out.getvalue()


class StandardStreams:
    """`brain.browsing.runner.Channel` over this process's standard input and output."""

    def receive(self) -> bytes:
        return sys.stdin.buffer.readline()

    def emit(self, line: bytes) -> None:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


def main() -> int:
    arguments = sys.argv[1:]
    if len(arguments) != 2 or arguments[0] != "--command" or not COMMAND_RE.match(arguments[1]):
        os.write(2, b"the runner was not given a declared command\n")
        return 2
    command = arguments[1]
    origin = os.environ[ORIGIN_VARIABLE]

    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    display = subprocess.Popen(  # noqa: S603 - a fixed argument list
        ["Xvfb", VIRTUAL_DISPLAY, "-screen", "0", "1280x800x24"]  # noqa: S607 - on the image's PATH
    )
    process = None
    try:
        time.sleep(1.0)
        process = subprocess.Popen([command])  # noqa: S603 - matched against COMMAND_RE above
        application = _application_of(Atspi, process.pid)
        ended = drive(StandardStreams(), AtspiDesktop(Atspi, application, origin))
        os.write(2, f"{ended.reason}\n".encode())
    finally:
        if process is not None:
            process.terminate()
        display.terminate()
    return 0


def _application_of(atspi: Any, pid: int) -> Any:
    """The accessible application whose process is the one this runner started."""
    deadline = time.monotonic() + STARTUP_SECONDS
    desktop = atspi.get_desktop(0)
    while time.monotonic() < deadline:
        for index in range(desktop.get_child_count()):
            candidate = desktop.get_child_at_index(index)
            if candidate is not None and candidate.get_process_id() == pid:
                return candidate
        time.sleep(0.5)
    msg = "the application showed no window in time"
    raise RuntimeError(msg)


if __name__ == "__main__":
    raise SystemExit(main())
