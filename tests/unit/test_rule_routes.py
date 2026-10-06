"""Department fast-lane rules: the routes' decisions, the store, and `0199` on PostgreSQL.

The pure half asks the routes' functions with built reaches and a store that keeps rules in a
list: where a rule may be read and written, what id it is kept under, what a test answers, and
that every refusal of a rule out of reach reads as a rule that does not exist. The database half
builds PostgreSQL to head once and asks the table itself, as the application role: a rule written
in somebody else's name is refused, nothing a rule says can be updated, two departments may hold
the same words, and the loader reads each asker's department and the install's and nothing else.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.5.1
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Table, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex

from brain import rule_routes
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent, Denied
from brain.core.scope import Clause, Op, Scope
from brain.db import metadata
from brain.gate import rule_store
from brain.gate.fast_lane import FastPathRule
from brain.gate.rule_store import KeptRule, StoredRules
from brain.ops.classification_store import Writer
from brain.ops.migration_policy import check_file
from brain.rule_routes import (
    NO_SUCH_RULE,
    NOT_ADDED_INVALID,
    NOT_ADDED_TAKEN,
    NOT_YOUR_DEPARTMENT,
    RULE_READ,
    RULE_WRITE,
    TEST_ANSWERED,
    TEST_DID_NOT_MATCH,
    TEST_NOTHING,
    FastRuleAsked,
    FastRuleTried,
    added,
    candidate,
    may_read_at,
    may_write_at,
    readable,
    retired,
    stored_id,
    tried,
)
from brain.tables.fast_lane import FastPathRuleRow

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "versions" / "0199_department_fast_path_rules.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Pinned far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 1, 1, tzinfo=UTC)

SALES, STUDIO = "sales", "studio"
WRITER = Writer(actor_id="u_admin", ent_hash="0" * 32, trace_id="t_rules")


def in_department(department: str | None, *capabilities: Capability) -> EntitlementSet:
    """A reach holding these grants in one department, or everywhere for None."""
    scope = (
        Scope()
        if department is None
        else Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))
    )
    return EntitlementSet(
        principal_id="u_admin",
        grants=tuple(Grant(capability=one, scope=scope) for one in capabilities),
    )


SALES_ADMIN = in_department(SALES, RULE_READ, RULE_WRITE)
STUDIO_ADMIN = in_department(STUDIO, RULE_READ, RULE_WRITE)
INSTALL_ADMIN = in_department(None, RULE_READ, RULE_WRITE)
SALES_READER = in_department(SALES, RULE_READ)


def asked(department: str | None = SALES, name: str = "hours", **changed: str) -> FastRuleAsked:
    fields = {
        "name": name,
        "department": department,
        "template": "hours left on {client}",
        "slot": "client",
        "source": "laravel",
        "entity": "client",
        "match_field": "name",
        "answer_field": "hours_remaining",
        **changed,
    }
    return FastRuleAsked.model_validate(fields)


def kept(department: str | None, name: str = "hours") -> KeptRule:
    rule = candidate(asked(department, name))
    assert rule is not None
    return KeptRule(rule=rule, department=department, created_by="u_admin", created_at=NOW)


class ListedRules(StoredRules):
    """`StoredRules` over a list, so the routes' decisions are asked with no database."""

    def __init__(self, *rules: KeptRule, taken: bool = False) -> None:
        self.rules = list(rules)
        self.taken = taken
        self.retired: list[str] = []

    async def live(self) -> tuple[KeptRule, ...]:
        return tuple(one for one in self.rules if one.rule.rule_id not in self.retired)

    async def add(self, rule: FastPathRule, *, department: str | None, writer: Writer) -> bool:
        if self.taken:
            return False
        self.rules.append(
            KeptRule(rule=rule, department=department, created_by=writer.actor_id, created_at=NOW)
        )
        return True

    async def retire(self, rule_id: str, *, writer: Writer) -> bool:
        del writer
        self.retired.append(rule_id)
        return True


