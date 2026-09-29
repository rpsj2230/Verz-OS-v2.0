"""The install acceptance checks: the registry, the verdict's words, the safety rules, a real run.

The pure half holds what a check may say and what the run may touch: every leaf a check names is a
leaf, every reason a check raises is a literal sentence, an exception's message never reaches a
result, a run is owed once per commit or on request, and the reserved names are names the product
accepts. The database half builds a PostgreSQL to head and runs the suite against it as the worker
would, then reads the tables back: the checks that can run pass, the result rows are written, and
nothing else a check wrote is left, which is `NOTHING_A_CHECK_WRITES_IS_EVER_COMMITTED` measured.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.core.department import SLUG_PATTERN
from brain.ops import acceptance, acceptance_audit, acceptance_run
from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    RESERVED_DEPARTMENTS,
    RESERVED_PRINCIPAL_PREFIX,
    AcceptanceError,
    Check,
    CheckFailedError,
    CheckNotRunError,
    Occasion,
    Result,
    owed,
    reason_for,
    registered,
    served,
)
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_limit_store import FakeClient

ROOT = Path(__file__).resolve().parents[2]
#: Every module a check or the harness raises a verdict from: the harness, and each module named in
#: `CHECK_MODULES`, so a new check module is held to the literal-reason rule the day it is named.
SOURCES = (
    ROOT / "src" / "brain" / "ops" / "acceptance_run.py",
    *(ROOT / "src" / f"{module.replace('.', '/')}.py" for module in acceptance.CHECK_MODULES),
)

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


async def _nothing(harness: Harness) -> None:
    del harness


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every run of the suite here imports from a GitHub that does not answer, so no test in this
    file reaches the network; `tests/unit/test_acceptance_skills.py` fakes one that does."""
    from brain.ops import acceptance_checks_skills
    from tests.unit.test_acceptance_skills import unreachable

    monkeypatch.setattr(acceptance_checks_skills, "_transport", unreachable)


# ------------------------------------------------------------------------ the registry
def test_a_check_proving_no_leaf_or_an_unknown_shape_of_leaf_is_refused() -> None:
    """A result that closes nothing, or names something that is not a leaf id, cannot be declared.
    Delete this and a check can be registered whose result no task can be closed from."""
    for leaves in ((), ("M23",), ("M23.1.1", "M23.1.1"), ("banana",)):
        with pytest.raises(AcceptanceError):
            Check(name="some_check", leaves=leaves, sentence="Said.", run=_nothing)
    with pytest.raises(AcceptanceError):
        Check(name="Bad Name", leaves=("M23.1.1",), sentence="Said.", run=_nothing)
    with pytest.raises(AcceptanceError):
        Check(name="some_check", leaves=("M23.1.1",), sentence=" ", run=_nothing)
    assert Check(name="some_check", leaves=("M23.1.1",), sentence="Said.", run=_nothing).leaves


def test_every_leaf_a_check_names_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so a leaf id that moved or never existed reads as a correct claim.
    Held against `docs/wbs.json`, which is outside the registry. Delete this and a result can be
    recorded against an id no task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    checks = registered()
    assert checks
    for one in checks:
        assert set(one.leaves) <= leaves, one.name


