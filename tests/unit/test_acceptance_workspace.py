"""An agent page's install acceptance checks: registered, passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, and to the rule that a
reason is a literal sentence short enough to be stored whole. The database half builds PostgreSQL to
head once and runs the checks as the worker would: each passes with no reason and every table in the
database holds afterwards what it held before. Then each check is run against a product broken in
the one place its sentence depends on, and fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.1.1.2, M39.1.1.4, M39.1.1.5, M39.1.3.1, M39.1.3.2, M39.1.3.3, M39.1.3.4
Task ids: M39.2.1.4, M39.2.2.1, M39.2.2.2, M39.2.2.3, M39.2.2.4, M39.2.2.5
Task ids: M39.2.3.1, M39.2.3.2, M39.2.3.3, M39.2.3.4, M39.3.1.1, M39.3.1.2, M39.3.1.3, M39.3.1.4
Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.4, M39.4.1.5, M39.4.2.1, M39.4.2.2, M39.4.2.4
Task ids: M39.6.1.1, M39.6.1.2, M39.6.1.3, M39.6.1.4, M39.6.1.5, M39.6.2.1, M39.6.2.2, M39.6.2.4
Task ids: M39.5.1.1, M39.5.1.2, M39.5.1.4, M39.5.1.5, M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4
Task ids: M39.5.2.5, M39.8.4, M39.8.5
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_workspace as workspace_checks
from brain.ops.acceptance import CHECK_MODULES, FAILED, PASSED, REASON_CHARS, Check, registered
from brain.ops.artifact_store import ARTIFACT_BUCKET
from brain.ops.object_store import S3Backend, StoreCredential
from brain.ops.storage import Backend, config_for
from tests.fixtures.fake_s3 import FakeS3
from tests.unit.test_acceptance import at_head
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]

#: The module under test, by the name `CHECK_MODULES` carries it under.
MODULE = "brain.ops.acceptance_workspace"

#: Each check and the leaves it proves.
LEAVES = {
    "an_agent_pins_its_parts_and_its_diff_shows_local_changes": (
        "M39.1.1.2",
        "M39.1.1.4",
        "M39.1.1.5",
    ),
    "an_agents_figures_follow_the_period_and_project_to_its_budget": (
        "M39.1.3.1",
        "M39.1.3.2",
        "M39.1.3.3",
        "M39.1.3.4",
    ),
    "an_agents_connector_is_attached_or_requested_by_its_ceiling": ("M39.2.1.4",),
    "an_agents_skills_are_chips_and_offers_from_the_library": (
        "M39.2.2.1",
        "M39.2.2.2",
        "M39.2.2.3",
        "M39.2.2.4",
        "M39.2.2.5",
    ),
    "an_agents_knowledge_is_a_predicate_over_the_readers_documents": (
        "M39.2.3.1",
        "M39.2.3.2",
        "M39.2.3.3",
        "M39.2.3.4",
    ),
    "an_agent_is_found_by_its_audience_and_previewed_as_a_person": (
        "M39.3.1.1",
        "M39.3.1.2",
        "M39.3.1.3",
        "M39.3.1.4",
    ),
    "an_agents_memory_is_text_its_owner_corrects_and_its_tiers_route": (
        "M39.4.1.1",
        "M39.4.1.2",
        "M39.4.1.3",
        "M39.4.1.4",
        "M39.4.1.5",
        "M39.4.2.1",
        "M39.4.2.2",
        "M39.4.2.4",
    ),
    "an_agents_automation_is_installed_started_run_and_removed": (
        "M39.6.1.1",
        "M39.6.1.2",
        "M39.6.1.3",
        "M39.6.1.4",
        "M39.6.1.5",
        "M39.6.2.1",
        "M39.6.2.2",
        "M39.6.2.4",
    ),
    "an_agents_report_holds_what_its_reader_may_see_and_is_rechecked": (
        "M39.5.1.1",
        "M39.5.1.2",
        "M39.5.1.4",
        "M39.5.1.5",
        "M39.5.2.1",
        "M39.5.2.2",
        "M39.5.2.3",
        "M39.5.2.4",
        "M39.5.2.5",
        "M39.8.4",
        "M39.8.5",
    ),
}

#: The artifact check's object store in the database half: the real S3 client over a fake bucket,
#: because these tests run with no vault and the product builds its store from the vault.
ARTIFACT_KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test")


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_workspace_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks in the order the page lists them, each with its leaves, and
    the suite runs it. Delete this and a check can fall out of the module or out of the suite with
    the Install page simply listing one fewer row, or close a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in CHECK_MODULES


def test_every_leaf_the_workspace_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def _reasons() -> list[str]:
    """Every reason the module raises a verdict with, read from its source."""
    tree = ast.parse(Path(workspace_checks.__file__).read_text(encoding="utf-8"))
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        [argument] = node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            said.append(argument.value)
        else:
            pytest.fail(ast.unparse(node))
    return said


def test_every_reason_the_workspace_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal, never built from a value, and
    fits the column so the Install page shows the sentence the source wrote. Delete this and a
    reason can quote a row the check read, or be cut mid-word on the page."""
    said = _reasons()
    assert len(said) > 15
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_budget_authority_the_route_asks_for_is_the_one_a_budget_warning_reaches() -> None:
    """The route restates `brain.ops.budget_stop.BUDGET_AUTHORITY` rather than importing the
    stop's machinery. Delete this and the two drift, so an agent's budget is set by somebody the
    budget's own warning never reaches."""
    from brain.agent_workspace_routes import BUDGET_AUTHORITY
    from brain.ops.budget_stop import BUDGET_AUTHORITY as WARNED

    assert BUDGET_AUTHORITY == WARNED


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_workspace") as url:
        yield url


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    """The artifact check's store, over a fake bucket the test can look into afterwards."""
    fake = FakeS3(credential=ARTIFACT_KEY).holding(ARTIFACT_BUCKET, {})
    backend = S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url="http://objects.example.test:8333"),
        ARTIFACT_KEY,
        transport=fake.transport(),
    )
    monkeypatch.setattr(workspace_checks, "artifact_backend", lambda h: (backend, "brain"))
    return fake


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


