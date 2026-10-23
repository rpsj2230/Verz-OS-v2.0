"""The install checks for retention, the dry run and a person's own export, each passing on
PostgreSQL at head and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes (or says it did not run, for the one that reads a report only the worker writes) and leaves
nothing. Then each is shown failing: a policy that lost a class or shortened the ledger, a report
that left a store out, a release that records nothing, and an export handed over unrecorded.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M25.1.1, M25.1.2, M25.1.5, M25.2.3, M25.3.1, M25.4.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_data_governance import (
    CHECK_ORDER,
    NO_REPORT_YET,
    THE_SWEEP_CANNOT_COUNT_HERE,
    THE_SWEEP_IS_RELEASED_HERE,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_data_governance"
POLICY = "retention_is_declared_per_class_and_a_backup_states_its_limit"
REPORT = "the_retention_report_reaches_every_store_and_says_why_it_did_not"
DRY_RUN = "a_dry_run_removes_nothing_until_a_person_releases_the_sweep"
EXPORT = "a_person_exports_their_own_conversation_and_it_is_recorded"


def test_the_module_names_each_leaf_in_one_check() -> None:
    """Four checks, each closing its own leaves. Delete this and a leaf can move to a check that
    never looked at it, with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (POLICY, ("M25.1.1", "M25.1.2", "M25.2.3")),
        (REPORT, ("M25.1.5",)),
        (DRY_RUN, ("M25.4.1",)),
        (EXPORT, ("M25.3.1",)),
    ]
    assert checks_in(MODULE) == [POLICY, REPORT, DRY_RUN, EXPORT]


def test_the_module_stands_inside_its_assigned_range_and_its_sentences_fit_a_result() -> None:
    """The order is the builder's assigned range, and a reason is stored whole. Delete this and
    two packages can place themselves on one number, or a reason is cut short on the Install
    page."""
    assert 2100 <= CHECK_ORDER <= 2199
    for sentence in (NO_REPORT_YET, THE_SWEEP_IS_RELEASED_HERE, THE_SWEEP_CANNOT_COUNT_HERE):
        assert len(sentence) <= REASON_CHARS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_data_governance") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

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
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Three pass, the report check says in words that the
    worker has not written one yet (a fresh database has none), and nothing a check wrote is
    left. Delete this and a check that can never pass on a real schema, or one that leaves a
    release or an export behind, reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes[POLICY] == (PASSED, "")
    assert outcomes[DRY_RUN] == (PASSED, ""), outcomes[DRY_RUN]
    assert outcomes[EXPORT] == (PASSED, ""), outcomes[EXPORT]
    assert outcomes[REPORT][0] == NOT_RUN
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_report_check_reads_the_report_the_worker_wrote(install: str) -> None:
    """A report in the table is shown, every store named. Delete this and the one check that reads
    the worker's report is only ever shown the empty case, so a report that left a store out
    would pass it."""
    from brain.ops.retention import enforcement_report
    from brain.ops.retention_store import report_document
    from tests.fixtures.scratch_postgres import sql

    made = enforcement_report(now=_now(), census=())
    document = report_document(made)
    # What a real sweep adds: a store it cannot count says why.
    for line in document["stores"]:
        line["unreached_because"] = "it is not a table in the database"

    _put_report(install, document["stores"])
    try:
        assert run_module(install, REPORT)[REPORT] == (PASSED, "")
        sql(install, "DELETE FROM ops.retention_report")
        _put_report(install, document["stores"][:-1])
        assert "say why" in _failed(install, REPORT)
    finally:
        sql(install, "DELETE FROM ops.retention_report")


def _put_report(url: str, stores: list[Any]) -> None:
    """A report row as the worker writes one, with these store lines."""
    from psycopg.types.json import Jsonb

    from tests.fixtures.scratch_postgres import sql

    sql(
        url,
        "INSERT INTO ops.retention_report (at, report_only, complete, stores, holds, findings) "
        "VALUES (now(), true, false, %s, '[]'::jsonb, '[]'::jsonb)",
        Jsonb(stores),
    )


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


