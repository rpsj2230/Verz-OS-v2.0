"""The widget's acceptance check: registered, passing as the worker runs it, and able to fail.

The check writes nothing, so it runs through the suite's own runner against PostgreSQL at head
only because that is how every check is run; what it exercises is the route and the widget's
store. Then the widget is broken where the check proves it, each the way it would break: the
allowlist check skipped, the rate guard not asked, and a session handed a reach. Each is a
failed check with its own sentence.

Task ids: M10.5.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_widget"
NAME = "a_widget_session_is_minted_for_a_listed_site_within_its_rate"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M10.5.5",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M10.5.5" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


def run_check(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes() -> None:
    """**The check as the worker runs it.** Delete this and a check that cannot pass on the
    deployed image reaches the owner's server first."""
    with at_head("brain_acceptance_widget") as url:
        assert run_check(url, tuple(mine().values())) == {NAME: (PASSED, "")}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("allowlist", "an unlisted site was not refused as not set up"),
        ("rate", "the mint past the minute's allowance was not told to wait"),
        ("reach", "a minted session was not held as one carrying no reach"),
    ],
)
def test_the_check_fails_where_the_widget_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: every origin read as listed, so a stranger's page
    opens sessions; the rate guard answered yes whatever the window holds, so one page opens a
    session per request; and a session built with something other than the empty reach. Delete
    this and the check is satisfied by a door that mints for anybody, as often as they like."""
    from brain.channels import widget
    from brain.ops.limits import MintDecision

    if broken == "allowlist":
        real_mint = widget.WidgetSessions.mint

        def anybody(self: widget.WidgetSessions, **kwargs: Any) -> Any:
            self.allowed = self.allowed | {widget.normalise_origin(kwargs["origin"])}
            return real_mint(self, **kwargs)

        monkeypatch.setattr(widget.WidgetSessions, "mint", anybody)
    elif broken == "rate":

        def always(**_: Any) -> MintDecision:
            return MintDecision(minted=True, retry_after_seconds=0.0, reason="")

        monkeypatch.setattr(widget, "mint_widget_session", always)
    else:
        real = widget.WidgetSession

        def reached(**kwargs: Any) -> Any:
            made = real(**kwargs)
            object.__setattr__(made, "reach", "anything")
            return made

        monkeypatch.setattr(widget, "WidgetSession", reached)
    with at_head("brain_acceptance_widget") as url:
        assert run_check(url, (mine()[NAME],)) == {NAME: (FAILED, reason)}