@pytest.mark.needs_db
def test_on_a_real_database_every_workspace_check_passes_and_leaves_nothing_behind(
    head: str, bucket: FakeS3
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table in the database, the agent's rows, its requests, its costs, its budget
    versions and the ledger among them, holds afterwards exactly what it held before. Delete this
    and a check that cannot pass on the real schema, or one that commits an agent or a budget to a
    client's install, reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before
    assert bucket.buckets[ARTIFACT_BUCKET] == {}


# ------------------------------------------------------------------ each check can fail
@pytest.mark.needs_db
def test_an_install_that_forgets_what_was_changed_here_fails_the_composition_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the divergence read returning nothing, the persona changed on the install is not
    flagged, and the check says so. Delete this and the check could pass over an install whose
    local edits nobody is told about."""
    monkeypatch.setattr("brain.agent_routes.divergent_parts", lambda instance: frozenset())
    name = "an_agent_pins_its_parts_and_its_diff_shows_local_changes"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the divergence flag did not name exactly the changed persona",
    )


@pytest.mark.needs_db
def test_an_automation_counted_as_a_message_fails_the_figures_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every traffic class read as a person's, the automation's run is counted as a message,
    and the check says so. Delete this and the message figure could be the run figure renamed."""
    monkeypatch.setattr(
        "brain.console_stats_routes.PERSON_TRAFFIC",
        frozenset({"human_interactive", "human_async", "automation", "system"}),
    )
    name = "an_agents_figures_follow_the_period_and_project_to_its_budget"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "an automation's run was counted as a message, or a period missed one",
    )


@pytest.mark.needs_db
def test_a_budget_anybody_may_set_fails_the_figures_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the budget authority asked of nobody, a member may set the agent's budget, and the
    check says so. Delete this and the check could pass over an install where anybody who can open
    an agent can raise what it may spend."""
    monkeypatch.setattr("brain.agent_workspace_routes.within_reach", lambda *args: True)
    name = "an_agents_figures_follow_the_period_and_project_to_its_budget"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the budget authority did not decide who may set an agent's budget",
    )


@pytest.mark.needs_db
def test_a_source_told_to_everybody_fails_the_connector_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every source told to every reader, a person in the other department is shown the
    agent's connector, and the check says so. Delete this and the check could pass over an install
    whose capability block names sources to people who may not be told they exist."""
    monkeypatch.setattr(
        "brain.agent_capability_routes.sources_at", lambda registry, reach, now: ("local",)
    )
    name = "an_agents_connector_is_attached_or_requested_by_its_ceiling"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a reader who may not be told of a source was shown its row",
    )


