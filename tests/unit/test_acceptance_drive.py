"""Google Drive's acceptance check: registered, placed, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Drive folder
made up for the run is connected, listed into the index by the worker with a token its key file
bought, and asked about through the application's own passage reader, and every table the check
writes holds afterwards what it held before. Then it is run against the product broken where it
proves: a file's words never read live, a reader outside the folder's department told them, and the
lock on a file ignored. Each fails with its own sentence.

Task ids: M11.6.7, M11.9.15
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.core.scope import Scope
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_drive"
NAME = "a_drive_folder_s_words_are_read_live_and_kept_nowhere"
DEPTH_FIRST = "a_drive_tree_wider_than_a_pass_is_read_whole_depth_first"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_drive_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        NAME: ("M11.6.7",),
        DEPTH_FIRST: ("M11.9.15",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def test_the_drive_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them: a Drive folder
    connected, listed and its words read live, then a tree wider than a pass read whole over two,
    placed after the Google sources'. Held
    here, beside the module's other tests, so a package adding a check edits its own file and
    never a list every package appends to. Delete this and a check can drop out of the module with
    the page simply listing one fewer row."""
    from brain.ops import acceptance
    from brain.ops.acceptance_checks_drive import CHECK_ORDER
    from brain.ops.acceptance_checks_google import CHECK_ORDER as ANALYTICS

    assert checks_in(MODULE) == [NAME, DEPTH_FIRST]
    assert CHECK_ORDER > ANALYTICS
    modules = acceptance.check_modules()
    assert modules.index(MODULE) > modules.index("brain.ops.acceptance_checks_google")


@pytest.mark.needs_db
def test_on_a_real_database_a_folder_s_words_are_read_live_and_nothing_is_left_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Both pass, and the
    projection, the connections, the attempts and the ledger hold what they held before. Delete
    this and the path from a connected folder to a file's words on Ask can break with nothing on
    the owner's install saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_drive") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, ""), DEPTH_FIRST: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("live", "a file's words were not read for a reader granted them"),
        ("reach", "a file's words were told to a reader not granted them"),
        ("lock", "a file locked narrower than its folder was read"),
    ],
)
def test_the_drive_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: a passage reader that never reads a file's words, a reach
    that admits every reader to the folder's files, and the lock on a file ignored. Each fails the
    check with its own sentence. Delete this and the check can pass with the property gone."""
    import brain.ops.drive_passages as drive_passages
    from brain.core.entitlement import EntitlementSet

    if broken == "live":

        def never(self: Any, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
            del self, args, kwargs
            return ()

        monkeypatch.setattr(drive_passages.DrivePassages, "read", never)
    elif broken == "reach":
        original = EntitlementSet.scope_for

        def everywhere(self: EntitlementSet, capability: Any, now: Any = None) -> Scope | None:
            if capability == drive_passages.READ_FILE:
                return Scope(clauses=())
            return original(self, capability, now)

        monkeypatch.setattr(EntitlementSet, "scope_for", everywhere)
    else:
        monkeypatch.setattr(drive_passages, "withheld_from_a_read", lambda *args: None)
    with at_head(f"brain_acceptance_drive_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_depth_first_check_fails_where_the_walk_s_path_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second check broken where it proves: a walk whose path is read back as empty forgets
    the folders waiting on it, so the pass that carries on lists the chain's last folder and ends.
    The check fails with its own sentence. Delete this and the check can pass with a walk that
    reads only the first branch of every tree."""
    from brain.connectors import google_drive

    monkeypatch.setattr(google_drive, "walk_path", lambda asked: ())
    with at_head("brain_acceptance_drive_path") as url:
        outcome = run_checks(url, (mine()[DEPTH_FIRST],))
    assert outcome[DEPTH_FIRST] == (
        FAILED,
        "the next pass did not start where the first stopped and list the folders it left waiting",
    )


@pytest.mark.needs_db
def test_the_drive_check_steps_aside_where_the_install_has_drive_connected() -> None:
    """`A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`. Delete this and the check could move the
    owner's real connection aside, or fail on an install whose Drive is connected."""
    from brain.ops.acceptance_checks_drive import DRIVE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_drive_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('google_drive', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, DRIVE_IS_CONNECTED_HERE_ALREADY)