def test_each_module_of_the_suite_declares_its_checks_in_order() -> None:
    """Held per module, so a package adding checks in a module of its own changes only its own
    line here: limits, channels and documents, then volume, refusals and a head's audit, then Lark
    chat's three, the skill library's four, the models' eleven and the audit's one, the connectors'
    three, the tools' three, a document's life in four, the classified tables' three, an
    answer's evidence in four and the channels' seven, the modules in `CHECK_MODULES` order rather
    than the order a process imported them. Delete this and a check can drop out of the suite with
    the page simply listing one fewer row, or the page can lead with whichever module was imported
    first."""
    by_module: dict[str, list[str]] = {}
    for one in registered():
        by_module.setdefault(one.run.__module__, []).append(one.name)
    assert by_module["brain.ops.acceptance_checks"] == [
        "asking_past_a_window_is_refused_with_a_retry_hint",
        "a_webhook_channel_receives_once_and_stops_both_ways",
        "documents_are_answered_in_their_department_only",
    ]
    assert by_module["brain.ops.acceptance_oversight"] == [
        "unusual_volume_is_found_per_person",
        "repeated_refusals_raise_a_denial_notice",
        "a_head_reads_their_own_peoples_audit_entries_only",
    ]
    assert by_module["brain.ops.acceptance_checks_chat"] == [
        "a_lark_group_message_is_answered_only_when_it_names_the_bot",
        "a_person_bound_in_lark_is_given_their_web_answer_directly",
        "a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone",
    ]
    assert by_module["brain.ops.acceptance_checks_skills"] == [
        "a_pasted_or_uploaded_skill_waits_undecided_and_unread",
        "a_skill_is_imported_from_a_github_commit_and_from_an_address",
        "an_edit_is_a_new_version_and_moves_no_agent_until_reassigned",
        "categories_are_kept_and_offered_from_what_a_reader_was_shown",
    ]
    # One row per provider per leaf, then three; `tests/unit/test_acceptance_models.py` names them.
    assert len(by_module["brain.ops.acceptance_models"]) == 11
    # One per clause of M5.6.3; `tests/unit/test_acceptance_routing.py` names them.
    assert len(by_module["brain.ops.acceptance_routing"]) == 6
    assert by_module["brain.ops.acceptance_audit"] == [
        "each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught"
    ]
    assert by_module["brain.ops.acceptance_checks_connectors"] == [
        "manifest_review_refuses_a_projection_that_is_more_than_a_pointer",
        "a_sync_keeps_its_minimal_index_and_the_canary_reaches_no_table",
        "a_changed_declaration_makes_the_next_sync_refuse",
    ]
    assert by_module["brain.ops.acceptance_checks_tools"] == [
        "every_registered_tool_is_a_catalogue_row_under_the_name_grammar",
        "a_tool_named_for_a_sensitive_effect_must_declare_it",
        "a_switched_off_tool_is_refused_and_a_department_stops_its_own",
    ]
    assert by_module["brain.ops.acceptance_checks_lifecycle"] == [
        "a_newer_version_supersedes_the_older_and_answers_use_the_newer",
        "a_company_wide_request_waits_until_another_approver_approves_it",
        "a_review_that_fell_due_opens_its_steward_s_task_until_verified",
        "a_solution_answers_only_once_somebody_else_approves_it",
    ]
    assert by_module["brain.ops.acceptance_checks_tables"] == [
        "a_price_list_upload_classifies_every_column",
        "a_reader_without_the_cost_grant_is_told_the_sell_price_alone",
        "an_applied_mark_is_in_the_ledger_under_the_administrator",
    ]
    # What an answer stands on and how it declines; `tests/unit/test_acceptance_answers.py`.
    assert by_module["brain.ops.acceptance_answers"] == [
        "a_document_answer_cites_the_passage_it_was_shown_with_its_badge",
        "a_record_answer_cites_the_record_field_and_read_time",
        "four_kinds_of_nothing_are_kept_apart",
        "an_answer_and_a_refusal_say_what_the_asker_s_reach_covers",
    ]
    # What channels declare, carry and bind, keys and WhatsApp; `test_acceptance_channels.py`.
    assert by_module["brain.ops.acceptance_checks_channels"] == [
        "every_adapter_serves_its_declared_capabilities_and_plans_by_them",
        "a_reply_above_a_channels_ceiling_is_refused_and_points_to_ask",
        "each_adapter_is_listed_and_its_health_follows_its_deliveries",
        "a_code_minted_in_an_open_sign_in_binds_one_chat_account_once",
        "a_new_device_replaces_the_old_and_unbinding_is_recorded",
        "an_api_key_is_answered_until_it_is_revoked",
        "a_whatsapp_webhook_is_accepted_only_under_its_app_secret",
    ]
    assert list(by_module) == list(acceptance.CHECK_MODULES)
    oversight = {one.name: one.leaves for one in registered()}
    assert oversight["unusual_volume_is_found_per_person"] == ("M23.2.1",)
    assert oversight["repeated_refusals_raise_a_denial_notice"] == ("M23.2.2",)
    assert oversight["a_head_reads_their_own_peoples_audit_entries_only"] == ("M1.8.3",)


