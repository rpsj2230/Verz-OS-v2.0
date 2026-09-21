"""Every console write's ledger entry carries the writer's reach digest and the request's trace.

The first test is the gate itself, over this repository: `brain.ops.write_attribution.findings` is
empty, which is what the CI step of the same name requires. The rest drive the sweep over a small
source tree written into a temporary directory, so each rule can be shown to fire and to stay
quiet: a route writing through a store with nothing setting the attribution is found, the same
route setting it is not, a store nobody calls is found, and an excuse nothing reaches is stale.

Task ids: M24.3.1
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from brain.ops.application_privileges import Catalogue, Use, migrations_catalogue
from brain.ops.write_attribution import (
    NOT_A_REQUEST_WITH_A_REACH,
    attributed_writes,
    findings,
)


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return migrations_catalogue()


def test_every_console_write_in_this_repository_sets_its_attribution(catalogue: Catalogue) -> None:
    """**The sweep M24.3.1 asks for, as the build runs it.** Delete this and a route added
    tomorrow can write a grant, a hold or a setting whose ledger entry carries thirty-two zeros
    and a transaction number, and verify, and nothing notices until somebody needs to know at
    what reach it was done."""
    assert findings(catalogue) == []


def test_the_tables_the_sweep_follows_are_the_ones_whose_triggers_read_the_reach(
    catalogue: Catalogue,
) -> None:
    """The grant, setting and budget triggers read the attribution; the sensitive read's trigger
    takes its digest from the row and is not followed. Delete this and the sweep can follow no
    table at all and report "ok" about nothing."""
    followed = attributed_writes(catalogue)
    assert ("gate.capability_grant", "INSERT") in followed
    assert ("ops.setting", "UPDATE") in followed
    assert ("ops.budget_version", "INSERT") in followed
    assert not any(table == "ops.sensitive_read" for table, _ in followed)


def _tree(root: Path, routes_body: str) -> Path:
    src = root / "src" / "brain"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "fake_store.py").write_text(
        dedent(
            """
            async def put(session):
                await session.execute("INSERT INTO ops.setting VALUES (1)")


            async def orphan(session):
                await session.execute("INSERT INTO ops.setting VALUES (2)")
            """
        ),
        encoding="utf-8",
    )
    (src / "fake_routes.py").write_text(dedent(routes_body), encoding="utf-8")
    return src


ROUTE_WITHOUT = """
    from brain.fake_store import put


    @router.post(PATH)
    async def save(session):
        await put(session)
"""

ROUTE_WITH = """
    from brain.attribution import attribute
    from brain.fake_store import put


    @router.post(PATH)
    async def save(session, asked):
        await attribute(session, asked)
        await put(session)
"""


def _writes(src: Path) -> list[Use]:
    text = (src / "fake_store.py").read_text(encoding="utf-8").splitlines()
    lines = [number for number, line in enumerate(text, 1) if "INSERT INTO" in line]
    return [Use("brain.fake_store", line, "ops.setting", "INSERT") for line in lines]


def test_a_route_writing_through_a_store_with_nothing_setting_the_attribution_is_found(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    """The shape every finding on 2026-09-21 had: the store writes, the route calls it, neither
    sets anything. Delete this and the sweep can stop following a write past its own module and
    pass every store in the tree."""
    src = _tree(tmp_path, ROUTE_WITHOUT)
    found = findings(catalogue, _writes(src)[:1], src=src, explained={})
    assert found == [
        "INSERT ops.setting via brain.fake_store:put <- brain.fake_routes:save: a route handler "
        "writes with nothing setting the attribution"
    ]


def test_the_same_route_setting_the_attribution_passes(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    """The positive sibling. Delete this and the finding above is satisfied by a sweep that
    reports every write whatever its route does."""
    src = _tree(tmp_path, ROUTE_WITH)
    assert findings(catalogue, _writes(src)[:1], src=src, explained={}) == []


def test_a_write_nothing_calls_is_found_and_an_excuse_nothing_reaches_is_stale(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    """A writing function with no caller is the placeholder waiting for its first caller, and an
    excuse no path reaches is an excuse for code that has gone. Delete this and both can sit in
    the tree reading as covered."""
    src = _tree(tmp_path, ROUTE_WITH)
    found = findings(
        catalogue, _writes(src)[1:], src=src, explained={"brain.gone:thing": "a reason"}
    )
    assert found == [
        "INSERT ops.setting via brain.fake_store:orphan: nothing calls it, so whoever does first "
        "will write the placeholder",
        "brain.gone:thing: excused in NOT_A_REQUEST_WITH_A_REACH and no write path reaches it any "
        "more",
    ]


def test_every_excuse_says_why_in_more_than_a_phrase() -> None:
    """Delete this and an excuse can be one word, which is a finding silenced rather than a path
    argued out of scope."""
    assert all(len(reason.split()) > 15 for reason in NOT_A_REQUEST_WITH_A_REACH.values())
