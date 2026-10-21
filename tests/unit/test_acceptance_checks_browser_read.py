"""The read install check: what it names, that it is never a pass, and that it fails for each way
the read could return more, less or the wrong thing.

The runner is the product's own and the page a stand-in, as in the other browser checks. The
database half skips when `DATABASE_URL` is unset, as every `needs_db` test does; the cases that need
no database break the product in the one place a guard sits and watch the check fail before it can
be not run.

Task ids: M19.7.1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_checks_browser_read as module
from brain.ops.acceptance import FAILED, NOT_RUN, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_read"
NAME = "a_browser_read_returns_only_the_declared_fields"
STAND_IN_TEXT: Final = "do not return this"


def test_the_check_names_the_read_leaf_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose its leaf with the page showing the same row, or sit
    outside the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M19.7.1",))]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_check_stands_after_the_desktop_check() -> None:
    """Delete this and two checks can take one place on the Install page."""
    from brain.ops import acceptance_checks_desktop

    assert module.CHECK_ORDER > acceptance_checks_desktop.CHECK_ORDER


def test_the_page_shows_the_declared_field_and_text_nobody_declared() -> None:
    """The check is only worth as much as its page: it has to show something that must not come
    back. Delete this and a page of one declared field passes a tool that returns the page."""
    shown = [name for _, name in module.SHOWN]

    assert any(name.startswith(f"{module.DECLARED_FIELD}:") for name in shown)
    assert any(STAND_IN_TEXT in name for name in shown)
    assert len(shown) > len(module.EXPECTED)
    assert module.EXPECTED == ((module.DECLARED_FIELD, "INV-1042"),)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_read") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def outcome(url: str) -> tuple[str, str]:
    return run_checks(url, registered((MODULE,)))[NAME]


@pytest.mark.needs_db
def test_the_check_is_not_run_on_an_install_and_leaves_nothing_it_wrote(install: str) -> None:
    """**The module as the worker runs it.** The first half passes on the real schema, so the only
    thing between it and a pass is the sentence, which is the answer an install that has opened no
    page should give. Delete this and a check that cannot get that far, or one that commits a
    declaration or a switch to a client's install, reaches the owner first."""
    before = counts(install)

    assert outcome(install) == (NOT_RUN, module.A_PAGE_THAT_WAS_NEVER_OPENED_HAS_NOT_BEEN_READ)
    assert counts(install) == before


def fails_with(install: str, words: str) -> None:
    result = outcome(install)
    assert result[0] == FAILED and words in result[1], result


@pytest.mark.needs_db
def test_a_read_that_returns_the_whole_page_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a tool that returns every node of the page passes: the heading, the note
    nobody declared and the sentence a page addressed to a model."""
    from brain.browsing import read_tool

    def everything(snapshot: Any, fields: Any) -> Any:
        return tuple((node.role, node.name) for node in snapshot.nodes)

    monkeypatch.setattr(read_tool, "fields_read", everything)

    fails_with(install, "other than the declared field")


@pytest.mark.needs_db
def test_a_read_made_with_the_switch_off_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a read tool that stopped asking the browser switch passes."""
    from brain.browsing import read_tool

    async def always(session: Any) -> bool:
        return True

    monkeypatch.setattr(read_tool, "browser_runs_are_on", always)

    fails_with(install, "switched off")


@pytest.mark.needs_db
def test_a_run_that_is_not_recorded_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a driver that stopped writing recordings passes the check."""
    from brain.browsing import driver

    monkeypatch.setattr(driver, "write", lambda backend, recording: ())

    fails_with(install, "was not recorded")


@pytest.mark.needs_db
def test_a_session_never_closed_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a read that leaves its session counted as open, until the site is full,
    passes the check."""
    from brain.browsing import driver

    async def never(self: Any, *, run_id: str, at: Any, recording: Any) -> None:
        return None

    monkeypatch.setattr(driver.DatabaseLedger, "closed", never)

    fails_with(install, "counted as open")


@pytest.mark.needs_db
def test_a_read_that_opens_another_page_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a read that navigates somewhere its envelope did not name passes."""
    from brain.ops.acceptance_checks_browser import StandInPage

    def elsewhere(self: Any, url: str) -> None:
        self.navigated.append("https://elsewhere.invalid/")
        self.at = "https://acceptance-check.invalid"

    monkeypatch.setattr(StandInPage, "navigate", elsewhere)

    fails_with(install, "did not name")


@pytest.mark.needs_db
def test_a_read_of_a_surface_nobody_declared_that_is_answered_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a tool that answers for any surface a caller names passes."""
    from brain.browsing import read_tool
    from brain.browsing.sessions import BROWSER_SURFACE_OBJECT, SurfaceReading
    from brain.core.envelope import TypedResult

    real = read_tool.ReadSurfaceTool.handler

    def handler(self: Any) -> Any:
        inner = real(self)

        async def wrapped(request: Any, *, entitlement: Any, now: Any = None) -> Any:
            if request.surface == "no_such_surface":
                made = SurfaceReading(
                    entity=BROWSER_SURFACE_OBJECT, id="made.up", surface="s", origin="o"
                )
                return TypedResult(records=(made,), source="browser", fetched_at="")
            return await inner(request, entitlement=entitlement, now=now)

        return wrapped

    monkeypatch.setattr(read_tool.ReadSurfaceTool, "handler", handler)

    fails_with(install, "nobody should be answered")
