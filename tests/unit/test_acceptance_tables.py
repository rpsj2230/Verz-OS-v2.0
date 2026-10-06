"""The classified tables' install acceptance checks: registered, read, passing, and able to fail.

The pure half holds the three checks to the leaves they prove and to the work breakdown, holds the
CSV and the XLSX the checks build to the product's own reader, holds the marks the upload check
expects to the ones a first upload gives, holds the gate the checks restate to the Classification
routes' own function over every combination of grants, channel and sign-in, and measures the
collision `TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS` is about.

The database half builds PostgreSQL to head once for the module, commits a price list of the
install's own into it the way an administrator's upload leaves one, and runs the checks as the
worker would: each passes, and every table they write to holds, row for row, what it held before.
Then the property each check proves is broken, one at a time, by replacing the product function
the check relies on where the check looks it up, and the check fails with its own sentence. A check
that cannot fail would pass on an install that does not do what its leaf says.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from brain.ops import acceptance_checks_tables as tables
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_tables"

#: Each table check and the leaves it proves, as the coordinator scoped them.
LEAVES = {
    "a_price_list_upload_classifies_every_column": ("M7.5.1",),
    "a_reader_without_the_cost_grant_is_told_the_sell_price_alone": ("M7.5.2",),
    "an_applied_mark_is_in_the_ledger_under_the_administrator": ("M7.5.3",),
}

#: Every table the table checks write to, which must hold afterwards exactly what it held before.
#: Measured rather than guessed: on a fresh database at head, the tables whose insert, update or
#: delete counters in `pg_stat_user_tables` moved across one run of the three checks, rolled back
#: as every write of theirs is.
WRITTEN_BY_TABLE_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "know.classified_table",
    "know.classified_row",
)

#: The two counters every grant moves, which the suite's own list does not name. Every check that
#: grants anything writes both, so the gap is the suite's rather than this module's; they are held
#: row for row by this module's database test until the suite's list names them.
COUNTERS = frozenset({"gate.grants_version", "gate.policy_epoch"})

#: The price list the install already holds before any check runs, under a name of its own.
OWN_TABLE = "prices"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)

#: A service name as the lane's question slot takes one: a single word nothing else holds.
SERVICE = "QZ0123456789ABCDEF"


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def one(name: str) -> Check:
    [found] = [check for check in mine() if check.name == name]
    return found


def words(columns: Sequence[str], services: int = 2) -> list[dict[str, str]]:
    """Rows of distinct words, keyed by column, as the checks fill a price list."""
    return [
        {column: f"QZ{service}{position:02d}ABCDEF" for position, column in enumerate(columns)}
        for service in range(services)
    ]


# ------------------------------------------------------------------------ without a server
def test_the_table_checks_prove_the_classification_leaves_and_nothing_else() -> None:
    """Each check names the one leaf it was scoped to. Delete this and a check can close a leaf it
    does not exercise, or fall out of its module with the Install page listing one row fewer."""
    assert {check.name: check.leaves for check in mine()} == LEAVES


def test_every_leaf_the_table_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Held against
    `docs/wbs.json`, which is outside the registry. Delete this and a result can close the wrong
    leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_table_checks_write_is_one_the_suite_measures() -> None:
    """The suite's own run test counts `WRITTEN_BY_CHECKS` before and after the whole run, and
    every table these checks write is in it but the two `COUNTERS`. Delete this and a table these
    checks write can be left out of that count, so a check that committed a row to it would pass
    the suite."""
    assert set(WRITTEN_BY_TABLE_CHECKS) - set(WRITTEN_BY_CHECKS) <= COUNTERS


@pytest.mark.parametrize(
    ("headings", "columns"),
    [
        (tables.PRICE_LIST_HEADINGS, tables.PRICE_LIST_COLUMNS),
        (tables.ASKED_HEADINGS, tables.ASKED_COLUMNS),
    ],
)
@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_the_files_the_checks_upload_are_read_by_the_product_as_the_price_list_they_hold(
    headings: tuple[str, ...], columns: tuple[str, ...], suffix: str
) -> None:
    """Both files, both price lists, through `brain.knowledge.table_file.read_table_file`, the
    reader the upload route calls: the headings as typed, the columns the check expects, and every
    row. The columns are written out in the check module rather than derived there, so this holds
    the parser to them instead of the parser agreeing with itself. Delete this and an XLSX the
    product cannot read reaches the owner's server as a failed upload check, or a CSV the product
    reads differently passes a check about a different table."""
    from brain.knowledge.table_file import read_table_file

    rows = words(columns)
    grid = [[row[column] for column in columns] for row in rows]
    build = tables.price_list_csv if suffix == ".csv" else tables.price_list_xlsx

    parsed = read_table_file(f"acceptance{suffix}", build(headings, grid))

    assert parsed.headings == headings
    assert parsed.columns == columns
    assert list(parsed.rows) == rows


def test_the_marks_the_upload_check_expects_are_the_ones_a_first_upload_gives() -> None:
    """`FIRST_MARKS` against `next_upload` and `view_of`, which live outside the check, and all
    three marks among them, because the leaf is that each column is classified open, restricted
    or derived. Delete this and the check can expect marks no install gives, or prove only two of
    the three words."""
    from brain.classification_routes import view_of
    from brain.knowledge.classified_rows import next_upload

    table = next_upload(
        None,
        entity="acceptance_pure_csv",
        title="Price list",
        key_column="name",
        columns=tables.PRICE_LIST_COLUMNS,
    )
    view = view_of(table.classification, editable=True, stored=table)

    shown = {column.column: (column.access, tuple(column.derived_from)) for column in view.columns}
    assert shown == tables.FIRST_MARKS
    assert {mark for mark, _ in tables.FIRST_MARKS.values()} == {"open", "restricted", "derived"}


def reaches() -> Iterator[tuple[str, Any, Any, Any]]:
    """Every combination of the two classification grants, the channel and the sign-in."""
    from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel

    capabilities = (CLASSIFICATION_READ, CLASSIFICATION_WRITE)
    for mask in range(4):
        held = EntitlementSet(
            principal_id="acceptance.pure.a.person",
            grants=tuple(
                Grant(capability=one, scope=Scope.department("acceptance_a"))
                for bit, one in enumerate(capabilities)
                if mask & (1 << bit)
            ),
        )
        for channel in (Channel.CONSOLE, Channel.API):
            for assurance in Assurance:
                yield (
                    f"{mask}-{channel}-{assurance.name}",
                    admit(held, channel, assurance),
                    channel,
                    (assurance),
                )


def test_the_gate_the_checks_restate_is_the_classification_routes_own() -> None:
    """`THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN`: `may_change` against the route's
    `_may_change` for every combination of grants, channel and sign-in, and both answers seen, so
    the agreement is not two functions refusing everything. Delete this and the route can come to
    ask for a third grant while every check keeps proving the old gate."""
    from brain.api_routes import Asking
    from brain.classification_routes import _may_change
    from brain.identity.bearer import Caller

    answers = set()
    for label, reach, channel, _ in reaches():
        # The route reads only the reach and the instant; the caller is never looked at.
        asked = Asking(caller=cast(Caller, None), reach=reach, channel=channel, now=NOW)
        ours = tables.may_change(reach, NOW)
        assert ours == _may_change(asked), label
        answers.add(ours)
    assert answers == {True, False}


class NoRows:
    """A row source that holds nothing, for a lane that is only matched against."""

    async def rows(self, query: Any) -> Sequence[Mapping[str, Any]]:
        return ()


class OneService:
    """A row source holding one service of one table, returning what the statement selects."""

    def __init__(self, entity: str, row: Mapping[str, str]) -> None:
        self.entity = entity
        self.row = row

    async def rows(self, query: Any) -> Sequence[Mapping[str, Any]]:
        if query.entity != self.entity:
            return ()
        held = {"entity": query.entity, "id": "0", **self.row}
        return ({one.name: held.get(one.name) for one in query.statement.selected_columns},)


def test_two_uploaded_price_lists_are_asked_in_the_same_words_and_the_check_s_own_answers() -> None:
    """`TWO_PRICE_LISTS_ARE_ASKED_IN_THE_SAME_WORDS_AND_EACH_ANSWERS`, measured on the product's
    matcher: with an install's own price list beside the check's, the sell price question matches a
    rule of each, so the collision is real on any install holding a price list, and the lane now
    answers the check's service from the check's list for a reader of it alone. Delete this and the
    check can go back to asking its own rules, which is how it passed an install where a second
    price list silenced the first."""
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.gate.fast_lane import FastLaneAnswer, entities_served, match_rule, respond
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of, lane_for, next_upload
    from brain.knowledge.columns import table_capability

    ours, theirs = (
        next_upload(
            None, entity=name, title=name, key_column="name", columns=tables.PRICE_LIST_COLUMNS
        )
        for name in ("acceptance_pure_prices", OWN_TABLE)
    )
    row = {"name": SERVICE, "sell_price": "QZ9"}
    lane = lane_for([ours, theirs], OneService(ours.entity, row))
    question = QUESTION_SHAPES[0].format(label=label_of(tables.SELL_PRICE), slot=SERVICE)
    reader = EntitlementSet(
        principal_id="acceptance.pure.a.reader",
        grants=(Grant(capability=table_capability(ours.entity), scope=Scope.unrestricted()),),
    )

    assert match_rule(question, lane.rules, served=entities_served(lane.readers)) is None
    found = asyncio.run(
        respond(question, rules=lane.rules, readers=lane.readers, entitlement=reader, now=NOW)
    )
    assert isinstance(found, FastLaneAnswer) and found.entity == ours.entity
    assert [one.model_dump().get(tables.SELL_PRICE) for one in found.result.records] == ["QZ9"]


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine
    from brain.settings import settings_from

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

    return {result.name: (result.outcome, result.reason) for result in asyncio.run(run())}


def a_price_list_of_the_install_s_own(url: str) -> None:
    """A price list committed as the application role, as an administrator's upload leaves one,
    so the checks run on an install already holding a table asked about in their words."""
    from brain.db import normalise_database_url
    from brain.knowledge.classified_rows import next_upload
    from brain.ops.classification_store import SqlClassifiedTables, Writer
    from brain.session import make_app_engine, make_application_sessions

    async def go() -> None:
        engine = make_app_engine(normalise_database_url(url))
        try:
            store = SqlClassifiedTables(make_application_sessions(engine))
            table = next_upload(
                None,
                entity=OWN_TABLE,
                title="Price list",
                key_column="name",
                columns=tables.PRICE_LIST_COLUMNS,
            )
            await store.upload(
                table,
                words(tables.PRICE_LIST_COLUMNS),
                writer=Writer(actor_id="u_owner", ent_hash="a" * 32, trace_id="seeded"),
            )
        finally:
            await engine.dispose()

    asyncio.run(go())


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every check rolls back, so they can share it."""
    with at_head("brain_acceptance_tables") as url:
        a_price_list_of_the_install_s_own(url)
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_TABLE_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_every_table_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The three checks as the worker runs them, against PostgreSQL at head, on an install that
    already holds a price list of its own.** Each passes with no reason, and every table any of
    them wrote to, the classified tables and the ledger among them, holds row for row what it held
    before, the install's own price list included. Delete this and a check that cannot pass on the
    real schema, or one that commits a price list to a client's install, reaches the owner's
    server first."""
    before = contents(database)
    outcomes = run_checks(database, mine())
    after = contents(database)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before
    assert before["know.classified_table"][0] == 1


# ------------------------------------------------------------- each check can fail
def refused(database: str, name: str) -> tuple[str, str]:
    return run_checks(database, (one(name),))[name]


@pytest.mark.needs_db
def test_the_upload_check_fails_when_a_first_upload_leaves_every_column_restricted(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first classification that opens and derives nothing is default-deny with no price list
    behind it: the sell price is withheld from the whole company. Delete this and the upload check
    can pass on an install whose uploads classify nothing as the leaf says."""
    from brain.knowledge import classified_rows
    from brain.knowledge.columns import ColumnAccess, TableClassification, marked

    def restricted(entity: str, columns: Sequence[str]) -> TableClassification:
        return TableClassification(
            entity=entity,
            rules=tuple(marked(entity, column, ColumnAccess.RESTRICTED) for column in columns),
        )

    monkeypatch.setattr(classified_rows, "first_classification", restricted)

    assert refused(database, "a_price_list_upload_classifies_every_column") == (
        FAILED,
        "an uploaded price list's columns were not each held as open, restricted or derived as "
        "the shipped price list marks them",
    )


