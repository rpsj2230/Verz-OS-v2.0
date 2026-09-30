"""The connector acceptance checks: registered, passing on a real schema, and able to fail.

The pure half holds the checks to the suite and runs the manifest review check, which needs no
database, against the install's own validator and against four validators broken one way each: a
cap that admits thirteen, a denylist that forgets its spellings, a change signal that is always
present, and a kept-row rule that finds nothing. Each broken validator is a failed check with its
own sentence, which is the check shown able to fail.

The database half builds PostgreSQL to head and runs the three checks as the worker would, with
the source's answers recorded in the check and no socket opened: they pass, and every table they
write to holds afterwards what it held before. Then the sync check is run against a worker that
copies a recorded answer into a settings row, which is a copy by a route that is not a projected
field, and fails on the canary; and the pin check against a plan that ignores the digest, which
fails, and against an install with the source connected, which is not run.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1, M11.1.6
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from brain.ops import acceptance_checks_connectors as connectors
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_connectors"

#: Each check and the leaves it proves, as the coordinator scoped them.
LEAVES = {
    "manifest_review_refuses_a_projection_that_is_more_than_a_pointer": (
        "M11.4.2",
        "M11.4.3",
        "M11.4.4",
        "M11.8.1",
        "M11.4.7",
    ),
    "a_sync_keeps_its_minimal_index_and_the_canary_reaches_no_table": (
        "M11.4.1",
        "M11.4.5",
        "M11.8.2",
    ),
    "a_changed_declaration_makes_the_next_sync_refuse": ("M11.1.7",),
    "a_source_is_connected_switched_off_and_upgraded_from_the_console": ("M11.1.6",),
}

#: Every table the connector checks write to, which must hold afterwards what it held before.
WRITTEN_BY_CONNECTOR_CHECKS = (
    "proj.record",
    "ops.connector_connection",
    "ops.connector_sync",
    "ops.setting",
)

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def review() -> Check:
    return mine()["manifest_review_refuses_a_projection_that_is_more_than_a_pointer"]


def without_a_database() -> Harness:
    # The review check reads nothing: it is handed a harness with no connection on purpose.
    return Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]


def reviewed() -> tuple[str, str]:
    """The review check's outcome and reason, as the run records them."""
    from brain.ops.acceptance import reason_for

    try:
        asyncio.run(review().run(without_a_database()))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


# ------------------------------------------------------------------------ without a server
def test_the_connector_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names the leaves it was scoped to, and each is a leaf of the work breakdown.
    Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_the_manifest_review_check_passes_against_the_install_s_own_validator() -> None:
    """The positive run: twelve pointers accepted, every refusal seen. Delete this and the check
    can refuse its own accepted case, which reads on the page as review being broken."""
    assert reviewed() == (PASSED, "")


def test_the_review_check_fails_when_the_cap_admits_a_thirteenth_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.4.2 broken at the validator the check asks. Delete this and a check that could pass
    with the cap gone is the only thing standing between a mirror and the install."""
    import brain.connectors.manifest as manifest

    monkeypatch.setattr(manifest, "MAX_PROJECTED_FIELDS", 13)
    assert reviewed() == (FAILED, "manifest review accepted a thirteenth projected field")


def test_the_review_check_fails_when_the_denylist_forgets_a_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.4.4 broken: the denylist keeps its names and loses its shapes, so `contact_email` gets
    through. Delete this and a denylist matching only exact names passes the check."""
    import brain.core.projection as projection

    monkeypatch.setattr(projection, "NEVER_PROJECT_PATTERNS", ())
    assert reviewed() == (FAILED, "manifest review accepted a projected personal field")


def test_the_review_check_fails_when_a_source_with_no_signal_may_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.4.7 broken: every signal counts as one. Delete this and the clause that stops the
    projection becoming a mirror can go with the check still green."""
    from brain.connectors.manifest import ChangeSignal

    monkeypatch.setattr(ChangeSignal, "is_a_signal", property(lambda self: True))
    assert reviewed() == (
        FAILED,
        "a source with no change signal was allowed to project a field",
    )


def test_the_review_check_fails_when_a_kept_row_is_not_held_to_its_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.8.1's kept-row half broken: the rule finds nothing. Delete this and an undeclared
    field or a label that is a body can be kept with the check green."""
    import brain.connectors.minimal_index as minimal_index

    monkeypatch.setattr(minimal_index, "minimal_index_findings", lambda manifest, rows: ())
    assert reviewed() == (
        FAILED,
        "a kept row holding a field that is not a declared pointer was accepted",
    )


