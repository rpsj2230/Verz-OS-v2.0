"""The install checks for the weekly rehearsal, each passing on PostgreSQL at head and failing with
the product broken.

The checks that read the install's own bucket are given a listing in place of the object store the
test process does not have, by replacing the one function that reads it. The checks that call the
product's own code are given nothing, and are broken by replacing the product's function they call.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M30.3.3, M30.3.4, M30.3.6, M30.3.7, M30.3.8, M30.3.9, M30.3.11
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_backup_drill"
ASKED = "a_rehearsal_is_asked_for_once_and_only_by_an_administrator"
THREE = "the_newest_rehearsal_asked_all_three_questions"
TIMED = "a_verified_rehearsal_states_its_measured_time"
LOUDEST = "a_rehearsal_that_did_not_verify_is_the_loudest_alert"
PLACED = "the_newest_copy_is_off_the_host_under_the_clients_key"
WRITTEN = ("ops.setting",)

#: Far outside any plausible wall clock for what the stand-in bucket holds.
YEAR = 2019


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (ASKED, ("M30.3.9",)),
        (THREE, ("M30.3.6", "M30.3.7")),
        (TIMED, ("M30.3.8",)),
        (LOUDEST, ("M30.3.11",)),
        (PLACED, ("M30.3.3", "M30.3.4")),
    ]
    assert checks_in(MODULE) == [ASKED, THREE, TIMED, LOUDEST, PLACED]


def manifest(*, off_host: bool | None, key: str | None) -> tuple[str, str]:
    document: dict[str, object] = {
        "backup_id": f"database-{YEAR}0101T020000Z",
        "coverage": "database",
        "method": "full",
        "destination": "s3://copies",
        "started_at": f"{YEAR}-01-01T02:00:00+00:00",
        "finished_at": f"{YEAR}-01-01T02:04:00+00:00",
        "recoverable_to": f"{YEAR}-01-01T02:04:00+00:00",
        "size_bytes": 4096,
    }
    if off_host is not None:
        document["off_host"] = off_host
    if key is not None:
        document["key_held_by"] = key
    return (f"database-{YEAR}0101T020000Z.manifest.json", json.dumps(document))


def record(*, canary: bool | None = True, skip: str | None = None) -> tuple[str, str]:
    checks = [
        {"check": "schema_complete", "passed": True, "detail": "every schema is present"},
        {"check": "smoke_query", "passed": True, "detail": "every count came back"},
    ]
    if canary is not None:
        checks.append(
            {
                "check": "permission_canary",
                "passed": canary,
                "detail": "a stranger was refused" if canary else "a stranger was shown a row",
            }
        )
    if skip is not None:
        checks = [one for one in checks if one["check"] != skip]
    document = {
        "backup_id": f"database-{YEAR}0101T020000Z",
        "started_at": f"{YEAR}-01-02T09:00:00+00:00",
        "finished_at": f"{YEAR}-01-02T09:30:00+00:00",
        "into_scratch": True,
        "checks": checks,
    }
    return (f"database-{YEAR}0101T020000Z-drill-1.drill.json", json.dumps(document))


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_backup_drill") as url:
        yield url


def run_module(
    url: str, *names: str, listing: tuple[tuple[str, str], ...] | None = None
) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops import acceptance_checks_backup_drill as module

    real = module._install_listing
    if listing is not None:

        async def held(_h: Any) -> tuple[tuple[str, str], ...]:
            return listing

        module._install_listing = held  # type: ignore[assignment]
    try:
        settings = settings_from({"BRAIN_DATABASE_URL": url})
        checks = [one for one in registered((MODULE,)) if not names or one.name in names]
        _, results = asyncio.run(
            acceptance_run.run_acceptance(
                normalise_database_url(url),
                settings=settings,
                commit="abc1234",
                checks=checks,
                force=True,
            )
        )
    finally:
        module._install_listing = real  # type: ignore[assignment]
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


GOOD = (manifest(off_host=True, key="client"), record())


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_that_has_done_it_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it**, with a bucket that holds a good copy and a rehearsal
    of it. Delete this and a check that can never pass on a real schema, or that leaves the switch
    on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_module(install, listing=GOOD)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert _counts(install) == before


@pytest.mark.needs_db
def test_the_checks_that_read_the_bucket_are_not_run_and_say_why_where_nothing_is_there(
    install: str,
) -> None:
    """Without a store, or with a bucket holding nothing yet. Delete this and an install that has
    done none of it reads as one that has, or as one that failed."""
    nothing = run_module(install, THREE, TIMED, PLACED, listing=())
    assert {name: outcome for name, (outcome, _) in nothing.items()} == dict.fromkeys(
        (THREE, TIMED, PLACED), NOT_RUN
    )
    assert "no rehearsal has been recorded" in nothing[THREE][1]
    assert "no rehearsal has verified" in nothing[TIMED][1]
    assert "no copy of the database" in nothing[PLACED][1]
    unconnected = run_module(install, THREE, TIMED, PLACED)
    assert {outcome for outcome, _ in unconnected.values()} == {NOT_RUN}
    assert all("object store" in why for _, why in unconnected.values())


def _failed(url: str, name: str, *, listing: tuple[tuple[str, str], ...] = GOOD) -> str:
    [(outcome, reason)] = run_module(url, name, listing=listing).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_record_that_skipped_a_question_fails_the_check_that_a_failed_copy_does_not(
    install: str,
) -> None:
    """The check judges the machinery. Delete this and a record with no canary closes the leaf, or
    a copy that failed its canary (a finding about the copy, not the rehearsal) fails it."""
    skipped = _failed(
        install, THREE, listing=(manifest(off_host=True, key="client"), record(canary=None))
    )
    assert "all three questions" in skipped
    failed_canary = run_module(
        install, THREE, listing=(manifest(off_host=True, key="client"), record(canary=False))
    )
    assert failed_canary[THREE] == (PASSED, "")


@pytest.mark.needs_db
def test_a_copy_kept_on_the_host_or_readable_by_anybody_fails_the_placement_check(
    install: str,
) -> None:
    """The two facts, separately. Delete this and a copy beside the original, or one in the clear,
    closes the off-host and encryption leaves."""
    on_host = _failed(install, PLACED, listing=(manifest(off_host=False, key="client"),))
    assert "machine it is a copy of" in on_host
    in_clear = _failed(install, PLACED, listing=(manifest(off_host=True, key="nobody"),))
    assert "anybody who reaches the bucket" in in_clear
    platform = _failed(install, PLACED, listing=(manifest(off_host=True, key="platform"),))
    assert platform == in_clear


@pytest.mark.needs_db
def test_a_copy_that_declares_nothing_is_not_run_rather_than_failed(install: str) -> None:
    """An old manifest. Delete this and an install whose backup predates the declaration is told
    its copies are on the host when nothing recorded where they are."""
    [(outcome, reason)] = run_module(
        install, PLACED, listing=(manifest(off_host=None, key=None),)
    ).values()
    assert outcome == NOT_RUN and "before copies declared" in reason


@pytest.mark.needs_db
def test_a_press_that_ignores_the_switch_fails_the_asking_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and the request is left on an install where
    nothing reads it, with the check green."""
    from brain import rehearsal_routes
    from brain.ops import acceptance_checks_backup_drill as module

    async def always(_session: Any, _feature: Any) -> bool:
        return True

    monkeypatch.setattr(rehearsal_routes, "is_on", always)
    assert _failed(install, ASKED) == module.THE_SWITCH_WAS_IGNORED


