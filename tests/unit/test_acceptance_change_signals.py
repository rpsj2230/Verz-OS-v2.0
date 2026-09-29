"""The change-signal acceptance checks: registered, passing on a real schema, and able to fail.

The pure half holds the four checks to the suite and to the leaves they prove, and the recorded
callers to the answers they give. The database half builds PostgreSQL to head and runs the four
checks as the worker would, with the sources' answers recorded in the check and no socket opened:
they pass, and every table they write to holds afterwards what it held before. Then each is run
against the product broken the one way its leaf is about, a read that always asks for everything,
a read that always starts at its first page, a page write that never counts a change, and a read
that never retires, and fails with its own sentence; and a source the install has connected is not
read by any of them.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1, M11.4.6, M11.4.8, M11.8.4, M11.8.11
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from brain.ops import acceptance_checks_change_signals as signals
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_connectors import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_change_signals"

#: Each check and the leaf it proves.
LEAVES = {
    "a_second_read_asks_only_for_what_changed_since_the_first": ("M11.4.6",),
    "a_read_cut_short_carries_on_where_it_stopped": ("M11.4.8",),
    "a_changed_read_moves_the_epoch_and_the_cached_answer_goes": ("M11.8.4",),
    "a_dropped_record_is_retired_withheld_and_returned_as_a_new_row": ("M11.8.11",),
}

#: Every table the checks write to, which must hold afterwards what it held before.
WRITTEN_BY_THE_CHECKS = (
    "proj.record",
    "proj.record_retired",
    "proj.source_epoch",
    "ops.connector_connection",
    "ops.connector_sync",
)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_THE_CHECKS
    }


# ------------------------------------------------------------------------ without a server
def test_the_change_signal_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names the one leaf it was scoped to, each a leaf of the work breakdown, in the
    order the page lists them. Delete this and a check can close a leaf it does not exercise, or
    name an id no task has."""
    assert [(name, one.leaves) for name, one in mine().items()] == list(LEAVES.items())
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_the_helpdesk_caller_answers_each_page_it_was_given_and_an_empty_page_past_them() -> None:
    """The recorded list answers the page a call names, in Freshdesk's bare array, with that page's
    headers, and an empty array past the last, which is how the helpdesk ends a list. Delete this
    and the caller could answer every page with the first, and the carried-on check would pass a
    read that started again."""
    caller = signals._Listing(
        {1: [signals._ticket(1)], 2: [signals._ticket(2)]}, headers={1: {"X-A": "1"}}
    )
    headers = cast(Any, {})
    one = caller.get(
        "https://h.invalid/api/v2/tickets?page=1", address="x", headers=headers, max_bytes=9
    )
    two = caller.get(
        "https://h.invalid/api/v2/tickets?page=2", address="x", headers=headers, max_bytes=9
    )
    past = caller.get(
        "https://h.invalid/api/v2/tickets?page=3", address="x", headers=headers, max_bytes=9
    )
    assert json.loads(one.body) == [signals._ticket(1)] and one.headers == {"X-A": "1"}
    assert json.loads(two.body) == [signals._ticket(2)] and two.headers == {}
    assert json.loads(past.body) == []
    assert [query["page"] for query in caller.queries()] == ["1", "2", "3"]


def test_the_ledger_caller_answers_invoices_and_no_contacts_and_nothing_else() -> None:
    """Xero's two lists in Xero's envelope and a 404 for anything else, never a socket. Delete this
    and a caller answering contacts with invoices would put invoices under the wrong entity with
    the retirement check green."""
    caller = signals._Ledger([signals._invoice("a")])
    headers = cast(Any, {})
    invoices = caller.get("https://x.invalid/Invoices", address="x", headers=headers, max_bytes=9)
    contacts = caller.get("https://x.invalid/Contacts", address="x", headers=headers, max_bytes=9)
    other = caller.get("https://x.invalid/Other", address="x", headers=headers, max_bytes=9)
    assert json.loads(invoices.body) == {"Invoices": [signals._invoice("a")]}
    assert json.loads(contacts.body) == {"Contacts": []}
    assert other.status == 404


