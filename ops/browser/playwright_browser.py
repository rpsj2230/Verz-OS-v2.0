"""The runner container's entry point: Chromium through Playwright, driven by the runner.

This file is copied into the runner image at `/opt/brain-runner/playwright_browser.py` by
`ops/browser/Dockerfile` and is not part of the `brain` package. It imports Playwright, which the
application does not depend on, and it can only run where a browser is installed, which is not
the machine it was written on. So it is kept as small as the `Browser` protocol allows, every
decision about what may happen lives in `brain.browsing`, and what this file does is the
rehearsal in `ops/browser/REHEARSAL.md`.

**The DevTools session is opened over Playwright's pipe and held here for the process's life.**
`chromium.launch` talks to the browser over a pipe, not a debugging port, so there is no socket for
anything else to connect to. `new_cdp_session` gives this process a DevTools session on the one
page, and every read of the tree and every input event goes through it.

**Actions address nodes by backend id, never by selector.** A click resolves the node's box through
`DOM.getBoxModel` and dispatches mouse events at its centre; typing focuses the node and inserts
text; an upload sets the file input's files from a file written to the container's own tmpfs. A
selector would be something the page can change the meaning of; a backend id is not.

**Every picture is taken with form controls painted over.** `Page.captureScreenshot` is preceded
by a style that paints every input, textarea, select and editable element solid, and followed by
removing it, so the value typed into a field is never in the pixels.

Chromium's own sandbox is switched off, and gVisor is the sandbox: whether Chromium's namespaces
and seccomp work under gVisor is the first thing the rehearsal checks. The TLS errors Chromium is
told to ignore are those of the one peer it can reach, the run's own egress proxy, which verifies
every upstream certificate itself.

Task ids: M19.1.2, M19.1.3
"""

from __future__ import annotations

import base64
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from brain.browsing.runner import drive
from brain.browsing.sandbox import PROXY_ADDRESS
from brain.browsing.targets import Verb

#: The style that paints every form control solid before a picture is taken.
MASK = (
    "input, textarea, select, [contenteditable], [contenteditable] * "
    "{ color: transparent !important; text-shadow: none !important; "
    "background: #000 !important; caret-color: transparent !important; }"
)

#: How long a navigation may take, in milliseconds.
NAVIGATION_TIMEOUT_MS = 30_000


class PlaywrightBrowser:
    """`brain.browsing.runner.Browser` over one Playwright page and its DevTools session."""

    def __init__(self, page: Any, session: Any) -> None:
        self.page = page
        self.session = session

    def navigate(self, url: str) -> None:
        self.page.goto(url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS)

    def origin(self) -> str:
        return str(self.page.evaluate("() => window.location.origin"))

    def accessibility_tree(self) -> Mapping[str, Any]:
        tree: Mapping[str, Any] = self.session.send("Accessibility.getFullAXTree", {})
        return tree

    def act(self, verb: Verb, ref: str, text: str) -> None:
        backend = int(ref.removeprefix("n"))
        if verb in (Verb.CLICK, Verb.SUBMIT):
            self.session.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend})
            quad = self.session.send("DOM.getBoxModel", {"backendNodeId": backend})["model"][
                "content"
            ]
            x = sum(quad[0::2]) / 4
            y = sum(quad[1::2]) / 4
            for event in ("mousePressed", "mouseReleased"):
                self.session.send(
                    "Input.dispatchMouseEvent",
                    {"type": event, "x": x, "y": y, "button": "left", "clickCount": 1},
                )
        elif verb is Verb.TYPE:
            self.session.send("DOM.focus", {"backendNodeId": backend})
            self.session.send("Input.insertText", {"text": text})
        elif verb is Verb.UPLOAD:
            path = Path(f"/tmp/upload-{backend}")  # noqa: S108 - the container's own tmpfs
            path.write_bytes(base64.b64decode(text))
            self.session.send(
                "DOM.setFileInputFiles", {"files": [str(path)], "backendNodeId": backend}
            )
        else:
            msg = f"{verb.value} is not an action on a node"
            raise ValueError(msg)

    def capture(self) -> bytes:
        handle = self.page.add_style_tag(content=MASK)
        try:
            shot = self.session.send("Page.captureScreenshot", {"format": "png"})
        finally:
            handle.evaluate("node => node.remove()")
        return base64.b64decode(shot["data"])


class StandardStreams:
    """`brain.browsing.runner.Channel` over this process's standard input and output."""

    def receive(self) -> bytes:
        return sys.stdin.buffer.readline()

    def emit(self, line: bytes) -> None:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            proxy={"server": PROXY_ADDRESS},
            chromium_sandbox=False,
            args=["--no-first-run", "--disable-background-networking"],
        )
        context = browser.new_context(
            ignore_https_errors=True, accept_downloads=False, service_workers="block"
        )
        page = context.new_page()
        session = context.new_cdp_session(page)
        ended = drive(StandardStreams(), PlaywrightBrowser(page, session))
        context.close()
        browser.close()
    os.write(2, f"{ended.reason}\n".encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