# ----------------------------------------------------------------- where a rule may be
def test_a_department_grant_reads_and_writes_its_own_department_and_no_other() -> None:
    """`A_RULE_IS_WRITTEN_UNDER_THE_GRANTS_A_TABLE_IS_CHANGED_UNDER`: the classification grants,
    asked at the rule's department. Delete this and a department administrator can write rules
    for every department, or for none, with nothing failing."""
    assert may_read_at(SALES_ADMIN, SALES, NOW)
    assert may_write_at(SALES_ADMIN, SALES, NOW)
    assert not may_read_at(SALES_ADMIN, STUDIO, NOW)
    assert not may_write_at(SALES_ADMIN, STUDIO, NOW)


def test_an_install_wide_rule_is_reached_only_by_a_grant_over_everything() -> None:
    """Install-wide rules stay the install administrator's. Delete this and a department grant
    can write a rule every department's askers are matched against."""
    assert not may_read_at(SALES_ADMIN, None, NOW)
    assert not may_write_at(SALES_ADMIN, None, NOW)
    assert may_read_at(INSTALL_ADMIN, None, NOW)
    assert may_write_at(INSTALL_ADMIN, None, NOW)
    assert may_write_at(INSTALL_ADMIN, SALES, NOW)


def test_writing_a_rule_needs_the_read_grant_as_well_as_the_write_grant() -> None:
    """A change is read and written at one place, as a classified table's is. Delete this and a
    write grant alone writes rules its holder could never list."""
    assert may_read_at(SALES_READER, SALES, NOW)
    assert not may_write_at(SALES_READER, SALES, NOW)
    assert not may_write_at(in_department(SALES, RULE_WRITE), SALES, NOW)


def test_the_rule_grants_are_the_classification_grants() -> None:
    """No new capability: an administrator who changes a department's tables writes its rules.
    Delete this and the screen can be gated on a capability no install has granted anybody."""
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE

    assert (RULE_READ, RULE_WRITE) == (CLASSIFICATION_READ, CLASSIFICATION_WRITE)
    assert (
        "classification" in rule_routes.A_RULE_IS_WRITTEN_UNDER_THE_GRANTS_A_TABLE_IS_CHANGED_UNDER
    )


def test_the_screen_is_answered_only_to_a_holder_of_the_grant_somewhere() -> None:
    """The routes' first gate: the grant held at some place, or one refusal for everybody else,
    in the words a missing rule gets. Delete this and the list is answered, empty, to anybody
    signed in, which tells them the screen exists for others."""
    from types import SimpleNamespace
    from typing import cast

    from brain.api_routes import Asking

    def asking(reach: EntitlementSet) -> Asking:
        # A stand-in carrying the three fields `_gate` reads; building a real `Asking` needs a
        # resolved caller, which says nothing more about this gate.
        caller = SimpleNamespace(principal=SimpleNamespace(id="u_admin"))
        return cast(Asking, SimpleNamespace(reach=reach, now=NOW, caller=caller))

    with pytest.raises(Denied) as refused:
        rule_routes._gate(asking(in_department(SALES, RULE_READ)), RULE_WRITE)
    assert refused.value.public_message == NO_SUCH_RULE
    rule_routes._gate(asking(SALES_ADMIN), RULE_WRITE)
    rule_routes._gate(asking(SALES_READER), RULE_READ)


# --------------------------------------------------------------------- what id it is kept under
def test_a_department_rule_is_kept_under_its_department_and_an_install_rule_under_its_name() -> (
    None
):
    """`A_RULE_OUT_OF_REACH_IS_A_RULE_THAT_DOES_NOT_EXIST`: two departments may use one name, so
    neither learns from a refusal that the other did. Delete this and a department adding a rule
    can be told another department holds that name."""
    assert stored_id(SALES, "hours") == "sales__hours"
    assert stored_id(STUDIO, "hours") == "studio__hours"
    assert stored_id(None, "hours") == "hours"


def test_a_name_holding_the_separator_is_kept_nowhere() -> None:
    """Without this an install-wide rule named `sales__hours` would be read as sales's rule by its
    id. Delete this and an install-wide id can impersonate a department's."""
    assert stored_id(None, "sales__hours") is None
    assert stored_id(SALES, "a__b") is None
    assert candidate(asked(None, "sales__hours")) is None


