"""The deployment history: what the deploy writes, what the Version screen reads, and where it is
kept apart from the permission ledger.

The pure half runs everywhere. The database half builds `0091` on a scratch server and runs the
store's own statements as the login and the route's read as `brain_app`; it skips without
`DATABASE_URL`, and CI always sets it.

Task ids: M38.1.3.5
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.db import normalise_database_url
from brain.install_routes import (
    NOTHING_HERE_READS_THE_DEPLOYMENT_HISTORY,
    DeploymentHistoryView,
    history_view,
    read_history,
)
from brain.ops.application_privileges import reachable
from brain.ops.deployment_history import (
    NOTHING_RECORDED_YET,
    THE_HISTORY_DOES_NOT_HOLD,
    THE_HISTORY_HOLDS,
    history_from,
)
from brain.ops.deployment_store import main, parse, record, row_of
from brain.ops.deployments import Deployment, DeploymentChain, DeploymentRecordError
from tests.fixtures.scratch_postgres import drop, fresh, migrate, run

REPO = Path(__file__).resolve().parents[2]

#: Far from any wall clock, because nothing here is about the present.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def a_deploy(minutes: int, outcome: str = "deployed", image: str = "sha256:new") -> Deployment:
    return Deployment(
        at=LONG_AGO + timedelta(minutes=minutes),
        outcome=outcome,
        commit=f"c{minutes:06d}",
        image=image,
        previous="sha256:old",
        task_ids=("M38.1.3.5", "M1.1.1"),
    )


def a_line(one: Deployment) -> str:
    return json.dumps(
        {
            "at": one.at.isoformat(),
            "outcome": one.outcome,
            "commit": one.commit,
            "image": one.image,
            "previous": one.previous,
            "task_ids": ",".join(one.task_ids),
        }
    )


@dataclass(frozen=True)
class Stored:
    """A row as the table returns it, built from a chain link through the store's own mapping."""

    seq: int
    at: datetime
    outcome: str
    commit: str
    image: str
    previous: str
    task_ids: list[str]
    prev_hash: str
    entry_hash: str
    fingerprint: str = ""


def stored(*deploys: Deployment) -> list[Stored]:
    chain = DeploymentChain()
    return [Stored(**row_of(chain.append(one))) for one in deploys]


# ---------------------------------------------------------------------------- the read, pure
def test_the_screen_lists_the_newest_deploys_first_and_says_the_chain_holds() -> None:
    """Delete this and the list can come out oldest first, which buries the deploy somebody opened
    the screen to find under every deploy before it."""
    rows = stored(*(a_deploy(minute) for minute in range(5)))

    history = history_from(rows, shown=3)

    assert [link.deployment.commit for link in history.shown] == ["c000004", "c000003", "c000002"]
    assert history.broken == ()
    assert history.says == THE_HISTORY_HOLDS


def test_an_edited_row_outside_the_rows_shown_is_still_reported() -> None:
    """The chain is verified over every stored row, not over the ones on the screen: an edit to
    the oldest deploy is reported while only the newest two are drawn.

    Delete this and verification can be narrowed to the rows shown, which passes every history
    whose older half was changed to hide a bad release."""
    rows = stored(*(a_deploy(minute) for minute in range(5)))
    rows[0] = replace(rows[0], outcome="rolled_back")

    history = history_from(rows, shown=2)

    assert [link.seq for link in history.shown] == [4, 3]
    assert 0 in history.broken
    assert history.says == THE_HISTORY_DOES_NOT_HOLD


def test_no_deploy_recorded_yet_is_said_in_words_and_not_as_an_empty_list() -> None:
    """Delete this and a new install shows a heading over nothing, which reads as a screen that did
    not load."""
    assert history_from([]).says == NOTHING_RECORDED_YET