@pytest.mark.needs_db
def test_a_policy_that_lost_a_class_or_shortened_the_ledger_fails_the_policy_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen listing a policy without one class, then with the ledger cut to a year. Delete
    this and M25.1.1 and M25.1.2 close on a screen that forgot a class or kept the ledger short."""
    from dataclasses import replace

    from brain import erasure_routes
    from brain.ops.retention import HORIZONS, DataClass

    with monkeypatch.context() as patched:
        patched.setattr(erasure_routes, "HORIZONS", HORIZONS[:-1])
        assert "every class" in _failed(install, POLICY)
    cut = tuple(
        replace(one, days=365) if one.data_class is DataClass.METADATA_LEDGER else one
        for one in HORIZONS
    )
    monkeypatch.setattr(erasure_routes, "HORIZONS", cut)
    assert "ledger" in _failed(install, POLICY)


@pytest.mark.needs_db
def test_a_release_that_records_nothing_fails_the_dry_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The release route returning without writing the release. Delete this and M25.4.1 closes on
    a button that releases nothing."""
    import uuid

    from brain import retention_routes

    async def nothing(*args: Any, **kwargs: Any) -> uuid.UUID:
        return uuid.uuid4()

    monkeypatch.setattr(retention_routes, "release_sweep", nothing)
    assert "still not released" in _failed(install, DRY_RUN)


@pytest.mark.needs_db
def test_an_export_handed_over_unrecorded_fails_the_export_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export route recording nothing before it hands the document over. Delete this and
    M25.3.1 closes on an export with no record of it."""
    from brain import thread_routes
    from brain.ops.data_export_store import StoredExports

    async def nothing(self: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(StoredExports, "record_report", nothing)
    assert thread_routes is not None
    assert "no record" in _failed(install, EXPORT)


def test_the_report_only_run_counts_as_the_owner_on_a_read_only_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The connection the dry run opens, seen without a database.** An install that names the
    application's login in `BRAIN_DATABASE_URL` keeps the owner's in `BRAIN_MIGRATION_DATABASE_URL`,
    and the sweep must be handed the owner's, read-only, or the check says it cannot count. Delete
    this and the check goes back to the application's login, which an install with a narrow
    `brain_app` cannot count with, so M25.4.1 is never shown there."""
    from types import SimpleNamespace

    import psycopg

    from brain.ops import acceptance_checks_data_governance as module

    opened: list[Any] = []

    class Connection:
        read_only = False

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def connect(conninfo: str, **kwargs: Any) -> Connection:
        one = Connection()
        opened.append((conninfo, one))
        return one

    seen: list[bool] = []

    def executor(conn: Connection, *, holds: Any) -> str:
        seen.append(conn.read_only)
        return "executor"

    def sweep(given: Any, *, now: Any, report_only: bool) -> tuple[Any, bool]:
        return given, report_only

    monkeypatch.setattr(psycopg, "connect", connect)
    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": "postgresql://brain_app:x@db.invalid:5432/brain",
            "BRAIN_MIGRATION_DATABASE_URL": "postgresql://brain_owner:x@db.invalid:5432/brain",
        }
    )
    got = asyncio.run(
        module._dry_run(cast(Any, SimpleNamespace(settings=settings)), executor, sweep)
    )
    assert got == ("executor", True)
    [(conninfo, _)] = opened
    assert "brain_owner" in conninfo and "brain_app" not in conninfo
    assert seen == [True]


def _dry_run_with(url: str, env: dict[str, str]) -> tuple[str, str]:
    """The dry-run check alone, on the install `url` names, with the process's settings `env`."""
    from brain.db import normalise_database_url

    settings = settings_from(env)
    checks = [one for one in registered((MODULE,)) if one.name == DRY_RUN]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    [only] = results
    return only.outcome, only.reason


@pytest.mark.needs_db
def test_on_an_install_naming_the_application_login_the_dry_run_counts_as_the_owner(
    install: str,
) -> None:
    """**The install the check could never be shown on.** The process names a login that holds the
    application's role in `BRAIN_DATABASE_URL` and the owner's in `BRAIN_MIGRATION_DATABASE_URL`.
    Counted as the application the sweep is refused a table (measured: permission denied for
    `obs.trace_step`) and the check is not run; counted as the owner, as the worker counts, it
    passes. Delete this and a change back to the application's login passes every test here, where
    the database is a superuser, and M25.4.1 is never shown on a real install."""
    import os
    from urllib.parse import urlsplit, urlunsplit

    from tests.fixtures.scratch_postgres import sql

    role = f"acceptance_app_{os.getpid()}"
    sql(install, f"CREATE ROLE {role} LOGIN IN ROLE brain_app")
    try:
        parts = urlsplit(install)
        app = urlunsplit(parts._replace(netloc=f"{role}@{parts.hostname}:{parts.port}"))
        counted = _dry_run_with(
            install, {"BRAIN_DATABASE_URL": app, "BRAIN_MIGRATION_DATABASE_URL": install}
        )
        refused = _dry_run_with(install, {"BRAIN_DATABASE_URL": app})
    finally:
        sql(install, f"DROP ROLE {role}")
    assert counted == (PASSED, "")
    assert refused == (NOT_RUN, THE_SWEEP_CANNOT_COUNT_HERE)