def test_every_reason_a_check_raises_is_a_literal_sentence() -> None:
    """`A_RESULT_NAMES_NO_DATA`: a reason is served on a public page, so it is written in the source
    and never built from a value. Every `CheckFailedError` and `CheckNotRunError` is raised with a
    string literal or a module constant. Delete this and a reason can be an f-string quoting the
    row a check read."""
    raised = 0
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign | ast.AnnAssign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
                continue
            raised += 1
            [argument] = node.args
            literal = isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            named = isinstance(argument, ast.Name) and argument.id in constants
            assert literal or named, ast.unparse(node)
    assert raised > 10


def test_an_exception_s_message_never_reaches_a_result() -> None:
    """Anything a check raises that is not a verdict is recorded by its type alone, and a verdict's
    own sentence is kept. Delete this and a database error quoting a row reaches the page."""
    outcome, reason = reason_for(ValueError("row 42 holds the cost 7.25"))
    assert outcome == FAILED and "7.25" not in reason and "ValueError" in reason
    assert reason_for(CheckFailedError("the window moved")) == (FAILED, "the window moved")
    assert reason_for(CheckNotRunError("no cache")) == (NOT_RUN, "no cache")
    assert reason_for(TimeoutError())[0] == FAILED


def test_a_run_is_owed_for_an_unchecked_commit_or_a_request_and_not_otherwise() -> None:
    """`ONE_RUN_PER_DEPLOYED_COMMIT`. Delete this and the worker checks every five minutes for ever,
    or never checks a new deploy, or ignores a Super Admin pressing run now."""
    later = LONG_AGO + timedelta(minutes=5)
    assert owed(serving="b", checked=("a",), asked_at=None, last_started=LONG_AGO) is (
        Occasion.DEPLOY
    )
    assert owed(serving="a", checked=("a",), asked_at=None, last_started=LONG_AGO) is None
    assert owed(serving="a", checked=("a",), asked_at=later, last_started=LONG_AGO) is (
        Occasion.REQUEST
    )
    assert owed(serving="a", checked=("a",), asked_at=LONG_AGO, last_started=later) is None


def test_the_page_lists_every_check_and_says_not_run_where_nothing_was_recorded() -> None:
    """A check with no row is not run, a stored outcome other than the three words is not run, and
    only the stored reason reaches the page. Delete this and a deploy the worker has not reached
    reads as the previous commit's pass."""
    checks = (
        Check(name="first_check", leaves=("M23.1.1",), sentence="One.", run=_nothing),
        Check(name="second_check", leaves=("M23.1.2",), sentence="Two.", run=_nothing),
    )
    rows = [
        {
            "check_name": "first_check",
            "leaves": "M23.1.1",
            "outcome": PASSED,
            "reason": None,
            "started_at": "2019-03-06T09:00:00+00:00",
            "checked_at": "2019-03-06T09:00:05+00:00",
        }
    ]
    body = served("abc1234", checks, rows)
    assert body["commit"] == "abc1234" and body["ran_at"] == "2019-03-06T09:00:00+00:00"
    assert [(one["name"], one["outcome"]) for one in body["checks"]] == [
        ("first_check", PASSED),
        ("second_check", NOT_RUN),
    ]
    odd = served("abc1234", checks[:1], [{**rows[0], "outcome": "crashed"}])
    assert odd["checks"][0]["outcome"] == NOT_RUN


def test_the_table_the_migration_and_the_registry_agree_on_every_shape() -> None:
    """Restated patterns, held equal to what they restate. Delete this and the table can refuse a
    check name the registry accepts, and a run's results are lost at the insert."""
    from brain.tables import acceptance as table
    from tests.unit.test_tables import VERSIONS, migration_module

    migration = migration_module(VERSIONS / "0133_acceptance_result.py")
    assert table.CHECK_NAME_PATTERN == acceptance.CHECK_NAME.pattern == migration.CHECK_NAME_PATTERN
    assert table.REASON_CHARS == acceptance.REASON_CHARS == migration.REASON_CHARS
    assert table.COMMIT_PATTERN == migration.COMMIT_PATTERN
    assert table.LEAVES_PATTERN == migration.LEAVES_PATTERN
    assert set(table.OUTCOMES) == {PASSED, FAILED, NOT_RUN}
    assert set(table.OCCASIONS) == {one.value for one in Occasion}
    assert "'acceptance_run'" in migration.WITH_ACCEPTANCE_RUN
    assert "'acceptance_run'" not in migration.WITHOUT_ACCEPTANCE_RUN