@pytest.mark.needs_db
def test_a_press_open_to_whoever_reads_the_screen_fails_the_asking_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority dropped, leaving the screen's read. Delete this and anybody who may see the
    backup page can load every record into a second place."""
    from brain import rehearsal_routes
    from brain.console.reads import permitted
    from brain.console.screens import screen
    from brain.ops import acceptance_checks_backup_drill as module

    monkeypatch.setattr(
        rehearsal_routes,
        "may_ask",
        lambda reach, now: permitted(screen("recovery").read, reach, now),
    )
    assert _failed(install, ASKED) == module.THE_PRESS_WAS_REFUSED_TO_NOBODY


@pytest.mark.needs_db
def test_a_second_press_that_asks_again_fails_the_asking_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The waiting request not noticed. Delete this and two presses queue two scratch databases."""
    from brain import rehearsal_routes
    from brain.ops import acceptance_checks_backup_drill as module

    monkeypatch.setattr(rehearsal_routes, "pending_in", lambda _listing: None)
    assert _failed(install, ASKED) == module.A_SECOND_PRESS_ASKED_AGAIN


@pytest.mark.needs_db
def test_an_alert_order_that_puts_a_late_copy_first_fails_the_loudest_alert_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sort reversed. Delete this and the alert an operator reads first is a late copy while
    every copy's readability is unknown."""
    from brain.ops import acceptance_checks_backup_drill as module
    from brain.ops import recovery

    real = recovery.alerts

    def quietest_first(**kwargs: Any) -> Any:
        return tuple(reversed(real(**kwargs)))

    monkeypatch.setattr(recovery, "alerts", quietest_first)
    assert _failed(install, LOUDEST) == module.A_FAILURE_WAS_NOT_THE_LOUDEST


def test_the_clock_the_stand_in_bucket_uses_is_in_the_past() -> None:
    """The fixtures are dated far outside the wall clock but not in its future: a copy that
    restores to a moment that has not happened is refused by `exposure_seconds`. Delete this and a
    change of constant puts the fixture ahead of the clock and every check reads it as a fault."""
    assert datetime(YEAR, 1, 1, tzinfo=UTC) < datetime.now(UTC) - timedelta(days=365)