def test_a_candidate_is_validated_by_the_validator_every_stored_rule_passes() -> None:
    """Delete this and the console can write a rule the loader then refuses, which takes every
    rule on the install out of the lane with it."""
    rule = candidate(asked())
    assert rule is not None and rule.rule_id == "sales__hours"
    assert candidate(asked(template="hours left on {client} and {other}")) is None
    assert candidate(asked(SALES, "x" * 58)) is None


# ------------------------------------------------------------------------ the list
def test_the_list_holds_the_rules_at_places_the_reader_may_read_and_no_others() -> None:
    """Delete this and the Rules page lists another department's rules, which says what that
    department's people ask."""
    rules = (kept(SALES), kept(STUDIO), kept(None, "global"))
    assert [one.rule_id for one in readable(rules, SALES_READER, NOW)] == ["sales__hours"]
    assert {one.rule_id for one in readable(rules, INSTALL_ADMIN, NOW)} == {
        "sales__hours",
        "studio__hours",
        "global",
    }


# ------------------------------------------------------------------------ adding
def test_an_administrator_adds_a_rule_for_their_own_department() -> None:
    """The positive sibling of every refusal below. Delete this and a route that refuses everybody
    passes them all."""
    rules = ListedRules()
    written = asyncio.run(added(rules, asked(), reach=SALES_ADMIN, writer=WRITER, now=NOW))
    assert (written.done, written.rule_id) == (True, "sales__hours")
    assert [(one.rule.rule_id, one.department) for one in rules.rules] == [("sales__hours", SALES)]


def test_a_rule_for_another_department_or_the_install_is_refused_and_nothing_is_written() -> None:
    """Delete this and a department's administrator writes rules other departments' askers are
    matched against."""
    rules = ListedRules()
    for place in (STUDIO, None):
        with pytest.raises(Denied) as refused:
            asyncio.run(added(rules, asked(place), reach=SALES_ADMIN, writer=WRITER, now=NOW))
        assert refused.value.public_message == NOT_YOUR_DEPARTMENT
    assert rules.rules == []


def test_an_invalid_rule_and_a_taken_one_are_told_apart_from_a_written_one() -> None:
    """Delete this and the page says a rule is live that was never written."""
    invalid = asyncio.run(
        added(ListedRules(), asked(SALES, "x" * 58), reach=SALES_ADMIN, writer=WRITER, now=NOW)
    )
    taken = asyncio.run(
        added(ListedRules(taken=True), asked(), reach=SALES_ADMIN, writer=WRITER, now=NOW)
    )
    assert (invalid.done, invalid.told) == (False, NOT_ADDED_INVALID)
    assert (taken.done, taken.told) == (False, NOT_ADDED_TAKEN)


# ------------------------------------------------------------------------ retiring
def test_an_administrator_retires_their_own_departments_rule() -> None:
    """The positive sibling. Delete this and a retirement that refuses everybody passes the
    refusals below."""
    rules = ListedRules(kept(SALES))
    written = asyncio.run(retired(rules, "sales__hours", reach=SALES_ADMIN, writer=WRITER, now=NOW))
    assert written.done and rules.retired == ["sales__hours"]


def test_another_departments_rule_is_refused_in_the_words_a_missing_rule_gets() -> None:
    """DENIED and ABSENT are one refusal. Delete this and retiring by a guessed id tells a
    department which rule ids another department holds."""
    rules = ListedRules(kept(STUDIO), kept(None, "global"))
    told = []
    for rule_id in ("studio__hours", "global", "sales__nothing"):
        with pytest.raises(Absent) as refused:
            asyncio.run(retired(rules, rule_id, reach=SALES_ADMIN, writer=WRITER, now=NOW))
        told.append(refused.value.public_message)
    assert told == [NO_SUCH_RULE] * 3
    assert rules.retired == []


def test_a_rule_retired_meanwhile_is_refused_as_missing() -> None:
    """Delete this and two administrators retiring one rule are both told it worked, and the
    second one's ledger entry names a retirement that did not happen."""

    class Raced(ListedRules):
        async def retire(self, rule_id: str, *, writer: Writer) -> bool:
            del rule_id, writer
            return False

    with pytest.raises(Absent):
        asyncio.run(
            retired(Raced(kept(SALES)), "sales__hours", reach=SALES_ADMIN, writer=WRITER, now=NOW)
        )


