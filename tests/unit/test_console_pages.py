"""The register of console pages is sound, and says only what it can show.

`docs/console-pages.json` records, for each primary page of the console, whether it is built on the
shared parts, which screen of the key screens page was drawn for it, and whether a walk-through of
it has passed on the owner's install. A page counts as rebuilt only on all three, in that order.
The first half of this file holds the shipped register against the menu the console serves and the
screens the design draws; the second half holds the rules on small registers written for the test,
each with the case beside it that is allowed, because a guard tested only by its refusals is
satisfied by one that refuses everything.

Task ids: M27.16.1, M27.16.4, M27.16.5
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain import docs_routes
from brain.app import create_app
from brain.console_pages import (
    AGENT_PAGE,
    PAGES_IN_DOCS,
    PageRow,
    PagesRegister,
    PageState,
    RegisterError,
    WalkThrough,
    findings,
    load_pages,
    menu_addresses,
    pages_page,
    screens_drawn,
)

DOCS = Path(__file__).resolve().parents[2] / "docs"

#: A release the walk-throughs below pass on. Any seven hex digits would do.
RELEASE = "abc1234"


def row(
    address: str = "/people",
    *,
    screen: str | None = "screen-10",
    kit: bool = True,
    walked: bool = False,
) -> PageRow:
    return PageRow(
        address=address,
        name="A page",
        module="A module",
        screen=screen,
        on_the_shared_parts=kit,
        walked=WalkThrough(on="2999-01-02", release=RELEASE) if walked else None,
    )


# ----------------------------------------------------------------- the shipped register


def test_the_shipped_register_is_sound_against_the_menu_and_the_screens_the_design_draws() -> None:
    """Every menu entry has a row, no row names a page the menu lacks, every screen a row names is
    drawn on the key screens page, and no page has a walk-through before it is rebuilt. Delete
    this and a page added to the menu is tracked by nobody, which is how a console grows pages no
    design was drawn for."""
    register = load_pages(DOCS / PAGES_IN_DOCS)
    assert findings(register, drawn=screens_drawn(DOCS), menu=menu_addresses()) == []


def test_every_primary_page_has_a_screen_drawn_and_the_agent_page_is_one_of_them() -> None:
    """M27.16.4: one designed screen for each primary page, the agent detail page included. Delete
    this and the key screens page can stop short of the console it designs without a test going
    red, which is the state it was in with eleven pages drawn of forty-two."""
    register = load_pages(DOCS / PAGES_IN_DOCS)
    assert AGENT_PAGE in {one.address for one in register.pages}
    assert [one.address for one in register.pages if one.screen is None] == []


def test_the_register_does_not_call_a_page_rebuilt_that_nobody_has_walked() -> None:
    """The walk-through is a person's, so the register starts with none and a page is rebuilt only
    when one is recorded. Delete this and a register edited to say every page is rebuilt without a
    walk-through looks the same as one where each was walked, and the count on /build says so."""
    register = load_pages(DOCS / PAGES_IN_DOCS)
    for page in register.pages:
        assert (page.state is PageState.REBUILT) == (page.walked is not None)


def test_every_menu_address_is_listed_in_the_order_the_menu_draws_it() -> None:
    """The agent's page follows the roster, where a person reaches it. Delete this and the
    register can list the agent page last, and the build page reads as though it were a menu entry
    of its own."""
    menu = menu_addresses()
    assert menu[menu.index("/agents") + 1] == AGENT_PAGE
    assert len(set(menu)) == len(menu)


# ----------------------------------------------------------------------------- the states


@pytest.mark.parametrize(
    ("page", "state"),
    [
        (row(kit=False, screen=None), PageState.NOT_REBUILT),
        (row(kit=False), PageState.NOT_REBUILT),
        (row(screen=None), PageState.BUILT_BEFORE_ITS_SCREEN_WAS_DRAWN),
        (row(), PageState.AWAITING_WALK_THROUGH),
        (row(walked=True), PageState.REBUILT),
    ],
)
def test_a_page_is_named_for_the_first_thing_it_lacks(page: PageRow, state: PageState) -> None:
    """The five combinations of the three facts. Delete this and the order a page is rebuilt in
    (the shared parts, the screen, the walk-through) is held by no test, and the one the owner
    cares about, that the screen is drawn first, can be reordered silently."""
    assert page.state is state


# ---------------------------------------------------------------------------- the findings


def test_a_menu_entry_with_no_row_and_a_row_the_menu_does_not_serve_are_each_a_finding() -> None:
    """Both directions. Delete this and a page can be added to the menu with nothing tracking it,
    or removed and left in the register to be counted as a page there is."""
    register = PagesRegister(pages=(row("/people"), row("/gone")))
    problems = findings(register, drawn={"screen-10"}, menu=("/people", "/new"))
    assert problems == [
        "/new is served by the menu and has no row",
        "/gone has a row and the menu does not serve it",
    ]


def test_a_register_that_agrees_with_the_menu_and_the_screens_has_no_finding() -> None:
    """The permitted sibling of the refusal above. Delete this and a `findings` that returns a
    finding for everything passes every refusal test."""
    register = PagesRegister(pages=(row("/people"), row("/agents", walked=True)))
    assert findings(register, drawn={"screen-10"}, menu=("/people", "/agents")) == []


def test_a_row_naming_a_screen_the_design_does_not_draw_is_a_finding() -> None:
    """Delete this and a page can point at a screen that was renamed or never drawn, and the
    build page links to an anchor that is not there."""
    register = PagesRegister(pages=(row("/people", screen="screen-99"),))
    assert findings(register, drawn={"screen-10"}, menu=("/people",)) == [
        "/people names a screen that docs/screens.html does not draw"
    ]


@pytest.mark.parametrize("page", [row(kit=False, walked=True), row(screen=None, walked=True)])
def test_a_walk_through_recorded_before_the_page_is_rebuilt_is_a_finding(page: PageRow) -> None:
    """Both ways to get it wrong: not yet on the shared parts, or no screen yet. Delete this and
    the register accepts a walk-through of the old page and counts the new one rebuilt on it."""
    problems = findings(PagesRegister(pages=(page,)), drawn={"screen-10"}, menu=("/people",))
    assert len(problems) == 1
    assert problems[0].startswith("/people has a walk-through recorded and is not rebuilt")


def test_two_rows_for_one_address_are_a_finding() -> None:
    """Delete this and a page counted twice makes the register's total a figure about rows."""
    register = PagesRegister(pages=(row("/people"), row("/people")))
    assert findings(register, drawn={"screen-10"}, menu=("/people",)) == [
        "/people has more than one row"
    ]


