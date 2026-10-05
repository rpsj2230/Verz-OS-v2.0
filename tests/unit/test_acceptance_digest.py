"""The evening digest's acceptance check: registered, passing as the worker runs it, and able to
fail.

The check writes the digest's record inside its transaction, so the database half runs it against
PostgreSQL at head and asserts the settings table is as it was afterwards. Then the digest is
broken where the check proves it, the way it would break: the day's key made per run, so a second
run sends again; an unset destination read as a destination; and a switched-off channel sent to.
Each is a failed check with its own sentence.

Task ids: M38.3.3.1, M38.3.3.2, M38.3.3.3, M38.3.3.4
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
from tests.unit.test_acceptance import INSTALL, at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_digest"
NAME = "the_evening_digest_is_sent_once_a_day_to_the_chosen_conversation"
LEAVES = ("M38.3.3.1", "M38.3.3.2", "M38.3.3.3", "M38.3.3.4")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: LEAVES}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert set(LEAVES) <= {one for module in wbs["modules"] for one in module["leaf_ids"]}


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
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    settings table holds what it held before. Delete this and a check that cannot pass on the real
    schema, or one that leaves a digest record on a client's install, reaches the owner first."""
    with at_head("brain_acceptance_digest") as url:
        before = counts(url)
        outcomes = run_check(url, tuple(mine().values()))
        after = counts(url)

    assert outcomes == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("key", "the chosen conversation was not sent exactly one digest today"),
        ("unset", "a digest nobody pointed anywhere was sent"),
        ("off", "a switched-off channel was sent a digest or not said to be stopped"),
    ],
)
def test_the_check_fails_where_the_digest_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: the day's intent made unique per run, so a
    restarted worker posts twice; an unset destination read as the last one chosen; and the
    switch on a channel's record ignored. Delete this and the check is satisfied by a digest
    that posts wherever and whenever."""
    import uuid

    from brain.ops import digest_delivery, digest_run
    from brain.ops.digest_destination import Destination

    if broken == "key":
        real = digest_delivery.digest_operation

        def every_time(digest: Any, **kwargs: Any) -> Any:
            import dataclasses

            once = real(digest, **kwargs)
            return dataclasses.replace(once, key=uuid.uuid4().hex + uuid.uuid4().hex)

        monkeypatch.setattr(digest_delivery, "digest_operation", every_time)
    elif broken == "unset":

        def anywhere(saved: str) -> Destination | None:
            from brain.gate.context import Channel

            return Destination(Channel.LARK, "somewhere")

        monkeypatch.setattr(digest_run, "destination_of", anywhere)
    else:
        monkeypatch.setattr(digest_run, "connected_problem", lambda *_, **__: "")
    with at_head("brain_acceptance_digest") as url:
        assert run_check(url, (mine()[NAME],)) == {NAME: (FAILED, reason)}
