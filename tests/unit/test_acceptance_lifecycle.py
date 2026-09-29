"""A stored document's install acceptance checks: registered, passing, and made to fail.

The pure half holds the four checks to the leaves they were scoped to, to `docs/wbs.json`, and to
the rule that a reason is a literal sentence short enough to be stored whole. The database half
builds PostgreSQL to head once and runs the checks as the worker would: every check passes with no
reason, and afterwards every table any of them wrote to, and every other table in the database,
holds what it held before, which is `brain.ops.acceptance.NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED`
measured for the knowledge lifecycle. Then each check is run against a product broken in the one
place its sentence depends on, and fails with its own sentence: a check that cannot fail proves
nothing on the owner's server.

One guard lives only in `0120`'s triggers, the closing of a review task by a new verification, so
its breakage is a replacement of that function inside the scratch database, put back afterwards;
every other breakage is a product attribute replaced where the check looks it up. The trigger's
refusal of a promotion approved by the person who asked is now the database's second wall behind
the Approvals screen, which never offers the asker their card, so the check cannot reach it and
`tests/unit/test_knowledge_lifecycle_db.py` presses it at the row instead.

Not broken here, and said rather than dropped: a capturer deciding their own solution. It is refused
three times, by `may_decide`, by `CapturedSolution`'s own rule and by `0120`'s policy and check
constraint, so breaking any one of them leaves the check green for a reason that is correct. The
mutation is equivalent at the check's level; `may_decide`'s refusal of the capturer is held by
`tests/unit/test_knowledge_lifecycle.py`.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from brain.ops import acceptance_checks_lifecycle as lifecycle
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, Check, registered
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]

#: The module under test, by the name `CHECK_MODULES` will carry it under.
MODULE = "brain.ops.acceptance_checks_lifecycle"

#: Each check and the leaf it proves, as the coordinator scoped them.
LEAVES = {
    "a_newer_version_supersedes_the_older_and_answers_use_the_newer": ("M7.4.5",),
    "a_company_wide_request_waits_until_another_approver_approves_it": ("M7.4.4",),
    "a_review_that_fell_due_opens_its_steward_s_task_until_verified": ("M7.4.6",),
    "a_solution_answers_only_once_somebody_else_approves_it": ("M7.6.2",),
}

#: Every table the lifecycle checks write to, which must hold afterwards what it held before.
WRITTEN_BY_LIFECYCLE_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "know.item",
    "know.chunk",
    "know.steward_task",
    "know.solution",
    "gate.suspension",
    "obs.audit_entry",
    "ops.outbox_event",
    "ops.outbox_delivery",
)


def _migration() -> Any:
    """`0120` as a module, read from its file, since a name opening with a digit is not imported."""
    path = ROOT / "migrations" / "versions" / "0120_knowledge_lifecycle.py"
    spec = importlib.util.spec_from_file_location("migration_0120", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_lifecycle_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares four checks, one per leaf, in the order the page lists them. Delete this
    and a check can fall out of the module with the Install page simply listing one fewer row, or
    close a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())


def test_every_leaf_the_lifecycle_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def _reasons() -> list[str]:
    """Every reason the module raises a verdict with, read from its source."""
    tree = ast.parse(Path(lifecycle.__file__).read_text(encoding="utf-8"))
    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        [argument] = node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            said.append(argument.value)
        elif isinstance(argument, ast.Name) and argument.id in constants:
            said.append(constants[argument.id])
        else:
            pytest.fail(ast.unparse(node))
    return said


def test_every_reason_the_lifecycle_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`, for this module before the registry names it: every reason is a
    string literal or a module constant, never built from a value, and fits the column so the
    Install page shows the sentence the source wrote. Delete this and a reason can quote a row the
    check read, or be cut mid-word on the page."""
    said = _reasons()
    assert len(said) > 30
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_figures_the_checks_rest_on_agree_with_the_product_they_check() -> None:
    """Each figure held against something outside the module: a review set `REVIEW_AHEAD` away is
    beyond the sweep's lead time, so the first run has nothing to ask; a verification recorded
    `VERIFIED_LONG_AGO` precedes the review date that `FELL_DUE`, which `verification_for` insists
    on; and the solution ledger's prefix is the one `0120`'s trigger writes. Delete this and a
    lead time lengthened past the figure makes the review check red on a working install, or a
    renamed subject makes the solution check look for entries under a name nothing writes."""
    from brain.knowledge.verification import DEFAULT_LEAD_TIME

    assert lifecycle.REVIEW_AHEAD > DEFAULT_LEAD_TIME
    assert lifecycle.VERIFIED_LONG_AGO > lifecycle.FELL_DUE > timedelta(0)
    migration = _migration()
    assert lifecycle.SOLUTION_SUBJECT_PREFIX == migration.SOLUTION_SUBJECT_PREFIX
    assert f"'{lifecycle.SOLUTION_SUBJECT_PREFIX}' || NEW.solution_id" in (
        migration.SOLUTION_AUDIT_FUNCTION
    )


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_lifecycle") as url:
        yield url


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

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def lifecycle_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_LIFECYCLE_CHECKS
    }


