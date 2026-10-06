"""The department rules install check: registered, passing on PostgreSQL, and able to fail.

The pure half holds the check to the leaf it proves, to the work breakdown and to the suite's list
of tables. The database half builds PostgreSQL to head once for the module and runs the check as
the worker would: it passes, and every table it writes to holds, row for row, what it held
before. Then each property it proves is broken, one at a time, by replacing the product function
the check relies on where the product looks it up, and the check fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.5.1
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head, checks_in
from tests.unit.test_acceptance_speed import run_checks

MODULE = "brain.ops.acceptance_checks_dept_rules"
NAME = "a_departments_rule_answers_its_own_from_the_next_question"

#: Every table the check writes to, which must hold afterwards exactly what it held before.
WRITTEN_BY_RULE_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "know.classified_table",
    "know.classified_row",
    "gate.fast_path_rule",
    "obs.request_telemetry",
    "mem.persistent",
    "mem.adaptive",
    "mem.learning",
)


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


# ------------------------------------------------------------------------ without a server
def test_the_department_rule_check_proves_its_leaf_and_nothing_else() -> None:
    """The check names M6.5.1 alone and the module is in the suite. Delete this and the check can
    close a leaf it does not exercise, or fall out of the run with nothing saying so."""
    assert {check.name: check.leaves for check in mine()} == {NAME: ("M6.5.1",)}
    assert MODULE in check_modules()
    assert checks_in(MODULE) == [NAME]


def test_the_leaf_the_department_rule_check_names_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Delete this and a
    result can close the wrong leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_department_rule_check_writes_is_one_the_suite_measures() -> None:
    """Delete this and a table the check writes can be left out of the suite's count, so a check
    that committed a department's rule to a client's install would pass the suite."""
    assert set(WRITTEN_BY_RULE_CHECKS) <= set(WRITTEN_BY_CHECKS)


def test_each_failure_sentence_is_distinct_so_a_failure_names_the_property() -> None:
    """The breaks below are told apart by sentence alone. Delete this and two properties can share
    one sentence, and a failure on the Install page no longer says which one broke."""
    from brain.ops import acceptance_checks_dept_rules as module

    sentences = [
        module.RULE_DID_NOT_ANSWER,
        module.ANSWERED_BEFORE_IT_WAS_ADDED,
        module.TEST_DID_NOT_ANSWER,
        module.ANSWERED_ANOTHER_DEPARTMENT,
        module.SEEN_BY_ANOTHER_DEPARTMENT,
        module.CHANGED_BY_ANOTHER_DEPARTMENT,
        module.STILL_ANSWERS_AFTER_RETIREMENT,
    ]
    assert len(set(sentences)) == len(sentences)


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every run rolls back, so they can share it."""
    with at_head("brain_acceptance_dept_rules") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the check writes to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_RULE_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


def outcome(database: str) -> tuple[str, str]:
    return run_checks(database, mine())[NAME]


@pytest.mark.needs_db
def test_on_a_real_database_the_department_rule_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes with no reason,
    and the rule table, the request ledger and every other table it wrote to hold row for row
    what they held before. Delete this and a check that cannot pass on the real schema, or one
    that leaves a department's rule on a client's install, reaches the owner's server first, and
    every break below is satisfied by a check that always fails."""
    before = contents(database)
    assert outcome(database) == (PASSED, "")
    assert contents(database) == before


@pytest.mark.needs_db
def test_the_check_fails_when_the_answer_route_reads_no_rule_as_it_is_asked(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule read at start, or never, is a rule that waits for a restart. Delete this and the
    check can pass on an install whose answer route never reads a rule an administrator added."""
    from brain import api_routes

    async def none(state: Any, department: str | None) -> tuple[()]:
        del state, department
        return ()

    monkeypatch.setattr(api_routes, "rules_for_asker", none)

    assert outcome(database) == (FAILED, _sentence("RULE_DID_NOT_ANSWER"))


@pytest.mark.needs_db
def test_the_check_fails_when_a_departments_rule_is_matched_for_every_asker(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The department filter is the whole of the rule's scope. Delete this and the check can pass
    on an install where a rule acceptance_a wrote answers acceptance_b's people."""
    from sqlalchemy import select

    from brain.gate import rule_store
    from brain.tables.fast_lane import FastPathRuleRow

    def everybodys(department: str | None) -> Any:
        del department
        return (
            select(FastPathRuleRow)
            .where(FastPathRuleRow.deleted_at.is_(None))
            .order_by(FastPathRuleRow.rule_id)
        )

    monkeypatch.setattr(rule_store, "live_rules", everybodys)

    assert outcome(database) == (FAILED, _sentence("ANSWERED_ANOTHER_DEPARTMENT"))


@pytest.mark.needs_db
def test_the_check_fails_when_a_retired_rule_is_still_read(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loader that ignores `deleted_at` answers with the rule somebody retired. Delete this and
    the check can pass on an install where retiring a rule changes nothing."""
    from sqlalchemy import or_, select

    from brain.gate import rule_store
    from brain.tables.fast_lane import FastPathRuleRow

    def retired_too(department: str | None) -> Any:
        return (
            select(FastPathRuleRow)
            .where(
                or_(
                    FastPathRuleRow.department.is_(None),
                    FastPathRuleRow.department == department,
                )
            )
            .order_by(FastPathRuleRow.rule_id)
        )

    monkeypatch.setattr(rule_store, "live_rules", retired_too)

    assert outcome(database) == (FAILED, _sentence("STILL_ANSWERS_AFTER_RETIREMENT"))


@pytest.mark.needs_db
def test_the_check_fails_when_a_retirement_writes_nothing(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retirement that reports success and leaves the rule live is the worst of both. Delete
    this and the check can pass on an install whose Retire button only says it worked."""
    from brain.gate.rule_store import StoredRules

    async def said_so(self: StoredRules, rule_id: str, *, writer: Any) -> bool:
        del self, rule_id, writer
        return True

    monkeypatch.setattr(StoredRules, "retire", said_so)

    assert outcome(database) == (FAILED, _sentence("STILL_ANSWERS_AFTER_RETIREMENT"))


@pytest.mark.needs_db
def test_the_check_fails_when_any_reader_is_shown_every_department_s_rules(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install whose Rules page lists acceptance_a's
    rules to acceptance_b's administrator."""
    from brain import rule_routes

    monkeypatch.setattr(rule_routes, "may_read_at", lambda *_: True)

    assert outcome(database) == (FAILED, _sentence("SEEN_BY_ANOTHER_DEPARTMENT"))


@pytest.mark.needs_db
def test_the_check_fails_when_any_administrator_may_write_any_department_s_rules(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install where acceptance_b's administrator tests,
    adds and retires acceptance_a's rules."""
    from brain import rule_routes

    monkeypatch.setattr(rule_routes, "may_write_at", lambda *_: True)

    assert outcome(database) == (FAILED, _sentence("CHANGED_BY_ANOTHER_DEPARTMENT"))


@pytest.mark.needs_db
def test_the_check_fails_when_a_test_does_not_say_what_the_rule_would_answer(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test is how an administrator learns a rule is right before it is live. Delete this and
    the check can pass on an install whose Test button answers nothing."""
    from brain import rule_routes

    monkeypatch.setattr(rule_routes, "served_from", lambda *_: "")

    assert outcome(database) == (FAILED, _sentence("TEST_DID_NOT_ANSWER"))


def _sentence(name: str) -> str:
    from brain.ops import acceptance_checks_dept_rules as module

    return str(getattr(module, name))
