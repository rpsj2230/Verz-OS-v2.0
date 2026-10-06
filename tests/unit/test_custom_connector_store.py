"""A connector definition is kept, reviewed by a second person, and sent back for review if changed.

The first half needs no server: the migration's copied grammars and vocabularies held to the live
ones. The second builds a database at head and drives `0181`'s table as the application role,
attributed as a route attributes it: a submission is kept waiting and on the ledger, the submitter's
own approval is refused by the store and by the database, a second person's is kept with them named,
a decision on a revision that has moved is refused, a change sends an approved definition back to
waiting, and only an approved one is read into the catalogue. **It skips when there is no server**,
and CI always has one.

Task ids: M11.7.8
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
import pytest
from sqlalchemy import String

from brain.audit.ledger import IDENTIFIER
from brain.connectors.declaration import CredentialShape
from brain.ops import connector_catalogue
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.custom_connector import MAX_LABEL, SCHEMES, ReviewState
from brain.ops.custom_connector_store import (
    DefinitionMovedError,
    OwnDefinitionError,
    StoredCustomConnectors,
    approved_in,
    refresh,
)
from brain.session import make_session_factory
from brain.tables import custom_connector as model
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_custom_connector import definition
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION: Final = VERSIONS / "0181_custom_connector.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

NAME: Final = "widgets_api"


# ------------------------------------------------------------ the migration and the model
def test_the_migration_copies_the_live_grammars_widths_and_vocabularies() -> None:
    """Delete this and the table `0181` builds can drift from the names, identifiers, states and
    schemes the product writes, so a definition the domain accepts is refused by a constraint
    nobody updated, or one it refuses is admitted."""
    migration = migration_module(MIGRATION)
    assert migration.CONNECTOR_NAME_PATTERN == CONNECTOR_NAME_PATTERN
    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.CONNECTOR_CHARS == CONNECTOR_CHARS
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert migration.LABEL_CHARS == model.LABEL_CHARS == MAX_LABEL
    for name in ("CITED_CHARS", "DEPARTMENT_CHARS", "PARAMETER_CHARS", "DOCUMENT_BYTES"):
        assert getattr(migration, name) == getattr(model, name), name
    assert migration.DEPARTMENT_PATTERN == model.DEPARTMENT_PATTERN
    assert set(migration.STATES) == set(model.STATES) == {one.value for one in ReviewState}
    assert set(migration.KEY_SCHEMES) == set(model.KEY_SCHEMES) == {one.value for one in SCHEMES}
    shapes = {one.value for one in SCHEMES.values()}
    assert set(migration.CREDENTIAL_SHAPES) == set(model.CREDENTIAL_SHAPES) == shapes
    assert CredentialShape.KEY.value in shapes
    column = model.CustomConnectorRow.__table__.c.name
    assert isinstance(column.type, String) and column.type.length == CONNECTOR_CHARS


def test_the_department_pattern_has_no_group_sqlalchemy_would_read_as_a_parameter() -> None:
    """CLAUDE.md's `(?:` defect: a non-capturing group in a check constraint was rendered as NULL.
    Delete this and the department's constraint can ship as a different one from the one written."""
    assert "(?" not in model.DEPARTMENT_PATTERN
    assert "(?" not in migration_module(MIGRATION).DEPARTMENT_PATTERN


# ------------------------------------------------------------------ against a database
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_custom_connector_store") as url:
        yield url


def as_app(url: str, actor: str) -> psycopg.Connection[Any]:
    """The application role, with the transaction attributed to `actor` as a route does it."""
    conn = psycopg.connect(url, autocommit=True)
    conn.execute("SET ROLE brain_app")
    conn.execute("SELECT set_config('brain.actor_id', %s, false)", (actor,))
    return conn


def with_store(url: str, work: Any) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await work(StoredCustomConnectors(make_session_factory(engine)), engine)
        finally:
            await engine.dispose()

    return run(go)


def ledger(url: str, name: str) -> list[tuple[str, str, int]]:
    return [
        (actor, details["change"], details["revision"])
        for actor, details in sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE subject = %s ORDER BY seq",
            f"connector:{name}",
        )
    ]