# ------------------------------------------------------------------------ testing
def wired(monkeypatch: pytest.MonkeyPatch, *rows: dict[str, str]) -> None:
    """The lane's readers and classification, as `tests/unit/test_fast_lane.py` builds them."""
    from tests.unit.test_fast_lane import CLIENTS, RecordingSource, readers_for

    async def wiring(state: Any) -> tuple[Any, Any, Any]:
        del state
        return readers_for(RecordingSource(*rows)), {"client": CLIENTS.policy()}, {}

    monkeypatch.setattr(rule_routes, "lane_wiring_of", wiring)


def trial(question: str, department: str | None = SALES) -> FastRuleTried:
    return FastRuleTried.model_validate({**asked(department).model_dump(), "question": question})


SEES_HOURS = (
    Capability(value="read:client"),
    Capability(value="read:client.name"),
    Capability(value="read:client.hours_remaining"),
)


def test_a_test_says_what_the_rule_would_answer_and_saves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`A_TEST_IS_THE_LANE_AT_THE_TESTERS_OWN_REACH`. Delete this and the Test button can answer
    nothing for every rule, and an administrator learns a rule is wrong from the people it
    answered."""
    from tests.unit.test_fast_lane import ACME

    wired(monkeypatch, ACME)
    reach = in_department(None, RULE_READ, RULE_WRITE, *SEES_HOURS)
    seen = asyncio.run(tried(object(), trial("hours left on Acme"), reach=reach, now=NOW))
    assert (seen.matches, seen.answer, seen.told) == (True, "12", TEST_ANSWERED)


def test_a_test_at_a_reach_that_cannot_read_the_field_answers_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tester's own reach, never the lane's. Delete this and the Test button reads any column
    of any table to an administrator who holds only the rule grants."""
    from tests.unit.test_fast_lane import ACME

    wired(monkeypatch, ACME)
    seen = asyncio.run(tried(object(), trial("hours left on Acme"), reach=SALES_ADMIN, now=NOW))
    assert (seen.matches, seen.answer, seen.told) == (True, None, TEST_NOTHING)


def test_a_test_by_a_reader_of_the_record_but_not_the_column_answers_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The redactor at the tester's reach, for a tester who may read the record and its name but
    not the column the rule answers with. Delete this and the Test button reads a withheld column
    to anybody who can see the row it sits on."""
    from tests.unit.test_fast_lane import ACME

    wired(monkeypatch, ACME)
    reach = in_department(
        None,
        RULE_READ,
        RULE_WRITE,
        Capability(value="read:client"),
        Capability(value="read:client.name"),
    )
    seen = asyncio.run(tried(object(), trial("hours left on Acme"), reach=reach, now=NOW))
    assert (seen.matches, seen.answer, seen.told) == (True, None, TEST_NOTHING)


def test_a_question_not_in_the_rules_words_is_told_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a test cannot tell an administrator their words are wrong from their data
    being missing."""
    wired(monkeypatch)
    seen = asyncio.run(
        tried(object(), trial("how many hours are left on Acme"), reach=SALES_ADMIN, now=NOW)
    )
    assert (seen.matches, seen.answer, seen.told) == (False, None, TEST_DID_NOT_MATCH)