def test_the_stand_in_address_is_one_the_address_rule_admits_and_nothing_serves() -> None:
    """The resolver's answer has to pass the product's own address rule, or the sync check fails
    for a reason that is not the product's. Delete this and a reserved or private address can be
    written here, and the check fails on every install before it reads a page."""
    from brain.tools.fetch import _is_reachable_only_from_inside

    assert not _is_reachable_only_from_inside(connectors.STAND_IN_ADDRESS)
    assert connectors._Resolver().resolve("any.example.invalid") == [connectors.STAND_IN_ADDRESS]


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def connector_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_CONNECTOR_CHECKS
    }


@pytest.mark.needs_db
def test_on_a_real_database_every_connector_check_passes_and_leaves_nothing_behind() -> None:
    """**The three checks as the worker runs them, against PostgreSQL at head.** Each passes with
    no reason, and the projection, the connections, the attempts, the settings and the ledger hold
    exactly what they held before. Delete this and a check that cannot pass on the real schema,
    or one that commits a projected row or a connection to a client's install, reaches the
    owner's server first."""
    with at_head("brain_acceptance_connectors") as url:
        before = (counts(url), connector_counts(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), connector_counts(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


def leaking(original: Any) -> Any:
    """`attempt`, and then a copy of the first recorded answer written to a settings row.

    The copy goes by a route that is not a projected field, which is the route the canary exists
    to find. Written as the login, inside the check's transaction, so it is rolled back with it.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async def attempt(*args: Any, **kwargs: Any) -> Any:
        done = await original(*args, **kwargs)
        body = kwargs["caller"].invoices.decode("utf-8")
        bound = kwargs["sessions"].kw["bind"]
        async with AsyncSession(bind=bound, join_transaction_mode="create_savepoint") as session:
            await session.execute(text("RESET ROLE"))
            await session.execute(
                text(
                    "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
                    " VALUES ('acceptance.leak', 'string', to_jsonb(CAST(:body AS text)),"
                    " 'a copy', 'u_admin')"
                ).bindparams(body=body)
            )
            await session.commit()
        return done

    return attempt


def ignoring_the_pin(original: Any) -> Any:
    """`plan_for`, asked as though the stored digest were always this release's."""
    import dataclasses

    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for

    def plan_for(connection: Any, **kwargs: Any) -> Any:
        today = manifest_digest(manifest_for(connection.connector, connection.settings))
        return original(dataclasses.replace(connection, digest=today), **kwargs)

    return plan_for


@pytest.mark.needs_db
def test_the_sync_check_fails_when_a_recorded_answer_is_copied_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.8.2 broken the way it breaks in practice: every kept row is right and a copy of the
    answer lands in another table. The audit finds the canary and the check fails. Delete this and
    the canary search can be pointed at nothing, or at proj.record alone, with the check green."""
    import brain.ops.connector_sync_run as sync_run

    [sync] = [one for one in mine().values() if one.name.startswith("a_sync_keeps")]
    monkeypatch.setattr(sync_run, "attempt", leaking(sync_run.attempt))
    with at_head("brain_acceptance_connectors_leak") as url:
        before = connector_counts(url)
        outcome = run_checks(url, (sync,))
        after = connector_counts(url)

    assert outcome[sync.name] == (
        FAILED,
        "the canary planted in a recorded answer was found in a table",
    )
    assert after == before


@pytest.mark.needs_db
def test_the_pin_check_fails_when_the_plan_ignores_the_digest_and_waits_on_a_connected_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M11.1.7 broken: a plan that reads under any declaration fails the check. And a source the
    install has connected is not connected again: the check is not run, with its own sentence.
    Delete this and the pin can be removed from the plan with the check green, or the check can
    move the owner's live connection aside."""
    import brain.ops.connector_sync as sync
    from tests.fixtures.scratch_postgres import sql

    [pin] = [one for one in mine().values() if one.name.endswith("next_sync_refuse")]
    with at_head("brain_acceptance_connectors_pin") as url:
        with monkeypatch.context() as patched:
            patched.setattr(sync, "plan_for", ignoring_the_pin(sync.plan_for))
            ignored = run_checks(url, (pin,))
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        connected = run_checks(url, (pin,))

    assert ignored[pin.name] == (FAILED, "a sync was planned under a declaration nobody agreed to")
    assert connected[pin.name] == (NOT_RUN, connectors.SOURCE_ALREADY_CONNECTED)


def test_the_sync_check_reads_only_through_the_recorded_caller() -> None:
    """`A_RECORDED_ANSWER_IS_NEVER_A_CALL`: the caller answers the two endpoints it was written for
    and a 404 for anything else, and never opens a socket. Delete this and a caller that fell
    through to a real transport could be substituted with every other test green."""
    caller = connectors._Recorded(invoices=b'{"Invoices": []}', contacts=b'{"Contacts": []}')
    headers = cast(Any, {})
    one = caller.get("https://source.invalid/Invoices", address="x", headers=headers, max_bytes=9)
    two = caller.get("https://source.invalid/Contacts", address="x", headers=headers, max_bytes=9)
    other = caller.get("https://source.invalid/Other", address="x", headers=headers, max_bytes=9)
    assert (one.status, one.body) == (200, b'{"Invoices": []}')
    assert (two.status, two.body) == (200, b'{"Contacts": []}')
    assert other.status == 404
    assert len(caller.asked) == 3


def lifecycle() -> Check:
    return mine()["a_source_is_connected_switched_off_and_upgraded_from_the_console"]


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("off", "a source switched off from the console was still read"),
        ("pin", "a source pinned to an older declaration was read before upgrade"),
        ("ledger", "a step in the source's life is missing from the audit ledger"),
    ],
)
def test_the_lifecycle_check_fails_when_a_step_does_not_take(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """M11.1.6 broken three ways, each the way it would break in practice: a switch-off that
    writes nothing, a plan that reads under any declaration, and a reconnection that bypasses the
    audited row. Each fails the check with its own sentence. Delete this and the check can pass
    with a source that cannot be switched off, or an upgrade nobody can find in the ledger."""
    import brain.ops.connector_store as store
    import brain.ops.connector_sync as sync

    if broken == "off":

        async def nothing(self: Any, connector: str, **kwargs: Any) -> Any:
            del self, connector, kwargs
            return LONG_AGO

        monkeypatch.setattr(store.StoredConnections, "disconnect", nothing)
    elif broken == "pin":
        monkeypatch.setattr(sync, "plan_for", ignoring_the_pin(sync.plan_for))
    else:
        from sqlalchemy import text

        original = store.StoredConnections.reconnect

        async def unaudited(self: Any, **kwargs: Any) -> Any:
            async with self._sessions() as session, session.begin():
                await session.execute(text("RESET ROLE"))
                await session.execute(
                    text("ALTER TABLE ops.connector_connection DISABLE TRIGGER USER")
                )
            try:
                return await original(self, **kwargs)
            finally:
                async with self._sessions() as session, session.begin():
                    await session.execute(text("RESET ROLE"))
                    await session.execute(
                        text("ALTER TABLE ops.connector_connection ENABLE TRIGGER USER")
                    )

        monkeypatch.setattr(store.StoredConnections, "reconnect", unaudited)
    with at_head(f"brain_acceptance_connectors_life_{broken}") as url:
        before = connector_counts(url)
        outcome = run_checks(url, (lifecycle(),))
        after = connector_counts(url)
    assert outcome[lifecycle().name] == (FAILED, reason)
    assert after == before


def test_the_connectors_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_connectors") == [
        "manifest_review_refuses_a_projection_that_is_more_than_a_pointer",
        "a_sync_keeps_its_minimal_index_and_the_canary_reaches_no_table",
        "a_changed_declaration_makes_the_next_sync_refuse",
        "a_source_is_connected_switched_off_and_upgraded_from_the_console",
    ]