@pytest.mark.needs_db
def test_the_upload_check_fails_when_an_xlsx_price_list_cannot_be_read(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CSV half passing is not the XLSX half passing. Delete this and an install that refuses
    every workbook passes a check whose leaf names both."""
    from brain.knowledge import table_file

    def unreadable(content: bytes) -> Iterator[list[str]]:
        raise table_file.TableFileError("the .xlsx file is not a workbook")

    monkeypatch.setattr(table_file, "_xlsx_grid", unreadable)

    assert refused(database, "a_price_list_upload_classifies_every_column") == (
        FAILED,
        "a well-formed price list, uploaded as a CSV or an XLSX, was refused as the upload route "
        "refuses one",
    )


ASKED = "a_reader_without_the_cost_grant_is_told_the_sell_price_alone"


@pytest.mark.needs_db
def test_the_ask_check_fails_when_the_rows_read_carry_the_cost_to_a_reader_without_its_grant(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A projection that selects every column whatever the reader holds. The redactor still
    withholds the cost from the answer, so only the rows show it, which is why the check reads
    them. Delete this and the check passes with the SELECT list carrying the cost one redaction bug
    away from a salesperson."""
    from brain.knowledge import classified_rows

    def everything(classification: Any, *, entitlement: Any, rows: Any, now: Any = None) -> Any:
        return () if rows is None else classification.columns()

    monkeypatch.setattr(classified_rows, "compile_projection", everything)

    assert refused(database, ASKED) == (
        FAILED,
        "the rows Ask read for a reader without the cost grant carried the cost or the margin",
    )


@pytest.mark.needs_db
def test_the_ask_check_fails_when_the_policy_forgets_the_margin_is_derived(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A classification compiled without its derivations, which is the defect fixed on
    2026-09-28: the projection still withholds the margin, so only the redactor handed the rows
    shows a reader with the margin grant and not the cost grant reading the margin. Delete this and
    the check passes with the redactor's closure never firing for an uploaded table."""
    from brain.core.field_policy import FieldRule
    from brain.knowledge.columns import ColumnRule

    def underived(self: ColumnRule, entity: str) -> FieldRule:
        return FieldRule(
            entity=entity,
            field=self.column,
            required_capability=self.required_capability,
            classification=self.classification,
        )

    monkeypatch.setattr(ColumnRule, "as_field_rule", underived)

    assert refused(database, ASKED) == (
        FAILED,
        "the redactor, handed rows holding the cost and the margin, did not narrow them to the "
        "sell price for a reader without the cost grant and leave them whole with it",
    )


@pytest.mark.needs_db
def test_the_ask_check_fails_when_a_withheld_cost_is_answered_unlike_an_absent_service(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An answer built from whatever survived redaction rather than from the field the question
    names: the reader is told something about a service whose cost they asked for, and nothing
    about one that does not exist. Delete this and the check passes with DENIED and ABSENT told
    apart on the frames a person receives."""
    from brain.gate import answer

    def everything(found: Any, payload: Any) -> str:
        return " ".join(str(value) for record in payload.records for value in record.values())

    monkeypatch.setattr(answer, "served_from", everything)

    assert refused(database, ASKED) == (
        FAILED,
        "a reader without the cost grant asking a service's cost or margin was not answered as "
        "for a service that does not exist",
    )


MARKED = "an_applied_mark_is_in_the_ledger_under_the_administrator"


@pytest.mark.needs_db
def test_the_mark_check_fails_when_a_mark_is_written_without_saying_who_wrote_it(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that writes without setting its writer: `0116`'s trigger still appends an entry,
    naming whoever the transaction last named, which is the run. Delete this and the check passes
    with every change to who may read the cost ledgered under the wrong person."""
    from brain.ops import classification_store

    async def unattributed(session: Any, writer: Any) -> None:
        return None

    monkeypatch.setattr(classification_store, "_attribute", unattributed)

    assert refused(database, MARKED) == (
        FAILED,
        "the upload and the applied mark did not reach the ledger once each, as 0116's entries "
        "under the administrator's name, reach and request",
    )


@pytest.mark.needs_db
def test_the_mark_check_fails_when_applying_a_mark_stores_the_classification_unchanged(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An apply that answers applied and writes the classification that stood. Delete this and
    the check passes on a Classification screen whose Apply button changes nothing."""
    from brain import classification_routes

    monkeypatch.setattr(classification_routes, "_in_place", lambda current, rule: current)

    assert refused(database, MARKED) == (
        FAILED,
        "an applied mark was not stored as the uploaded table's classification",
    )


# ------------------------------------------------ every other guard, each made to fire
UPLOADED = "a_price_list_upload_classifies_every_column"


def admitted_as(assurance_name: str) -> Callable[[pytest.MonkeyPatch], None]:
    """`admit` judging every session at one assurance, whatever the session was."""

    def breaks(monkeypatch: pytest.MonkeyPatch) -> None:
        from brain.gate import admission

        real = admission.admit
        fixed = admission.Assurance[assurance_name]
        monkeypatch.setattr(
            admission, "admit", lambda held, channel, assurance: real(held, channel, fixed)
        )

    return breaks


def kept_nowhere(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import classification_store

    monkeypatch.setattr(classification_store, "classified_tables_of", lambda state: None)


def refusing_every_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import classification_routes

    monkeypatch.setattr(classification_routes, "_upload_refusal", lambda entity: "refused")


def refusing_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import classification_routes

    monkeypatch.setattr(classification_routes, "_upload_refusal", lambda entity: "")


def reading_a_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import table_file

    monkeypatch.setattr(table_file, "CSV_SUFFIX", ".pdf")


def naming_no_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import columns

    monkeypatch.setattr(columns, "column_name_for", lambda heading: "no_such_column")


def dropping_the_last_row(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import table_file

    real = table_file._table

    def fewer(grid: Iterator[list[str]]) -> Any:
        parsed = real(grid)
        return replace(parsed, rows=parsed.rows[:-1])

    monkeypatch.setattr(table_file, "_table", fewer)


def reading_back_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops.classification_store import SqlClassifiedTables

    async def nothing(self: Any, entity: str) -> None:
        return None

    monkeypatch.setattr(SqlClassifiedTables, "table", nothing)


def classifying_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops.classification_store import SqlClassifiedTables

    async def nothing(self: Any, entity: str, classification: Any, *, writer: Any) -> None:
        return None

    monkeypatch.setattr(SqlClassifiedTables, "classify", nothing)


def loading_no_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import classification_routes

    def refused(stored: Any, column: str, mark: Any) -> Any:
        return classification_routes.ReviewView(
            entity=stored.entity, column=column, would_not_load="refused"
        )

    monkeypatch.setattr(classification_routes, "_mark_review", refused)


def nobody_live(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.identity.principal_store import StoredPrincipals

    async def nobody(self: Any, principal_id: str) -> None:
        return None

    monkeypatch.setattr(StoredPrincipals, "live_principal", nobody)


def an_empty_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge.classified_rows import ClassifiedLane
    from brain.ops import classification_store

    async def empty(state: Any) -> ClassifiedLane:
        return ClassifiedLane()

    monkeypatch.setattr(classification_store, "classified_lane_of", empty)


def fewer_rows_without_the_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import classified_rows

    real = classified_rows.read_table_rows

    async def fewer(table: Any, request: Any, *, entitlement: Any, **rest: Any) -> Any:
        result = await real(table, request, entitlement=entitlement, **rest)
        if any(grant.capability.value.endswith(".cost") for grant in entitlement.grants):
            return result
        return result.model_copy(update={"records": result.records[:-1]})

    monkeypatch.setattr(classified_rows, "read_table_rows", fewer)


def the_cost_for_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import classified_rows
    from brain.knowledge.rows import compile_projection as real

    def without(classification: Any, **given: Any) -> tuple[str, ...]:
        return tuple(column for column in real(classification, **given) if column != "cost")

    monkeypatch.setattr(classified_rows, "compile_projection", without)


def answering(withheld_only: bool) -> Callable[[pytest.MonkeyPatch], None]:
    """A lane that answers nothing, or nothing about the cost and the margin."""

    def breaks(monkeypatch: pytest.MonkeyPatch) -> None:
        from brain.gate import answer

        real = answer.served_from

        def sentence(found: Any, payload: Any) -> str:
            if withheld_only and found.field not in tables.WITHHELD:
                return real(found, payload)
            return ""

        monkeypatch.setattr(answer, "served_from", sentence)

    return breaks


def the_same_words_refused_for_two_places(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fast lane as it was until 2026-09-29: the same words for two places are two rules."""
    monkeypatch.setattr("brain.gate.fast_lane.asked_of_several_places", lambda found: False)


def a_scope_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Classification routes as they were until 2026-09-29: the grants held anywhere at all."""
    monkeypatch.setattr("brain.classification_routes.table_within_reach", lambda *given: True)


def a_read_needing_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Classification read as it was until 2026-09-29: the read grant held anywhere at all."""
    monkeypatch.setattr("brain.classification_routes.TO_READ", ())


def attributing_the_upload_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A store that sets its writer on an upload and not on a classification, so the apply's entry
    is written under whatever the upload left standing. See
    `AN_APPLIED_MARK_IS_ATTRIBUTED_BY_ITS_OWN_REQUEST`."""
    from brain.ops import classification_store

    real = classification_store._attribute

    async def upload_only(session: Any, writer: Any) -> None:
        if not writer.trace_id.endswith(tables.MARK_TRACE):
            await real(session, writer)

    monkeypatch.setattr(classification_store, "_attribute", upload_only)


def exposing_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import classification_routes

    monkeypatch.setattr(classification_routes, "newly_reachable", lambda current, proposed: ())


def marking_any_column(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import classification_routes

    monkeypatch.setattr(
        classification_routes,
        "_mark_review",
        lambda stored, column, mark: classification_routes.review_against(
            stored.classification, column, mark
        ),
    )


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("name", "reason", "breaks"),
    [
        pytest.param(
            UPLOADED,
            "an administrator holding both classification grants, signed in with a second factor, "
            "was refused a change to a classified table",
            admitted_as("AUTHENTICATED"),
            id="an-administrator-with-a-second-factor-is-refused",
        ),
        pytest.param(
            UPLOADED,
            "a person without the write grant, or signed in without a second factor, may change a "
            "classified table",
            admitted_as("STRONG"),
            id="a-password-only-session-keeps-the-admin-verb",
        ),
        pytest.param(
            UPLOADED,
            "this install's application keeps uploaded tables nowhere",
            kept_nowhere,
            id="the-application-keeps-uploaded-tables-nowhere",
        ),
        pytest.param(
            MARKED,
            "a table name made for this run was refused as a table's name",
            refusing_every_name,
            id="a-table-name-made-for-the-run-is-refused",
        ),
        pytest.param(
            UPLOADED,
            "a table named as the price list the product ships with was taken",
            refusing_no_name,
            id="the-shipped-price-list-s-name-is-taken",
        ),
        pytest.param(
            UPLOADED,
            "a file that is neither a CSV nor an XLSX was read as a table",
            reading_a_pdf,
            id="a-pdf-is-read-as-a-table",
        ),
        pytest.param(
            UPLOADED,
            "a well-formed price list, uploaded as a CSV or an XLSX, was refused as the upload "
            "route refuses one",
            naming_no_heading,
            id="the-key-heading-names-no-column-of-the-file",
        ),
        pytest.param(
            UPLOADED,
            "an uploaded price list's rows were not held as the file had them",
            dropping_the_last_row,
            id="a-row-of-the-file-is-not-held",
        ),
        pytest.param(
            MARKED,
            "a table uploaded a moment before was not there to be marked",
            reading_back_nothing,
            id="an-uploaded-table-is-not-read-back",
        ),
        pytest.param(
            MARKED,
            "a table uploaded a moment before was not there to be marked",
            classifying_nothing,
            id="an-applied-mark-finds-no-table-to-write",
        ),
        pytest.param(
            ASKED,
            "an uploaded price list's department column could not be opened",
            loading_no_mark,
            id="no-mark-loads",
        ),
        pytest.param(
            ASKED,
            "a reserved person was not live in the directory",
            nobody_live,
            id="a-reserved-person-is-not-live",
        ),
        pytest.param(
            ASKED,
            "Ask's lane did not carry the price list uploaded a moment before",
            an_empty_lane,
            id="ask-s-lane-carries-no-uploaded-table",
        ),
        pytest.param(
            ASKED,
            "readers of one price list were read different numbers of its rows, which counts what "
            "one of them was refused",
            fewer_rows_without_the_cost,
            id="a-reader-short-of-the-cost-grant-is-read-fewer-rows",
        ),
        pytest.param(
            ASKED,
            "the rows Ask read for a reader holding both grants left one out",
            the_cost_for_nobody,
            id="nobody-is-read-the-cost",
        ),
        pytest.param(
            ASKED,
            "a reader holding two price lists asked in the same words was not answered each "
            "list's sell price from its own list",
            answering(withheld_only=False),
            id="nobody-is-answered-anything",
        ),
        pytest.param(
            ASKED,
            "a reader holding two price lists asked in the same words was not answered each "
            "list's sell price from its own list",
            the_same_words_refused_for_two_places,
            id="two-lists-asked-in-the-same-words-answer-nobody",
        ),
        pytest.param(
            MARKED,
            "an administrator of one department could read or change another department's price "
            "list, or was refused it in other words than a price list that does not exist",
            a_scope_never_read,
            id="a-department-administrator-changes-another-department-s-table",
        ),
        pytest.param(
            MARKED,
            "an administrator of one department could read or change another department's price "
            "list, or was refused it in other words than a price list that does not exist",
            a_read_needing_nothing,
            id="a-department-administrator-reads-another-department-s-table",
        ),
        pytest.param(
            ASKED,
            "a reader holding the cost and margin grants was not answered a service's sell price, "
            "cost and margin",
            answering(withheld_only=True),
            id="nobody-is-answered-the-cost-or-the-margin",
        ),
        pytest.param(
            MARKED,
            "the upload and the applied mark did not reach the ledger once each, as 0116's entries "
            "under the administrator's name, reach and request",
            attributing_the_upload_alone,
            id="a-mark-is-ledgered-under-the-upload-s-attribution",
        ),
        pytest.param(
            MARKED,
            "the review of a mark dropping the margin's derivation did not name the cost as newly "
            "reachable",
            exposing_nothing,
            id="the-review-names-nothing-newly-reachable",
        ),
        pytest.param(
            MARKED,
            "a mark on a column the table does not carry, or a derived mark naming no input, was "
            "applied",
            marking_any_column,
            id="a-mark-on-a-column-the-table-does-not-carry-is-applied",
        ),
    ],
)
def test_every_other_guard_fails_its_check_with_its_own_sentence(
    database: str,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    reason: str,
    breaks: Callable[[pytest.MonkeyPatch], None],
) -> None:
    """Each guard the checks hold, broken in the product function it reads and nowhere else, fails
    its check with its own sentence. The guard audit mutates every `if` in the module and each of
    these is one it found no test made fire. Delete this and a check can stop noticing the
    administrator refused, a row lost, the lane empty or the review silent, and still read green on
    the Install page."""
    breaks(monkeypatch)

    assert refused(database, name) == (FAILED, reason)


def test_the_tables_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_tables") == [
        "a_price_list_upload_classifies_every_column",
        "a_reader_without_the_cost_grant_is_told_the_sell_price_alone",
        "an_applied_mark_is_in_the_ledger_under_the_administrator",
    ]