def every_count(url: str) -> dict[str, int]:
    """Every table in the database and its rows, so a write to a table nobody listed is seen too."""
    from tests.fixtures.scratch_postgres import sql

    named = sql(
        url,
        "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables"
        " WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1",
    )
    # The names are the catalogue's, quoted by format, never input.
    return {
        name: int(sql(url, f"SELECT count(*) FROM {name}")[0][0])  # noqa: S608
        for (name,) in named
    }


@pytest.mark.needs_db
def test_on_a_real_database_every_lifecycle_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table any of them wrote to, the documents, their passages, the tasks, the
    solutions, the cards, the nags and the ledger among them, holds afterwards exactly what it held
    before, and so does every other table. Delete this and a check that cannot pass on the real
    schema, or one that commits a document or a task to a client's install, reaches the owner's
    server first."""
    before = (counts(head), lifecycle_counts(head), every_count(head))
    outcomes = run_checks(head, mine())
    after = (counts(head), lifecycle_counts(head), every_count(head))

    assert set(WRITTEN_BY_LIFECYCLE_CHECKS) <= set(before[2])
    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------------ each check can fail
async def _writes_without_superseding(
    session: Any, predecessor: Any, successor: Any, *, blocks: Any, revision: Any, now: datetime
) -> Any:
    """`write_version` with `know.supersede_item` left out: the newer is written, nothing moves."""
    from brain.knowledge.chunk_store import reach_of, write_document

    del predecessor
    reach = await reach_of(session, successor.owner_id, now=now)
    assert reach is not None
    return await write_document(session, successor, reach=reach, revision=revision, blocks=blocks)


@pytest.mark.needs_db
def test_a_newer_version_that_supersedes_nothing_fails_the_supersession_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the supersession left out of the product's write, the newer version is stored beside
    the older and both answer, and the check says the older was not shown superseded. Delete this
    and the check could pass over an install whose new versions replace nothing."""
    monkeypatch.setattr(
        "brain.knowledge.lifecycle_store.write_version", _writes_without_superseding
    )
    name = "a_newer_version_supersedes_the_older_and_answers_use_the_newer"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the older version was not shown superseded by the newer one",
    )


@pytest.mark.needs_db
def test_a_reader_who_may_replace_any_document_fails_the_supersession_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every reader allowed to act on every document they can read, a plain member replaces
    the steward's document, and the check says so. Delete this and the check could pass over an
    install where anybody who reads a document may rewrite what everybody is answered from."""
    monkeypatch.setattr("brain.knowledge.lifecycle.Authority.may_act", lambda self, item: True)
    name = "a_newer_version_supersedes_the_older_and_answers_use_the_newer"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "somebody who neither stewards nor administers it replaced it",
    )


@pytest.mark.needs_db
def test_an_unverified_document_put_to_the_approvals_screen_fails_the_promotion_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the refusal of an unverified document gone, a document nobody vouched for waits on the
    Approvals screen, and the check says so. Delete this and the check could pass over an install
    that asks the company to read text nobody has verified."""
    monkeypatch.setattr("brain.knowledge.lifecycle.assert_may_propose", lambda item: None)
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a document nobody had verified was put to the Approvals screen",
    )


