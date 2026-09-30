"""The speed install acceptance checks: registered, passing on PostgreSQL, and able to fail.

The pure half holds the five checks to the leaves they prove and to the work breakdown, and the
tables they write to the suite's own list. The database half builds PostgreSQL to head once for the
module and runs the checks as the worker would: each passes, and every table they write to holds,
row for row, what it held before. Then the property each check proves is broken, one at a time, by
replacing the product function the check relies on where the product looks it up, and the check
fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.1.1, M6.1.2, M6.1.4, M6.1.6, M6.3.1, M6.3.2, M6.3.3, M6.3.4, M6.3.5, M6.4.2
Task ids: M6.4.3, M6.4.4, M6.1.3
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_speed"

#: Each speed check and the leaves it proves.
LEAVES = {
    "a_rule_row_answers_on_the_fast_lane_with_no_model": ("M6.1.1", "M6.1.2", "M6.1.4"),
    "the_fast_lane_share_counts_people_and_not_machines": ("M6.1.6",),
    "an_answer_streams_steps_then_citations_then_prose": (
        "M6.3.1",
        "M6.3.2",
        "M6.3.3",
        "M6.3.4",
        "M6.3.5",
    ),
    "every_prompt_opens_with_the_same_bytes_and_one_length": ("M6.4.2", "M6.4.3", "M6.4.4"),
    "the_fast_lane_reads_as_a_role_that_reaches_nothing_else": ("M6.1.3",),
}

#: Every table the speed checks write to, which must hold afterwards exactly what it held before.
WRITTEN_BY_SPEED_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "know.item",
    "know.chunk",
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


def one(name: str) -> Check:
    [found] = [check for check in mine() if check.name == name]
    return found


# ------------------------------------------------------------------------ without a server
def test_the_speed_checks_prove_the_speed_leaves_and_nothing_else() -> None:
    """Each check names the leaves it was scoped to, and the module is in the suite. Delete this
    and a check can close a leaf it does not exercise, or fall out of the run."""
    assert {check.name: check.leaves for check in mine()} == LEAVES
    assert MODULE in check_modules()


def test_every_leaf_the_speed_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Delete this and a
    result can close the wrong leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_speed_checks_write_is_one_the_suite_measures() -> None:
    """Delete this and a table these checks write can be left out of the suite's count, so a
    check that committed a rule row to a client's install would pass the suite."""
    assert set(WRITTEN_BY_SPEED_CHECKS) <= set(WRITTEN_BY_CHECKS)


def test_a_frame_is_decoded_as_a_browser_dispatches_it_and_a_malformed_one_fails() -> None:
    """The decoder the streaming check reads frames with: an event name and its data lines, and a
    frame a browser would drop is the check failing. Delete this and the check can read frames a
    browser never shows as though they arrived."""
    from brain.gate.answer import Answered
    from brain.gate.streaming import Event, encode
    from brain.ops.acceptance import CheckFailedError
    from brain.ops.acceptance_checks_speed import Frame, decoded

    frames = (encode(Event.STEP, "Reading"), encode(Event.TEXT, "one\n\ntwo"))
    assert decoded(Answered(frames=frames)) == [
        Frame(event="step", data="Reading"),
        Frame(event="text", data="one\n\ntwo"),
    ]
    with pytest.raises(CheckFailedError):
        decoded(Answered(frames=("data: no event\n\n",)))


def test_the_speed_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests so a package adding a check edits its own file and never a
    list every package appends to. Delete this and a check can drop out of the module with the
    page simply listing one fewer row."""
    assert checks_in(MODULE) == [
        "a_rule_row_answers_on_the_fast_lane_with_no_model",
        "the_fast_lane_share_counts_people_and_not_machines",
        "an_answer_streams_steps_then_citations_then_prose",
        "every_prompt_opens_with_the_same_bytes_and_one_length",
        "the_fast_lane_reads_as_a_role_that_reaches_nothing_else",
    ]


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


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every check rolls back, so they can share it."""
    with at_head("brain_acceptance_speed") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_SPEED_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_every_speed_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table any of them wrote to, the rule table and the request ledger among
    them, holds row for row what it held before. Delete this and a check that cannot pass on the
    real schema, or one that commits a rule row to a client's install, reaches the owner's server
    first."""
    before = contents(database)
    outcomes = run_checks(database, mine())
    after = contents(database)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------- each check can fail
def refused(database: str, name: str) -> tuple[str, str]:
    return run_checks(database, (one(name),))[name]


@pytest.mark.needs_db
def test_the_rule_check_fails_when_the_loader_reads_no_rule_rows(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule set that is code rather than rows is M6.1.1 undone. Delete this and the check can
    pass on an install whose rule table is read by nothing."""
    from brain.gate import rule_store

    def nothing(rows: object) -> tuple[()]:
        del rows
        return ()

    monkeypatch.setattr(rule_store, "rules_from_rows", nothing)

    assert refused(database, "a_rule_row_answers_on_the_fast_lane_with_no_model") == (
        FAILED,
        "a rule written as a row was not read by the install's loader",
    )