# ------------------------------------------------------------------------ the safety rules
def test_the_reserved_departments_are_slugs_the_product_accepts() -> None:
    """`TEST_DATA_LIVES_ONLY_IN_RESERVED_DEPARTMENTS`, and the slug grammar admits no hyphen, which
    is why they are acceptance_a and acceptance_b. Delete this and a reserved name the department
    table refuses stops every check at its first write."""
    import re

    assert len(RESERVED_DEPARTMENTS) == 2
    assert all(re.match(SLUG_PATTERN, one) for one in RESERVED_DEPARTMENTS)


def test_a_reserved_principal_is_named_by_the_prefix_and_nothing_else_is_made() -> None:
    """`A_RESERVED_PRINCIPAL_CANNOT_SIGN_IN`: every principal the harness makes carries the prefix
    and names this run, and the ledger's actor grammar holds it. Delete this and a check can make a
    principal whose id a real person's could be."""
    import re

    from brain.audit.ledger import IDENTIFIER

    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    made = harness.principal(RESERVED_DEPARTMENTS[0], "member")
    assert made == f"{RESERVED_PRINCIPAL_PREFIX}0a1b2c3d.a.member"
    assert re.match(IDENTIFIER, made) and re.match(IDENTIFIER, harness.actor)
    with pytest.raises(ValueError):
        harness.principal("finance", "member")
    with pytest.raises(ValueError):
        asyncio.run(harness.person("u_real", department=RESERVED_DEPARTMENTS[0]))
    with pytest.raises(ValueError):
        asyncio.run(harness.grant("u_real", "read:knowledge", acceptance_scope()))


def acceptance_scope() -> Any:
    from brain.core.scope import Scope

    return Scope.department(RESERVED_DEPARTMENTS[0])


def test_no_check_needs_a_login_and_the_one_setting_a_check_reads_names_public_code() -> None:
    """Every person a check acts as is a reserved principal made inside its transaction, so the
    install declares no setting for a test login and the harness has no way to bind one. The one
    acceptance setting names public skills for the import check to fetch, which is the install's
    to choose, and unset that check is not run rather than failed. Delete this and a check can come
    to depend on a login somebody has to create by hand."""
    from brain.install import BY_NAME

    assert [name for name in BY_NAME if "ACCEPTANCE" in name] == ["INSTALL_ACCEPTANCE_SKILL_SOURCE"]
    assert not hasattr(Harness, "test_login")


class CacheWithDeletes(FakeClient):
    """The limit store's fake, with the one command the run's undoing sends."""

    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    def delete(self, *names: str) -> int:
        self.deleted.extend(names)
        return sum(
            (self.sets.pop(one, None) is not None) + (self.counters.pop(one, None) is not None)
            for one in names
        )


