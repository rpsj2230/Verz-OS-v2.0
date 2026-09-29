"""Every application process follows the saved settings, not only the one that saved them.

Found on the owner's install on 2026-09-29: the currency was changed to SGD on the Settings
screen and the spend report kept answering XXX, because four application processes serve the
console and only the one that took the save held the new value until a restart.
`brain.ops.install_settings.keep_holding` re-reads the table every minute in each of them.

Task ids: M27.12.7
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.install import hold_saved
from brain.ops.install_settings import HOLD_EVERY, keep_holding
from brain.report_routes import money_and_clock

APP = Path(__file__).resolve().parents[2] / "src" / "brain" / "app.py"


@pytest.fixture(autouse=True)
def held_as_before() -> Iterator[None]:
    """Every test starts with the currency unset and leaves whatever was held before it."""
    before = hold_saved({"INSTALL_CURRENCY": "XXX"})
    yield
    hold_saved(before)


async def no_wait(_seconds: float) -> None:
    return None


def test_a_currency_saved_elsewhere_reaches_this_process_within_one_round() -> None:
    """The spend report's currency follows a value another process saved.

    Delete this and a re-read that fetched the rows and held nothing would pass, leaving the
    report saying XXX beside a currency the Settings screen shows as SGD."""

    async def another_process_saved(_sessions: Any) -> Sequence[str]:
        hold_saved({"INSTALL_CURRENCY": "SGD"})
        return ("INSTALL_CURRENCY",)

    assert money_and_clock()[0] == "XXX"
    asyncio.run(keep_holding(None, sleep=no_wait, rounds=1, refresh=another_process_saved))  # type: ignore[arg-type]
    assert money_and_clock()[0] == "SGD"


def test_a_round_the_database_refuses_is_asked_again_next_time() -> None:
    """A table that did not answer once is not a reason to stop following it.

    Delete this and one refused read ends the loop, and the process is back to holding whatever
    it held at its start until it is restarted."""
    asked: list[int] = []

    async def refused_once(_sessions: Any) -> Sequence[str]:
        asked.append(1)
        if len(asked) == 1:
            msg = "the database did not answer"
            raise OSError(msg)
        hold_saved({"INSTALL_CURRENCY": "SGD"})
        return ("INSTALL_CURRENCY",)

    asyncio.run(keep_holding(None, sleep=no_wait, rounds=2, refresh=refused_once))  # type: ignore[arg-type]
    assert len(asked) == 2
    assert money_and_clock()[0] == "SGD"


def test_the_re_read_waits_a_minute_between_rounds() -> None:
    """Once a minute, the provider keys' own figure, and it waits before its first read because
    the lifespan has just loaded the table.

    Delete this and a loop with no wait, which reads the table as fast as the event loop turns,
    passes every test above."""
    waited: list[float] = []

    async def counted(seconds: float) -> None:
        waited.append(seconds)

    async def nothing(_sessions: Any) -> Sequence[str]:
        return ()

    asyncio.run(keep_holding(None, sleep=counted, rounds=2, refresh=nothing))  # type: ignore[arg-type]
    assert waited == [60.0, 60.0]
    assert HOLD_EVERY.total_seconds() == 60.0


def test_every_application_process_starts_the_re_read_in_its_lifespan() -> None:
    """The loop is started by the application, beside the provider keys' own.

    Delete this and `keep_holding` can be written, tested and never started, which is the
    install's state before the fix: every process but one holding the old currency."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    started = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_task"
        and node.args
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Name)
        and node.args[0].func.id == "keep_holding"
    ]
    assert len(started) == 1