@pytest.mark.needs_db
def test_the_rule_check_fails_when_a_rule_matches_a_fragment_of_a_question(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A matcher reading a template anywhere in a question answers a question nobody wrote a rule
    for. Delete this and the check can pass on an install whose rules match fragments."""
    from brain.gate import fast_lane

    kept = fast_lane._tidy

    def tail_only(question: str) -> str:
        tidy = kept(question)
        return tidy.removeprefix("please tell me ")

    monkeypatch.setattr(fast_lane, "_tidy", tail_only)

    assert refused(database, "a_rule_row_answers_on_the_fast_lane_with_no_model") == (
        FAILED,
        "a rule answered words it was not written for",
    )


@pytest.mark.needs_db
def test_the_share_check_fails_when_a_programs_question_is_counted(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Machine traffic counted beside people's is M6.1.6 undone. Delete this and the check can
    pass on an install whose lane figures count programs."""
    from brain import operate_routes
    from brain.gate.context import TrafficClass

    monkeypatch.setattr(operate_routes, "HUMAN_TRAFFIC", frozenset(TrafficClass))

    assert refused(database, "the_fast_lane_share_counts_people_and_not_machines") == (
        FAILED,
        "the lane figures counted a program's question as a person's",
    )


@pytest.mark.needs_db
def test_the_streaming_check_fails_when_prose_arrives_before_its_citations(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install that cites after the prose, where nobody
    reads the citation."""
    from dataclasses import replace

    from brain import api_routes
    from brain.gate.answer import Answered
    from brain.gate.streaming import Event

    kept = api_routes.answered_for

    async def reordered(*args: Any, **kw: Any) -> Any:
        made = await kept(*args, **kw)
        if not isinstance(made, Answered):
            return made
        frames = list(made.frames)
        cited = [one for one in frames if one.startswith(f"event: {Event.CITATION.value}")]
        rest = [one for one in frames if one not in cited]
        done = rest.pop()
        return replace(made, frames=(*rest, *cited, done))

    monkeypatch.setattr(api_routes, "answered_for", reordered)

    assert refused(database, "an_answer_streams_steps_then_citations_then_prose") == (
        FAILED,
        "an answer's citations did not arrive before its prose",
    )


@pytest.mark.needs_db
def test_the_prompt_check_fails_when_a_person_reaches_the_shared_bytes(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt whose first bytes differ per person shares no provider cache and has carried that
    person into a region every caller shares. Delete this and the check can pass on an install
    whose prompts start with the asker."""
    from brain.gate import model_lane
    from brain.gate.prefix import build_prefix, lay_out

    kept = model_lane.prompt_for

    def personal(question: str, payload: Any, cards: Any = (), hints: Any = (), **kw: Any) -> Any:
        layout = kept(question, payload, cards, hints, **kw)
        own = build_prefix((), persona=model_lane.ANSWER_LANE_PERSONA + " " + question)
        return lay_out(own, *layout.variable)

    monkeypatch.setattr(model_lane, "prompt_for", personal)

    assert refused(database, "every_prompt_opens_with_the_same_bytes_and_one_length") == (
        FAILED,
        "two people's prompts did not open with the same bytes",
    )


@pytest.mark.needs_db
def test_the_role_check_fails_when_the_lane_does_not_mark_its_reads(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lane whose reads carry no mark is read as the application by every source. Delete this
    and the check can pass on an install whose fast lane reads everything the application can."""
    import contextlib

    from brain.gate import fast_lane

    monkeypatch.setattr(fast_lane, "read_as_the_fast_lane", contextlib.nullcontext)

    assert refused(database, "the_fast_lane_reads_as_a_role_that_reaches_nothing_else") == (
        FAILED,
        "the fast lane's reads were not marked as its own",
    )


@pytest.mark.needs_db
def test_the_role_check_fails_when_the_source_ignores_the_mark(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that runs a marked read as the application. Delete this and the check can pass on
    an install whose row source never takes the role, the lane's mark read by nothing."""
    from brain.knowledge import row_store

    monkeypatch.setattr(row_store, "is_a_fast_lane_read", lambda: False)

    assert refused(database, "the_fast_lane_reads_as_a_role_that_reaches_nothing_else") == (
        FAILED,
        "the fast lane's rows were read as the application",
    )