def test_a_test_at_another_department_is_refused_before_anything_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a department's administrator can test rules over another department's
    tables, which is reading them."""

    async def never(state: Any) -> Any:
        raise AssertionError("the lane was wired for a refused test")

    monkeypatch.setattr(rule_routes, "lane_wiring_of", never)
    with pytest.raises(Denied):
        asyncio.run(
            tried(object(), trial("hours left on Acme", STUDIO), reach=SALES_ADMIN, now=NOW)
        )


# ------------------------------------------------------------------------ the reasons
def test_each_reason_is_written_down_where_a_reviewer_reads_it() -> None:
    """The constants are how the rules survive the person who wrote them, and each one names the
    property its tests above hold. Delete this and a constant can be emptied with the tests still
    green."""
    assert "on every question" in rule_store.A_RULE_ANSWERS_FROM_THE_NEXT_QUESTION
    assert "never off their grants" in rule_store.A_DEPARTMENTS_RULE_ANSWERS_ITS_OWN_ASKERS_ALONE
    assert "a missing rule gets" in rule_routes.A_RULE_OUT_OF_REACH_IS_A_RULE_THAT_DOES_NOT_EXIST
    assert "reach" in rule_routes.A_TEST_IS_THE_LANE_AT_THE_TESTERS_OWN_REACH


# ------------------------------------------------------------------------ the loader's query
def test_the_loader_reads_the_install_s_rules_and_the_asker_s_department_s() -> None:
    """`A_DEPARTMENTS_RULE_ANSWERS_ITS_OWN_ASKERS_ALONE`, read off the compiled statement. Delete
    this and the department filter can go with the database tests skipped."""
    sales = str(rule_store.live_rules(SALES).compile(dialect=DIALECT))
    nobody = str(rule_store.live_rules(None).compile(dialect=DIALECT))
    assert "gate.fast_path_rule.deleted_at IS NULL" in sales
    assert ("gate.fast_path_rule.department IS NULL OR gate.fast_path_rule.department =") in sales
    assert "gate.fast_path_rule.deleted_at IS NULL" in nobody
    assert "gate.fast_path_rule.department IS NULL" in nobody
    assert "gate.fast_path_rule.department =" not in nobody


# ------------------------------------------------------------------------ 0199
def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0199", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(direction: str) -> str:
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "target_metadata": metadata},
    )
    with Operations.context(context):
        getattr(migration(), direction)()
    return " ".join(buffer.getvalue().split())


def test_the_migration_copies_the_models_department_check_and_index() -> None:
    """The migration copies the slug grammar rather than importing it. Delete this and the model
    and the database can disagree about what a department is, which surfaces as a rule the
    console accepts and the insert refuses."""
    from brain.tables import fast_lane as model

    module = migration()
    assert module.DEPARTMENT_IS_A_SLUG == model.DEPARTMENT_IS_A_SLUG
    assert module.NAME_CHARS == model.NAME_CHARS
    upgrade = rendered("upgrade")
    table = FastPathRuleRow.__table__
    assert isinstance(table, Table)
    [index] = [
        one for one in table.indexes if one.name == "uq_fast_path_rule_template_department_live"
    ]
    assert " ".join(str(CreateIndex(index).compile(dialect=DIALECT)).split()) in upgrade
    assert "ALTER TABLE gate.fast_path_rule ADD COLUMN department VARCHAR(60)" in upgrade
    assert "DROP INDEX gate.uq_fast_path_rule_template_live" in upgrade


def test_the_migration_holds_the_author_to_the_writer_and_changes_no_grant() -> None:
    """Delete this and the insert policy can go back to `WITH CHECK (true)` with only the
    database tests below to say so, or a grant can be taken away from the previous release."""
    upgrade = rendered("upgrade")
    assert "DROP POLICY fast_path_rule_writable ON gate.fast_path_rule" in upgrade
    assert "WITH CHECK (created_by = current_setting('brain.actor_id', true))" in upgrade
    assert "GRANT " not in upgrade
    assert "REVOKE " not in upgrade


def test_the_migration_leaves_a_schema_the_previous_release_can_use() -> None:
    """The deployment compatibility gate on this file alone, so a narrowing added here fails in
    this module's own run rather than in the repository-wide one. Delete this and the department
    index can go back to an expression the gate reads as a narrowing, or a grant can be revoked,
    and the failure is found by whoever next runs the whole suite."""
    from brain.deployment.compatibility import breaking_changes

    assert breaking_changes(MIGRATION.read_text(encoding="utf-8")) == ()


def test_the_downgrade_refuses_rows_the_old_index_would_not_admit_and_puts_0019_back() -> None:
    """Delete this and a downgrade builds a unique index over rows that violate it, and fails
    half-way with the policies already changed."""
    down = rendered("downgrade")
    assert down.index("two live rules share a template") < down.index("DROP POLICY")
    assert "WITH CHECK (true)" in down
    assert "CREATE UNIQUE INDEX uq_fast_path_rule_template_live" in down
    assert "ALTER TABLE gate.fast_path_rule DROP COLUMN department" in down


def test_the_migration_creates_no_table_and_satisfies_the_migration_policy() -> None:
    """Delete this and the file is the one migration the policy never reads."""
    assert migration().TABLES == ()
    assert migration().revision == "0199"
    assert check_file(MIGRATION) == []


# ------------------------------------------------------------------------ on PostgreSQL
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_rule_routes") as url:
        yield url


def as_app(url: str, *statements: str, actor: str | None = "u_admin") -> list[Any]:
    """Statements in one transaction as `brain_app`, attributed to `actor`, committed."""
    import psycopg

    out: list[Any] = []
    with psycopg.connect(url, options="-c role=brain_app") as conn:
        if actor is not None:
            conn.execute("SELECT set_config('brain.actor_id', %s, true)", (actor,))
        for statement in statements:
            cursor = conn.execute(statement)
            out.append(cursor.fetchall() if cursor.description else cursor.rowcount)
    return out


def insert(rule_id: str, template: str, department: str | None, created_by: str = "u_admin") -> str:
    where = "NULL" if department is None else f"'{department}'"
    # Every value is one of this module's literals, never input.
    return (
        "INSERT INTO gate.fast_path_rule (rule_id, template, slot, source, entity, match_field,"  # noqa: S608
        f" answer_field, created_by, department) VALUES ('{rule_id}', '{template}', 'sku',"
        f" 'crm', 'client', 'sku', 'price', '{created_by}', {where})"
    )


@pytest.mark.needs_db
def test_a_rule_written_in_somebody_elses_name_is_refused(database: str) -> None:
    """Delete this and the insert policy can go back to `WITH CHECK (true)`, so a rule answering
    with no model can name anybody as its author."""
    import psycopg

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, insert("forged", "forged price of item {sku}", None, "u_other"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, insert("unnamed", "unnamed price of item {sku}", None), actor=None)
    as_app(database, insert("own", "own price of item {sku}", None))


@pytest.mark.needs_db
def test_two_departments_may_hold_the_same_words_and_one_department_may_not_twice(
    database: str,
) -> None:
    """Delete this and either the second department is refused, and told the first wrote those
    words, or one department holds two rules that both match and so answer neither."""
    import psycopg

    words = "shared price of item {sku}"
    as_app(
        database,
        insert("sales__shared", words, SALES),
        insert("studio__shared", words, STUDIO),
        insert("shared", words, None),
    )
    for rule_id, department in (("sales__again", SALES), ("again", None)):
        with pytest.raises(psycopg.errors.UniqueViolation):
            as_app(database, insert(rule_id, words, department))


@pytest.mark.needs_db
def test_a_department_that_is_not_a_slug_is_refused(database: str) -> None:
    """Delete this and a department nobody's grant can name holds a rule nobody can retire."""
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(database, insert("bad", "bad price of item {sku}", "Not A Slug"))