@pytest.mark.needs_db
def test_a_definition_is_kept_waiting_reviewed_by_a_second_person_and_written_to_the_ledger(
    install: str,
) -> None:
    """The positive path, as the application role: submitted, it waits and is not in the approved
    set; the submitter's own approval is refused; a second person's is kept with them named, and
    the approved set then holds it; every step is a ledger entry under the source's subject.
    Delete this and the review can be skipped, or decided by its submitter, with nothing
    recorded."""
    name = f"{NAME}_one"

    async def work(store: StoredCustomConnectors, engine: Any) -> Any:
        sessions = make_session_factory(engine)
        kept = await store.submit(
            definition(name=name), by="u_definer", ent_hash="0" * 32, trace_id="t-submit"
        )
        async with sessions() as session:
            waiting = await approved_in(session)
        with pytest.raises(OwnDefinitionError):
            await store.decide(
                name,
                approve=True,
                revision=1,
                by="u_definer",
                at=LONG_AGO,
                ent_hash="0" * 32,
                trace_id="t-own",
            )
        decided = await store.decide(
            name,
            approve=True,
            revision=1,
            by="u_reviewer",
            at=LONG_AGO,
            ent_hash="0" * 32,
            trace_id="t-review",
        )
        async with sessions() as session:
            approved = await approved_in(session)
        return kept, waiting, decided, approved

    kept, waiting, decided, approved = with_store(install, work)
    assert (kept.state, kept.definition.revision, kept.submitted_by) == (
        ReviewState.UNREVIEWED,
        1,
        "u_definer",
    )
    assert name not in waiting
    assert (decided.state, decided.reviewed_by) == (ReviewState.APPROVED, "u_reviewer")
    assert approved[name].name == name
    assert ledger(install, name) == [
        ("u_definer", "definition_submitted", 1),
        ("u_reviewer", "definition_approved", 1),
    ]


@pytest.mark.needs_db
def test_the_database_refuses_a_definition_approved_by_its_own_submitter(install: str) -> None:
    """`0181`'s constraint and update policy, asked directly with the store's own refusal not in
    the way: a row whose reviewer is its submitter is refused even when the actor is that person.
    Delete this and a route that forgot to ask lets a submitter approve their own."""
    name = f"{NAME}_own"
    with_store(
        install,
        lambda store, engine: store.submit(
            definition(name=name), by="u_definer", ent_hash="0" * 32, trace_id="t-own"
        ),
    )
    with (
        as_app(install, "u_definer") as conn,
        pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.InsufficientPrivilege)),
    ):
        conn.execute(
            "UPDATE ops.custom_connector SET state = 'approved', reviewed_by = 'u_definer', "
            "reviewed_at = now() WHERE name = %s",
            (name,),
        )
    with as_app(install, "u_other") as conn:
        conn.execute(
            "UPDATE ops.custom_connector SET state = 'approved', reviewed_by = 'u_other', "
            "reviewed_at = now() WHERE name = %s",
            (name,),
        )
    assert sql(install, "SELECT state FROM ops.custom_connector WHERE name = %s", name) == [
        ("approved",)
    ]


@pytest.mark.needs_db
def test_a_changed_definition_waits_for_review_again_and_leaves_the_approved_set(
    install: str,
) -> None:
    """`A_CHANGED_DEFINITION_WAITS_FOR_A_SECOND_PERSON_AGAIN`, and a decision on the revision read
    before the change is refused. Delete this and an edit after approval is offered unread."""
    name = f"{NAME}_changed"

    async def work(store: StoredCustomConnectors, engine: Any) -> Any:
        sessions = make_session_factory(engine)
        at = {"ent_hash": "0" * 32, "trace_id": "t-change"}
        await store.submit(definition(name=name), by="u_definer", **at)
        await store.decide(name, approve=True, revision=1, by="u_reviewer", at=LONG_AGO, **at)
        changed = await store.change(
            definition(name=name, label="Widgets, changed"), by="u_definer", **at
        )
        async with sessions() as session:
            after = await approved_in(session)
        with pytest.raises(DefinitionMovedError):
            await store.decide(name, approve=True, revision=1, by="u_reviewer", at=LONG_AGO, **at)
        again = await store.decide(
            name, approve=True, revision=2, by="u_reviewer", at=LONG_AGO, **at
        )
        return changed, after, again

    changed, after, again = with_store(install, work)
    assert (changed.state, changed.definition.revision, changed.reviewed_by) == (
        ReviewState.UNREVIEWED,
        2,
        None,
    )
    assert changed.definition.label == "Widgets, changed"
    assert name not in after
    assert (again.state, again.definition.revision) == (ReviewState.APPROVED, 2)


@pytest.mark.needs_db
def test_refresh_serves_the_approved_set_and_an_unreadable_one_serves_none(install: str) -> None:
    """What every request and every worker cycle calls. Delete this and an approval reaches the
    table and never the process, or a failed read keeps serving what was last approved."""

    async def work(store: StoredCustomConnectors, engine: Any) -> Any:
        del store
        changed = await refresh(make_session_factory(engine))
        served = dict(connector_catalogue.reviewed())
        return changed, served

    try:
        _, served = with_store(install, work)
        assert f"{NAME}_one" in served

        def broken() -> Any:
            raise RuntimeError("no database")

        assert run(lambda: refresh(broken)) is True  # type: ignore[arg-type]
        assert dict(connector_catalogue.reviewed()) == {}
    finally:
        connector_catalogue.install({})