@pytest.mark.needs_db
def test_a_card_offered_outside_its_department_fails_the_promotion_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the Approvals screen offering every card to everybody, a holder of the approval in
    another department is offered the steward's card, and the check says so. Delete this and the
    check could pass over an install whose promotions are decided by whoever holds the word."""
    monkeypatch.setattr(
        "brain.console.approvals.pending_for",
        lambda entitlement, suspensions, now: tuple(suspensions),
    )
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the card was offered to somebody who may not approve it",
    )


def _shipped(name: str) -> str:
    """One of `0120`'s functions as the migration that ships it writes it, to replace in place."""
    return str(getattr(_migration(), name)).replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    )


def _outcome_with(url: str, shipped: str, broken: str, name: str) -> tuple[str, str]:
    """One check's outcome with a database function replaced, put back whatever happened."""
    from tests.fixtures.scratch_postgres import sql

    assert broken != shipped
    sql(url, broken)
    try:
        return run_checks(url, (by_name(name),))[name]
    finally:
        sql(url, shipped)


@pytest.mark.needs_db
def test_a_card_offered_to_its_own_asker_fails_the_promotion_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the Approvals screen's rule that nobody is offered their own promotion taken out, the
    steward, who holds the approval where the document sits, is offered their own card, and the
    check says so. Delete this and the screen can go back to offering a button that only the
    database refuses, which the route answers as a fault, with the check green."""
    monkeypatch.setattr("brain.console.role_surfaces.asked_by", lambda suspension, pid: False)
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the person who asked was offered their own card to approve",
    )


@pytest.mark.needs_db
def test_an_approval_the_database_refuses_fails_the_promotion_check_as_a_fault(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the decision refused by the database, as `0120`'s trigger refuses a self-approval by
    raising, the check fails saying the route answered a fault, rather than counting the raise as
    a refusal. That was the check's reading until 2026-09-29, and it passed an install whose
    Approvals route answered the asker's own approval with a 500. Delete this and it can again."""
    from sqlalchemy.exc import IntegrityError

    async def refused_by_the_database(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("UPDATE gate.suspension", {}, Exception("check_violation"))

    monkeypatch.setattr("brain.approval_routes.decide_once", refused_by_the_database)
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        lifecycle.THE_DATABASE_REFUSED_AN_APPROVAL_THE_SCREEN_OFFERED,
    )


@pytest.mark.needs_db
def test_a_moved_document_s_refusal_answered_as_a_fault_fails_the_promotion_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The route as it was until 2026-09-29.** With the store no longer recognising `0120`'s
    refusal of a moved document, approving the card whose document gained a newer version is a
    fault on the route, and the check says so. Delete this and the check can pass an install whose
    Approvals screen answers such a card with a 500, which is what the owner's did."""
    monkeypatch.setattr("brain.gate.suspension_store.refused_because_it_moved", lambda exc: False)
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        lifecycle.THE_DATABASE_REFUSED_AN_APPROVAL_THE_SCREEN_OFFERED,
    )


@pytest.mark.needs_db
def test_a_moved_document_s_card_left_open_fails_the_promotion_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the refused approval answered and the card never closed, it stays waiting for the next
    approver to fail on, and the check says so. Delete this and the check passes a screen that
    tells one approver the request no longer applies and offers it to everybody else again."""

    async def left_open(*args: Any, **kwargs: Any) -> Any:
        return None

    monkeypatch.setattr("brain.approval_routes.close_as_no_longer_applying", left_open)
    name = "a_company_wide_request_waits_until_another_approver_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "approving a card whose document had a newer version since it was asked for was not "
        "answered that the request no longer applies and closed as rejected",
    )


@pytest.mark.needs_db
def test_a_nag_routed_away_from_the_steward_fails_the_re_verification_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every due document's nag sent to its department, the worker's run opens no task on the
    steward's list, and the check says so. Delete this and the check could pass over an install
    whose sweep records nags nobody is ever shown, which is what the owner saw."""
    from brain.knowledge.item_store import Route

    monkeypatch.setattr(
        "brain.knowledge.item_store.route_for", lambda item, owner_reach: Route.DEPARTMENT
    )
    name = "a_review_that_fell_due_opens_its_steward_s_task_until_verified"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the re-verification run opened no task for the steward of a document past its review date",
    )