@pytest.mark.needs_db
def test_the_store_adds_reads_per_department_and_retires(database: str) -> None:
    """The store end to end as the application role: a rule the console adds is read for its own
    department's askers and nobody else's, a second add of its words is refused, and a retired
    rule is read by nobody. Delete this and every decision above is tested over a list."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from brain.db import normalise_database_url

    async def run() -> tuple[Sequence[str], ...]:
        engine = create_async_engine(
            normalise_database_url(database),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = StoredRules(sessions)
        try:
            rule = candidate(asked(SALES, "store", template="store hours left on {client}"))
            assert rule is not None
            first = await store.add(rule, department=SALES, writer=WRITER)
            again = await store.add(rule, department=SALES, writer=WRITER)
            sales = rule_store.rule_ids(await rule_store.load_rules(sessions, department=SALES))
            studio = rule_store.rule_ids(await rule_store.load_rules(sessions, department=STUDIO))
            listed = [one.department for one in await store.live() if one.rule == rule]
            gone = await store.retire(rule.rule_id, writer=WRITER)
            twice = await store.retire(rule.rule_id, writer=WRITER)
            after = rule_store.rule_ids(await rule_store.load_rules(sessions, department=SALES))
            return (
                (str(first), str(again), str(gone), str(twice)),
                sales,
                studio,
                tuple(str(one) for one in listed),
                after,
            )
        finally:
            await engine.dispose()

    flags, sales, studio, listed, after = asyncio.run(run())
    assert flags == ("True", "False", "True", "False")
    assert "sales__store" in sales
    assert "sales__store" not in studio
    assert listed == (SALES,)
    assert "sales__store" not in after