# --------------------------------------------------------------------------- reading it


def write(tmp_path: Path, pages: object) -> Path:
    target = tmp_path / "console-pages.json"
    target.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return target


GOOD = {
    "address": "/people",
    "name": "People",
    "module": "People and access",
    "screen": "screen-10",
    "on_the_shared_parts": True,
    "walked": None,
}


def test_a_well_formed_row_is_read_and_a_walk_through_is_a_day_and_a_release(
    tmp_path: Path,
) -> None:
    """Delete this and the reader is tested only on what it refuses."""
    walked = {**GOOD, "walked": {"on": "2999-12-31", "release": RELEASE}}
    register = load_pages(write(tmp_path, [GOOD, {**walked, "address": "/agents"}]))
    assert [one.state for one in register.pages] == [
        PageState.AWAITING_WALK_THROUGH,
        PageState.REBUILT,
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "extra": 1},
        {key: value for key, value in GOOD.items() if key != "screen"},
        {**GOOD, "on_the_shared_parts": "yes"},
        {**GOOD, "address": ""},
        {**GOOD, "walked": {"on": "2999-13-45", "release": RELEASE}},
        {**GOOD, "walked": {"on": "yesterday", "release": RELEASE}},
        {**GOOD, "walked": {"on": "2999-01-01", "release": "main"}},
        {**GOOD, "walked": {"on": "2999-01-01"}},
        "not an object",
    ],
)
def test_a_malformed_row_is_refused_in_words(tmp_path: Path, bad: object) -> None:
    """Delete this and a typo in the register (a date in no calendar, a release that is a branch
    name) is read as a record that a walk-through passed."""
    with pytest.raises(RegisterError):
        load_pages(write(tmp_path, [bad]))


def test_a_file_that_is_not_the_register_is_refused(tmp_path: Path) -> None:
    """Delete this and an absent or garbled register is read as an empty one, which the build page
    would show as a console with nothing left to rebuild."""
    broken = tmp_path / "console-pages.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(RegisterError):
        load_pages(broken)
    with pytest.raises(RegisterError):
        load_pages(tmp_path / "missing.json")


# ------------------------------------------------------------------------------- the page


def test_the_build_page_counts_the_pages_by_what_they_lack_and_links_each_screen() -> None:
    """The words a reader gets: how many are rebuilt, how many are not, and a link to the screen
    that was drawn. Delete this and the page can say nothing about which pages are rebuilt, which
    is the leaf."""
    text = pages_page(
        PagesRegister(
            pages=(row("/a", walked=True), row("/b"), row("/c", screen=None), row("/d", kit=False))
        )
    )
    assert "**1 of 4 pages are rebuilt.**" in text
    assert "1 are built to a drawn screen and await a walk-through" in text
    assert "1 were built before their screen was drawn" in text
    assert "1 are not on the shared parts" in text
    assert "[screen-10](/build/screens#screen-10)" in text
    assert "passed 2999-01-02 on abc1234" in text


def test_the_build_pages_route_serves_the_register_and_a_missing_one_is_a_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route and its refusal. Delete this and a page that serves an empty body for an absent
    register reads as a console with nothing to rebuild."""
    client = TestClient(create_app())
    served = client.get("/build/pages")
    assert served.status_code == 200
    assert "Console pages" in served.text
    monkeypatch.setattr(docs_routes, "DOCS", tmp_path)
    assert client.get("/build/pages").status_code == 404


def test_the_build_status_page_links_to_the_console_pages() -> None:
    """Delete this and the page exists at an address nobody is sent to."""
    assert 'href="/build/pages"' in TestClient(create_app()).get("/build").text