@pytest.mark.needs_db
def test_a_review_task_verifying_does_not_close_fails_the_re_verification_check(head: str) -> None:
    """With the trigger that closes a review task on a new verification made to close nothing, in
    the scratch database and put back afterwards, the steward's task outlives the verification and
    the check says so. Delete this and the half of the sentence that lives only in the database,
    verifying closes it, is the half no check was ever seen to catch."""
    shipped = _shipped("STEWARDSHIP_FUNCTION")
    closing = "WHERE item_id = NEW.item_id AND kind = 'reverify' AND done_at IS NULL"
    assert shipped.count(closing) == 1
    broken = shipped.replace(closing, "WHERE false")
    name = "a_review_that_fell_due_opens_its_steward_s_task_until_verified"

    assert _outcome_with(head, shipped, broken, name) == (
        FAILED,
        "verifying the document again did not close its review task",
    )


@pytest.mark.needs_db
def test_the_re_verification_check_is_not_run_on_a_login_that_cannot_run_the_control(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`THE_SWEEP_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN`: a login that cannot read past a policy,
    which is the run started by hand in the application container, says not run in its own words
    before anything is written. Delete this and that run reports the sweep as broken, or proves a
    sweep that ran as the application role, which is not the worker's."""
    monkeypatch.setattr("brain.session.LOGIN_BYPASSES_ROW_SECURITY", text("SELECT false"))
    name = "a_review_that_fell_due_opens_its_steward_s_task_until_verified"
    before = lifecycle_counts(head)

    outcome = run_checks(head, (by_name(name),))[name]

    assert outcome == (
        NOT_RUN,
        "this login cannot run the worker's re-verification control, so it was not asked; the "
        "worker's own run asks it",
    )
    assert lifecycle_counts(head) == before


@pytest.mark.needs_db
def test_a_solution_that_answers_before_approval_fails_the_solution_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a capture that also publishes the solution as its capturer's document, a question is
    answered from it while it waits, and the check says so. Delete this and the check could pass
    over an install where capturing is publishing."""
    from brain.knowledge import lifecycle_store
    from brain.knowledge.item import KnowledgeItem, KnowledgeState
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.solutions import solution_text
    from brain.knowledge.visibility import KnowledgeVisibility

    captured = lifecycle_store.put_solution

    async def published_on_capture(session: Any, solution: Any) -> None:
        await captured(session, solution)
        item = KnowledgeItem(
            item_id=solution.item_id,
            content=solution_text(solution),
            title=solution.title,
            visibility=KnowledgeVisibility.of_department(
                solution.department, owner_id=solution.captured_by
            ),
            owner_id=solution.captured_by,
            state=KnowledgeState.PUBLISHED,
            kind=KnowledgeKind.APPROVED_SOLUTION,
        )
        await lifecycle_store.write_solution_document(
            session, item, revision=None, now=solution.captured_at
        )

    monkeypatch.setattr(lifecycle_store, "put_solution", published_on_capture)
    name = "a_solution_answers_only_once_somebody_else_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a captured solution answered a question before anybody approved it",
    )


@pytest.mark.needs_db
def test_an_approved_solution_nobody_verified_fails_the_solution_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With approval writing the document unverified, the solution answers but not as vouched for
    by the person who approved it, and the check says so. Delete this and the check could pass
    over an install whose approved solutions carry no verification."""
    from brain.knowledge import solutions

    approved = solutions.approved_item

    def unverified(solution: Any, *, by: Any, review_by: datetime, now: datetime) -> Any:
        item = approved(solution, by=by, review_by=review_by, now=now)
        return item.model_copy(update={"verified_by": "", "verified_at": None})

    monkeypatch.setattr(solutions, "approved_item", unverified)
    name = "a_solution_answers_only_once_somebody_else_approves_it"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "an approved solution did not answer as verified by the person who approved it",
    )