def test_a_process_with_no_database_answers_why_and_never_an_empty_history() -> None:
    """Delete this and the route can answer `deploys: []` on a process that never looked, which
    reads as nothing ever having been deployed."""
    import asyncio

    answer = asyncio.run(read_history(None))

    assert answer.deploys is None
    assert answer.unread == NOTHING_HERE_READS_THE_DEPLOYMENT_HISTORY
    with pytest.raises(ValueError, match="nothing saying why"):
        DeploymentHistoryView()
    with pytest.raises(ValueError, match="cannot both be set"):
        DeploymentHistoryView(deploys=[], unread="x")


def test_the_view_carries_the_sha_the_time_the_task_ids_and_the_outcome_of_each_deploy() -> None:
    """Delete this and a field the owner reads the history for can be dropped from the response
    with the screen still rendering."""
    view = history_view(history_from(stored(a_deploy(1, "held_back"))))

    assert view.deploys is not None
    [one] = view.deploys
    assert (one.commit, one.outcome, one.task_ids) == (
        "c000001",
        "held_back",
        ["M1.1.1", "M38.1.3.5"],
    )
    assert one.at == (LONG_AGO + timedelta(minutes=1)).isoformat()
    assert view.holds is True


# ---------------------------------------------------------------------------- the write, pure
def test_a_malformed_line_refuses_the_whole_run_and_records_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete this and a partial line can be skipped, leaving the stored history shorter than the
    file it is derived from with nothing saying so."""
    lines = [a_line(a_deploy(1)), '{"at": "2019-03-04T09:02:00+00:00", "outc']

    with pytest.raises(DeploymentRecordError):
        parse(lines)
    assert main([], lines) == 1
    assert "Nothing was recorded" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (
            {
                "BRAIN_DATABASE_URL": "postgresql://brain_app:x@db/brain",
                "BRAIN_MIGRATION_DATABASE_URL": "postgresql://owner:y@db/brain",
            },
            "postgresql+psycopg://owner:y@db/brain",
        ),
        (
            {"DATABASE_URL": "postgresql://owner:y@db/brain"},
            "postgresql+psycopg://owner:y@db/brain",
        ),
    ],
)
def test_the_store_writes_as_the_owner_and_not_as_the_application_login(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str], expected: str
) -> None:
    """The store runs inside the app container, whose database login is `brain_app` once an
    install narrows it, and `brain_app` may only read `ops.deployment_record`. Found on an
    install, where every deploy's history write was refused with "permission denied".

    Delete this and the store can go back to `database_url`, and the Version screen stops growing
    on every narrowed install with each deploy still reporting success."""
    from brain.ops import deployment_store

    for name in ("BRAIN_DATABASE_URL", "DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    seen: list[str] = []

    class StopHereError(Exception):
        pass

    def fake_engine(url: str) -> object:
        seen.append(url)
        raise StopHereError

    monkeypatch.setattr(deployment_store, "create_engine", fake_engine)
    with pytest.raises(StopHereError):
        main([], [a_line(a_deploy(1))])
    assert [normalise_database_url(one) for one in seen] == [expected]


def test_a_row_stores_the_links_digests_and_the_fingerprint_the_table_keeps_unique() -> None:
    """Delete this and the stored digest can be recomputed on read, which makes an edited row agree
    with itself."""
    link = DeploymentChain().append(a_deploy(1))

    row = row_of(link)

    assert row["entry_hash"] == link.entry_hash
    assert row["prev_hash"] == link.prev_hash
    assert row["fingerprint"] == link.deployment.fingerprint()
    assert row["task_ids"] == ["M1.1.1", "M38.1.3.5"]


# ------------------------------------------------------------- apart from the permission ledger
def test_nothing_that_builds_the_ledger_or_its_export_reads_the_deployment_history() -> None:
    """The requirement is that deployments stay out of the permission audit trail and out of the
    compliance export. Both are built under `brain.audit`, so no module there may import the
    history, and the migration adds no trigger and names no ledger table.

    Delete this and one import makes the release history part of what a client's auditor is
    handed as the record of who could see what."""
    deployment_modules = {
        "brain.ops.deployments",
        "brain.ops.deployment_history",
        "brain.ops.deployment_store",
        "brain.tables.deployment_record",
    }
    for path in (REPO / "src" / "brain" / "audit").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not (imported & deployment_modules), path

    migration = (REPO / "migrations" / "versions" / "0091_deployment_record.py").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line
        for line in migration.split('"""', 2)[2].splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "audit_entry" not in code
    assert "TRIGGER" not in code.upper()