@pytest.mark.needs_db
def test_an_unreviewed_skill_offered_to_attach_fails_the_skills_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every library skill offered to attach, the unreviewed one is offered too, and the
    check says so. Delete this and the check could pass over an install where a skill nobody
    reviewed is one press away from an agent."""
    from brain.console.agent_tabs import Control, SkillOffer, chip_for

    monkeypatch.setattr(
        "brain.agent_capability_routes.offer_for",
        lambda imported, reader, now=None: SkillOffer(
            chip=chip_for(imported), control=Control.ATTACH
        ),
    )
    name = "an_agents_skills_are_chips_and_offers_from_the_library"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "an unreviewed skill was offered without the address of its review",
    )


@pytest.mark.needs_db
def test_a_predicate_that_matches_everything_fails_the_knowledge_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the predicate ignored, a reader in the other department is counted their own
    document as the agent's, and the check says so. Delete this and the slice could be every
    document its reader can see."""
    monkeypatch.setattr("brain.console.agent_tabs.matching", lambda scope, items: tuple(items))
    name = "an_agents_knowledge_is_a_predicate_over_the_readers_documents"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a reader elsewhere was counted documents of the agent's department",
    )


@pytest.mark.needs_db
def test_a_preview_anybody_may_ask_for_fails_the_availability_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the preview's disclosure moved to the price list read, a person who may not read
    grants previews somebody's run, and the check says so. Delete this and the check could pass
    over an install where anybody can read what a colleague's run would reach."""
    from brain.core.entitlement import Capability

    # Both places the disclosure is asked: before anybody's grants are read, and in the preview.
    for where in ("brain.console.reach_view", "brain.agent_capability_routes"):
        monkeypatch.setattr(f"{where}.PREVIEW_DISCLOSURE", Capability(value="read:price_list"))
    name = "an_agent_is_found_by_its_audience_and_previewed_as_a_person"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a reader who may not read grants was given somebody's preview",
    )


@pytest.mark.needs_db
def test_a_memory_offered_to_every_reader_fails_the_memory_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the agent's memory read at a reach wider than the reader holds, a colleague is shown
    what the agent keeps about somebody else, and the check says so. Delete this and the check
    could pass over an install whose Memory section is the lens taken off."""
    import brain.agent_memory_routes as routes
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope

    def wide(reader: EntitlementSet, record: object) -> EntitlementSet:
        return EntitlementSet(
            principal_id=reader.principal_id,
            grants=(
                Grant(capability=Capability(value="read:price_list"), scope=Scope.unrestricted()),
            ),
        )

    monkeypatch.setattr(routes, "run_reach", wide)
    name = "an_agents_memory_is_text_its_owner_corrects_and_its_tiers_route"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a colleague was shown what the agent keeps about somebody else",
    )


@pytest.mark.needs_db
def test_an_automation_its_owner_may_start_fails_the_automation_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the second-person rule gone, the owner may start their own automation, and the check
    says so. Delete this and the check could pass over an install where whoever an automation
    runs as widens its unattended schedule alone."""
    monkeypatch.setattr(
        "brain.console.automation_schedule.may_change_schedule",
        lambda one, *, becomes, approved_by: True,
    )
    name = "an_agents_automation_is_installed_started_run_and_removed"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "an automation's owner could start it without a second person",
    )


@pytest.mark.needs_db
def test_an_install_with_no_object_store_fails_the_artifact_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no object store connected, the check says the install cannot keep an artifact rather
    than keeping one somewhere the product never looks. Delete this and the check could pass on an
    install whose Artifacts section can never hold anything."""
    monkeypatch.setattr(workspace_checks, "artifact_backend", lambda h: (None, ""))
    name = "an_agents_report_holds_what_its_reader_may_see_and_is_rechecked"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "this install is not connected to its object store",
    )


@pytest.mark.needs_db
def test_a_report_built_at_the_callers_own_reach_fails_the_artifact_check(
    head: str, bucket: FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the report's fields decided at a reach holding every column, the person without the
    cost is sent it, and the check says so. Delete this and the check could pass over a producer
    that writes the rows as read."""
    import brain.ops.artifact_report as report

    monkeypatch.setattr(
        report, "producible_fields", lambda entity, present, **kwargs: tuple(present)
    )
    name = "an_agents_report_holds_what_its_reader_may_see_and_is_rechecked"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "a report for a person without the cost held the cost or margin",
    )


@pytest.mark.needs_db
def test_a_download_that_trusts_its_own_person_fails_the_artifact_check(
    head: str, bucket: FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a re-download no longer checked against what the content drew on, the steward can
    fetch a report whose cost they may not read, and the check says so. Delete this and the check
    could pass over an install where holding the Artifacts screen is holding every file on it."""
    monkeypatch.setattr(
        "brain.console.agent_output.still_holds", lambda drew_on, requester, now: True
    )
    name = "an_agents_report_holds_what_its_reader_may_see_and_is_rechecked"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the steward could fetch a report whose cost they may not read",
    )