def test_the_limit_check_passes_on_a_window_store_and_removes_only_its_own_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`, with the check itself driving the
    install's window store: three windows refused with a hint, then every key the check touched
    deleted and no other. Delete this and the check can pass against no store, or leave windows,
    or delete a real person's."""
    import brain.cache

    cache = CacheWithDeletes()
    cache.sets["lim:principal:u_real:minute"] = {"x": 1.0}
    monkeypatch.setattr(brain.cache, "make_client", lambda url, **_: cache)
    [limits] = [one for one in registered() if one.name.startswith("asking_past")]
    harness = Harness(
        run="0a1b2c3d",
        now=LONG_AGO,
        settings=settings_from({"BRAIN_VALKEY_URL": "redis://cache.invalid:6379/0"}),
        connection=None,  # type: ignore[arg-type]
    )

    async def run() -> None:
        try:
            await limits.run(harness)
        finally:
            await harness.undo(stream=__import__("sys").stderr)

    asyncio.run(run())
    assert cache.deleted and all("0a1b2c3d" in one for one in cache.deleted)
    assert list(cache.sets) == ["lim:principal:u_real:minute"]


def test_the_limit_check_waits_on_an_install_with_no_cache() -> None:
    """A check that cannot be asked says so rather than passing. Delete this and an install with no
    cache reports its limits as proved."""
    [limits] = [one for one in registered() if one.name.startswith("asking_past")]
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    with pytest.raises(CheckNotRunError):
        asyncio.run(limits.run(harness))


def test_the_documents_a_check_uploads_are_read_by_the_text_path() -> None:
    """The builders `tests/` cannot ship, held to the product's own parser: a PDF and a Word file
    read to their text, and the damaged PDF is refused as damaged. Delete this and a builder can
    drift from what an upload reads, which fails on the owner's server and not here."""
    from brain.knowledge.ingest import MediaType, ParseCause, ParseFailure, admit_upload
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import ReceivedUpload, read_for_text_path
    from brain.knowledge.visibility import KnowledgeVisibility
    from brain.ops.acceptance_documents import (
        CORRUPT_PDF,
        a_markdown_document,
        a_pdf,
        a_word_document,
    )

    def read(name: str, media_type: MediaType, body: bytes) -> Any:
        return read_for_text_path(
            ReceivedUpload(
                upload=admit_upload(filename=name, declared_type=media_type.value, content=body),
                body=body,
            ),
            kind=KnowledgeKind.SOP,
            placement=KnowledgeVisibility.of_department("acceptance_a", owner_id="u_owner"),
            owner_id="u_owner",
        )

    for name, media_type, body in (
        ("a.md", MediaType.MARKDOWN, a_markdown_document("Check", "QZWORDONE")),
        ("a.pdf", MediaType.PDF, a_pdf("QZWORDONE")),
        ("a.docx", MediaType.DOCX, a_word_document("Check", "QZWORDONE")),
    ):
        done = read(name, media_type, body)
        assert not isinstance(done, ParseFailure), name
        assert any("QZWORDONE" in block.text for block in done.blocks), name
    broken = read("b.pdf", MediaType.PDF, CORRUPT_PDF)
    assert isinstance(broken, ParseFailure) and broken.cause is ParseCause.CORRUPT
    with pytest.raises(ValueError):
        a_pdf("a (bracketed) word")


def test_the_acceptance_run_is_a_control_the_worker_starts_by_name() -> None:
    """Registered the way every control is: in `CONTROLS`, with a runner and a literal arm in
    `start_control`, at the cadence its own module declares. Delete this and the suite is a module
    nothing runs, which is the defect `brain.ops.controls` exists for."""
    from brain.ops.controls import control
    from brain.ops.schedule_runner import runner_for

    registered_control = control("acceptance_run")
    assert registered_control.every == acceptance_run.RUN_EVERY
    assert registered_control.entry_point == "brain.ops.acceptance_run:run_acceptance_now"
    assert runner_for("acceptance_run").run is not None
    source = (ROOT / "src" / "brain" / "ops" / "schedule_runner.py").read_text(encoding="utf-8")
    assert 'case "acceptance_run":' in source


def test_a_run_declines_in_report_only_mode() -> None:
    """Report-only mode is honoured by saying so. Delete this and a runner can ignore its mode."""
    from brain.ops.schedule_runner import acceptance_run as runner

    said = runner(LONG_AGO, True, "postgresql://nowhere.invalid/brain")
    assert said.startswith("report only")


# --------------------------------------------------------------------------- a real run
@contextmanager
def at_head(database: str) -> Iterator[str]:
    """A scratch database at head, named after this worktree's own test database as well, so two
    worktrees running this file against one local server never drop each other's."""
    from urllib.parse import urlsplit

    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url, database_url

    admin_url()
    own = urlsplit(database_url() or "").path.strip("/").removeprefix("brain_test_")
    with retirable(f"{database}_{own}"[:63] if own else database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0133 needs pgvector, which CI has")
        yield url


#: What the database half hands the run: an issuer the binding writer accepts, an address of the
#: install's own for the chat checks' link to Ask, and no cache.
INSTALL = {
    "INSTALL_OIDC_ISSUER": "https://id.example.invalid/realms/brain",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.invalid/callback",
}

#: Every table a check writes to and nothing may be left in afterwards.
WRITTEN_BY_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "auth.principal_identity",
    "gate.capability_grant",
    "obs.audit_entry",
    "ops.channel",
    "ops.channel_delivery",
    "gate.channel_event",
    "know.item",
    "know.chunk",
    "know.classified_table",
    "know.classified_row",
    "agent.skill",
    "agent.skill_review",
    "agent.skill_category",
    "agent.skill_assignment",
    "agent.agent",
    "agent.template_instance",
    "agent.template_version",
    "obs.request_telemetry",
    "gate.team",
    "gate.team_membership",
    "gate.department_lead",
    "ops.routing_rung",
    "ops.model_attempt",
    "ops.provider_health",
    "ops.chain_depth_alert",
    "ops.residency_constraint",
    "ops.model_provider",
    "ops.spend_actual",
    "ops.sensitive_read",
    "er.canonical",
    "proj.record",
    "ops.connector_connection",
    "ops.connector_sync",
    "ops.setting",
    "agent.tool_definition",
    "agent.tool_switch",
    "know.steward_task",
    "know.solution",
    "gate.suspension",
    "ops.outbox_event",
    "ops.outbox_delivery",
    "gate.grants_version",
    "gate.policy_epoch",
    "auth.binding_code",
    "auth.session",
    "auth.service_account",
    "auth.api_key",
    "ops.credential_write",
)


def counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_CHECKS
    }


def run_on(url: str, env: dict[str, str], *, force: bool = True) -> Any:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, **env})
    return asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url), settings=settings, commit="abc1234", force=force
        )
    )


@pytest.mark.needs_db
def test_on_a_real_database_the_checks_pass_and_leave_nothing_but_their_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The run as the worker makes it, against PostgreSQL at head.** Twice: every check that can
    be asked without a cache passes both times, including the two Lark checks needing a bound
    person now that the events route reads chat bindings (0118); the limits check says it was not
    run, the skill import says this install names no public skill, which is the declared default,
    and after
    both runs every table a check wrote to holds what it held before, while the result rows are
    there, one run each, keyed by the commit. Delete this and a check that commits, or one
    that cannot pass on a real schema, reaches the owner's server first."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_run") as url:
        before = counts(url)
        for name, value in INSTALL.items():
            monkeypatch.setenv(name, value)
        waited = run_on(url, {})
        bound = run_on(url, {})
        after = counts(url)
        recorded = sql(
            url,
            "SELECT commit, occasion, check_name, outcome, reason FROM ops.acceptance_result"
            " ORDER BY started_at, check_name",
        )
        runs = sql(url, "SELECT count(DISTINCT run_id) FROM ops.acceptance_result")

    for first, second in zip(waited[1], bound[1], strict=True):
        assert (first.name, first.outcome) == (second.name, second.outcome)
    outcomes = {one.name: (one.outcome, one.reason) for one in waited[1]}
    assert outcomes.pop("asking_past_a_window_is_refused_with_a_retry_hint")[0] == NOT_RUN
    assert outcomes.pop("a_skill_is_imported_from_a_github_commit_and_from_an_address") == (
        NOT_RUN,
        "this install names no public skill to import, so no import from GitHub was asked",
    )
    # No key and no hosted profile here, so every check that reaches a model says it was not run;
    # `tests/unit/test_acceptance_models.py` runs them against providers that answer, and
    # `tests/unit/test_acceptance_answers.py` the answer checks against the stand-in.
    for model_check in registered(
        (
            "brain.ops.acceptance_models",
            "brain.ops.acceptance_routing",
            "brain.ops.acceptance_answers",
        )
    ):
        assert outcomes.pop(model_check.name)[0] == NOT_RUN, model_check.name
    # Every act that exists was seen, and the leaf still cannot close: see its module.
    assert outcomes.pop("each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught") == (
        NOT_RUN,
        acceptance_audit.A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT,
    )
    assert outcomes == dict.fromkeys(outcomes, (PASSED, ""))
    assert len(outcomes) == 31
    assert after == before
    assert runs == [(2,)] and len(recorded) == 110
    assert {row[0] for row in recorded} == {"abc1234"} and {row[1] for row in recorded} == {
        "request"
    }


@pytest.mark.needs_db
def test_a_reserved_department_in_use_stops_the_run_before_it_writes() -> None:
    """`A_RESERVED_DEPARTMENT_HOLDING_A_REAL_PERSON_STOPS_THE_RUN`: somebody placed in acceptance_a
    means every check is recorded not run with that sentence, and no check is asked. Delete this
    and the checks grant, read and switch in a department a real person sits in."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_in_use") as url:
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
            " VALUES ('u_real', 'human', 'staff', 'A real person', 'acceptance_a')",
        )
        # Counted after the setup: since 0141 inserting a person writes its own audit entry, and
        # what this proves is that the run adds none.
        before = sql(url, "SELECT count(*) FROM obs.audit_entry")
        _, results = run_on(url, INSTALL)
        after = sql(url, "SELECT count(*) FROM obs.audit_entry")

    assert {one.outcome for one in results} == {NOT_RUN}
    assert all(one.reason.startswith("If a person on this install") for one in results)
    assert after == before


@pytest.mark.needs_db
def test_the_worker_runs_once_per_commit_and_again_when_asked() -> None:
    """The control's own decision against the table: owed for a commit with no run, not owed once
    it has one, owed again when a run request is newer than the last run. Delete this and the
    schedule checks every tick or never again."""
    from brain.session import make_app_engine
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_owed") as url:
        from brain.db import normalise_database_url

        async def occasion() -> Occasion | None:
            engine = make_app_engine(normalise_database_url(url))
            try:
                return await acceptance_run.occasion_now(engine, serving="abc1234")
            finally:
                await engine.dispose()

        first = asyncio.run(occasion())
        run_on(url, INSTALL, force=False)
        second = asyncio.run(occasion())
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
            " VALUES ('schedule.run_requested.acceptance_run', 'string', %s, 'asked', 'u_admin')",
            json.dumps((datetime.now(UTC) + timedelta(seconds=5)).isoformat()),
        )
        third = asyncio.run(occasion())

    assert (first, second, third) == (Occasion.DEPLOY, None, Occasion.REQUEST)


@pytest.mark.needs_db
def test_the_page_serves_the_newest_run_of_the_commit_it_is_asked_about() -> None:
    """`/api/acceptance.json` reads the table through the application's sessions and serves only
    the three words and the stored reason, for this process's commit or the one asked. Delete this
    and the page can show an older run's pass, or a row's text."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brain.acceptance_routes import router
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions

    with at_head("brain_acceptance_page") as url:
        run_on(url, INSTALL)
        app = FastAPI()
        app.include_router(router)
        engine = make_app_engine(normalise_database_url(url))
        app.state.db_sessions = make_application_sessions(engine)
        with TestClient(app) as client:
            asked = client.get("/api/acceptance.json", params={"commit": "abc1234"}).json()
            other = client.get("/api/acceptance.json", params={"commit": "fff9999"}).json()
        asyncio.run(engine.dispose())

    assert asked["commit"] == "abc1234" and asked["ran_at"]
    assert {one["outcome"] for one in asked["checks"]} <= {PASSED, FAILED, NOT_RUN}
    webhook = {one["name"]: one for one in asked["checks"]}[
        "a_webhook_channel_receives_once_and_stops_both_ways"
    ]
    assert webhook["outcome"] == PASSED and webhook["leaves"] == [
        "M10.2.1",
        "M10.3.3",
        "M10.4.5",
        "M10.6.3",
    ]
    assert other["ran_at"] == "" and {one["outcome"] for one in other["checks"]} == {NOT_RUN}


def test_results_are_written_whole_for_one_run() -> None:
    """A result keeps its reason within the column and its leaves as the check declared them.
    Delete this and a long reason is refused by the insert and the whole run's rows with it."""
    with pytest.raises(AcceptanceError):
        Result("some_check", ("M23.1.1",), PASSED, LONG_AGO, "x" * 241)
    with pytest.raises(AcceptanceError):
        Result("some_check", ("M23.1.1",), "crashed", LONG_AGO)