def test_the_writer_is_reached_by_nothing_the_applications_sessions_run() -> None:
    """The application role may read the history and never write it. The write lives in a module
    no route imports, which is what keeps `brain.ops.application_privileges` from seeing an
    INSERT `0091` does not grant; the read does not.

    Delete this and the store can be imported by a route, after which a console request could
    record a deploy that never happened."""
    reach = reachable()

    assert "brain.ops.deployment_store" not in reach
    assert "brain.ops.deployment_history" in reach


# ----------------------------------------------------------------------------- with a server
DATABASE = "brain_test_deployment_history"


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0086")
        migrate(DATABASE, "upgrade", "0091")
        yield scratch
    finally:
        drop(DATABASE)


def test_the_deploy_records_once_and_the_application_role_reads_it_and_cannot_write_it(
    migrated: str,
) -> None:
    """The store runs as the login, twice over the same file, and the table holds each deploy once
    in chain order; `brain_app` reads them back into a history that holds, and is refused an
    insert.

    Delete this and the grant can widen, or the second reconcile the deploy runs every time can
    start writing duplicates, with every test over fakes still green."""
    first, second, third = a_deploy(1), a_deploy(2, "held_back", "sha256:bad"), a_deploy(3)
    engine = create_engine(normalise_database_url(migrated), poolclass=NullPool)
    try:
        with engine.begin() as conn:
            assert len(record(conn, [first, second])) == 2
        with engine.begin() as conn:
            assert len(record(conn, [first, second, third])) == 1
    finally:
        engine.dispose()

    with psycopg.connect(migrated) as conn:
        conn.execute("SET ROLE brain_app")
        rows = conn.execute(
            "SELECT seq, at, outcome, commit, image, previous, task_ids, prev_hash, entry_hash "
            "FROM ops.deployment_record ORDER BY seq"
        ).fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO ops.deployment_record (seq, at, outcome, commit, image, previous, "
                "prev_hash, entry_hash, fingerprint) VALUES (9, now(), 'deployed', 'x', 'x', 'x', "
                "repeat('0', 64), repeat('0', 64), repeat('1', 64))"
            )
        conn.rollback()

    names = (
        "seq",
        "at",
        "outcome",
        "commit",
        "image",
        "previous",
        "task_ids",
        "prev_hash",
        "entry_hash",
    )
    history = history_from([Stored(**dict(zip(names, row, strict=True))) for row in rows])
    assert [link.deployment.commit for link in history.shown] == ["c000003", "c000002", "c000001"]
    assert history.broken == ()
    # The store keeps task ids sorted, as the hash and the log reader do.
    assert history.shown[1].deployment == replace(second, task_ids=tuple(sorted(second.task_ids)))


def test_the_route_reads_the_history_on_the_applications_session(migrated: str) -> None:
    """`read_history` executes the route's own statement on a session running as `brain_app`.

    Delete this and the read can be written against a column or a schema the application role
    cannot reach, and the screen answers its sentence about a database that did not answer on
    every install."""
    from brain.session import make_application_sessions
    from tests.fixtures.scratch_postgres import engine as async_engine

    login = create_engine(normalise_database_url(migrated), poolclass=NullPool)
    try:
        with login.begin() as conn:
            record(conn, [a_deploy(1)])
    finally:
        login.dispose()

    answer = run(lambda: read_history(make_application_sessions(async_engine(migrated))))

    assert answer.unread == ""
    assert answer.deploys is not None and answer.deploys
    assert answer.holds is True