# --------------------------------------------------------------------------- a real run
@pytest.mark.needs_db
def test_on_a_real_database_every_change_signal_check_passes_and_leaves_nothing_behind() -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and the projection, the epochs, the connections, the attempts and the ledger hold
    exactly what they held before. Delete this and a check that cannot pass on the real schema, or
    one that commits a retired row or an epoch to a client's install, reaches the owner's server
    first."""
    with at_head("brain_acceptance_change_signals") as url:
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


def reading_everything(original: Any) -> Any:
    """`next_read` as a release with no cursor would plan: carry on, or read everything."""
    from brain.ops.connector_sync import ReadPass

    def next_read(reading: Any, state: Any, *, now: Any) -> Any:
        planned = original(reading, state, now=now)
        return ReadPass(started_at=planned.started_at, walks=planned.walks)

    return next_read


def starting_again(original: Any) -> Any:
    """`page_to_ask` as a release that restarts every read at its first page."""
    import dataclasses

    def page_to_ask(reading: Any, read: Any, walk: Any) -> Any:
        return original(reading, read, dataclasses.replace(walk, cursor=""))

    return page_to_ask


async def retiring_nothing(*args: Any, **kwargs: Any) -> int:
    """`_retire` as the release before this one: a sync retires nothing."""
    del args, kwargs
    return 0


@pytest.mark.needs_db
def test_each_check_fails_with_its_own_sentence_when_its_leaf_is_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Each leaf broken the one way it breaks, and each check failing on it.** A read that asks
    for everything every time fails the cursor check; a read that starts again at its first page
    fails the carried-on check; a page write that never counts a change fails the epoch check; a
    read that retires nothing fails the retirement check. Each with the sentence its check wrote
    for that fault. Delete this and any one of the four can pass with the behaviour it names gone,
    which is a check that could never have failed."""
    import brain.ops.connector_sync as policy
    import brain.ops.connector_sync_run as sync_run

    checks = mine()
    breaks = {
        "a_second_read_asks_only_for_what_changed_since_the_first": (
            "next_read",
            reading_everything(policy.next_read),
            "the second read did not ask only for what changed since the first",
        ),
        "a_read_cut_short_carries_on_where_it_stopped": (
            "page_to_ask",
            starting_again(policy.page_to_ask),
            "the next read did not carry on from the page the last one stopped",
        ),
        "a_changed_read_moves_the_epoch_and_the_cached_answer_goes": (
            "changed",
            lambda held, kept: False,
            "a read that wrote new records left its source's epoch where it was",
        ),
        "a_dropped_record_is_retired_withheld_and_returned_as_a_new_row": (
            "_retire",
            retiring_nothing,
            "a record a read of everything no longer returned was not retired",
        ),
    }
    with at_head("brain_acceptance_change_signals_broken") as url:
        before = written(url)
        outcomes: dict[str, tuple[str, str]] = {}
        for name, (attribute, broken, _) in breaks.items():
            with monkeypatch.context() as patched:
                patched.setattr(sync_run, attribute, broken)
                outcomes.update(run_checks(url, (checks[name],)))
        after = written(url)

    assert outcomes == {name: (FAILED, said) for name, (_, _, said) in breaks.items()}
    assert after == before


def never_reviving(record: Any, fields: Any) -> Any:
    """`record_upsert` as the release before this one wrote it: a retired row is never written."""
    from sqlalchemy import and_
    from sqlalchemy.dialects.postgresql import insert

    from brain.tables.projection import ProjectedRecordRow

    statement = insert(ProjectedRecordRow).values(
        source=record.source,
        entity=record.entity,
        source_id=record.source_id,
        fields=dict(fields),
        last_seen_at=record.last_seen_at,
    )
    table = ProjectedRecordRow.__table__
    return statement.on_conflict_do_update(
        index_elements=[table.c.source, table.c.entity, table.c.source_id],
        set_={"fields": statement.excluded.fields, "last_seen_at": statement.excluded.last_seen_at},
        where=and_(
            table.c.deleted_at.is_(None),
            table.c.last_seen_at <= statement.excluded.last_seen_at,
        ),
    )


@pytest.mark.needs_db
def test_the_retirement_check_fails_where_a_returned_record_is_not_served_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retirement check's second half, broken the way the release before this one behaves: an
    upsert that never writes over a retired row. The check fails with the sentence it wrote for a
    returned record not served. Delete this and the check can pass with a returned record hidden for
    good, which is the half of M11.8.11 that retiring alone does not prove."""
    import brain.ops.connector_sync_run as sync_run

    name = "a_dropped_record_is_retired_withheld_and_returned_as_a_new_row"
    monkeypatch.setattr(sync_run, "record_upsert", never_reviving)
    with at_head("brain_acceptance_change_signals_returned") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[name],))
        after = written(url)
    assert outcome[name] == (FAILED, "a record the source returned again was not served again")
    assert after == before


@pytest.mark.needs_db
def test_a_source_the_install_has_connected_is_read_by_no_check() -> None:
    """`A_CONNECTED_SOURCE_IS_NOT_READ_BY_A_CHECK`: with the helpdesk and the ledger connected on
    the install, every check says it was not run, in its own words, and writes nothing. Delete
    this and a check can connect a source a second time, or hold the epoch row of a source the
    worker is reading for the length of the check."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_change_signals_connected") as url:
        for name in (signals.HELPDESK, signals.LEDGER):
            sql(
                url,
                "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
                " VALUES (%s, '{}'::jsonb, %s, 'u_admin')",
                name,
                "0" * 64,
            )
        before = written(url)
        outcomes = run_checks(url, tuple(mine().values()))
        after = written(url)

    assert outcomes == dict.fromkeys(LEAVES, (NOT_RUN, signals.SOURCE_CONNECTED_ALREADY))
    assert after == before
