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
from brain.ops import (
    acceptance,
    acceptance_audit,
    acceptance_checks_accounts,
    acceptance_checks_channels,
    acceptance_checks_class_pools,
    acceptance_checks_recovery,
    acceptance_checks_services,
    acceptance_operations_console,
    acceptance_run,
)
from brain.ops import acceptance_checks_deployment as acceptance_deployment
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
#: Every module a check or the harness raises a verdict from: the harness, and each module the
#: suite finds, so a new check module is held to the literal-reason rule the day it is written.
SOURCES = (
    ROOT / "src" / "brain" / "ops" / "acceptance_run.py",
    *(ROOT / "src" / f"{module.replace('.', '/')}.py" for module in acceptance.check_modules()),
)

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


async def _nothing(harness: Harness) -> None:
    del harness


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every run of the suite here imports from a GitHub that does not answer, so no test in this
    file reaches the network; `tests/unit/test_acceptance_skills.py` fakes one that does."""
    from brain.ops import acceptance_checks_skills, acceptance_workspace
    from brain.ops.artifact_store import ARTIFACT_BUCKET
    from brain.ops.object_store import S3Backend, StoreCredential
    from brain.ops.storage import Backend, config_for
    from tests.fixtures.fake_s3 import FakeS3
    from tests.unit.test_acceptance_skills import unreachable

    monkeypatch.setattr(acceptance_checks_skills, "_transport", unreachable)
    # The artifact check's object store: the real client over a fake bucket, because this file
    # runs with no vault and the product builds its store from the vault.
    key = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test")
    fake = FakeS3(credential=key).holding(ARTIFACT_BUCKET, {})
    backend = S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url="http://objects.example.test:8333"),
        key,
        transport=fake.transport(),
    )
    monkeypatch.setattr(acceptance_workspace, "artifact_backend", lambda h: (backend, "brain"))


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


def checks_in(module: str) -> list[str]:
    """The checks one module registers, in the order the Install page lists them.

    What each check module's own test file holds its list against, so a package adding a check
    edits its own file and never a list every package appends to.
    """
    return [one.name for one in registered() if one.run.__module__ == module]


def test_the_suite_is_every_check_module_in_the_order_each_declares() -> None:
    """`A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`, on the discovered result. The page lists the
    modules by the key each declares, ties by name, and never in the order a process imported
    them; every module that registers a check is in it, and every check in it is in one of them.
    Delete this and a check module can drop out of the run with the page listing fewer rows, or
    the page can lead with whichever module was imported first."""
    import importlib

    modules = acceptance.check_modules()
    keys = [getattr(importlib.import_module(one), acceptance.ORDER_ATTRIBUTE) for one in modules]
    assert list(modules) == sorted(modules, key=lambda one: (keys[modules.index(one)], one))
    assert modules[0] == "brain.ops.acceptance_checks"
    assert len(modules) >= 20
    suite = registered()
    by_module: dict[str, list[str]] = {}
    for one in suite:
        by_module.setdefault(one.run.__module__, []).append(one.name)
    assert list(by_module) == list(modules)
    assert {one.run.__module__ for one in suite} == set(modules)
    assert all(acceptance.is_check_module_name(one) for one in modules)


def test_the_first_two_modules_hold_their_checks_in_order() -> None:
    """The two modules with no test file of their own, held here. Delete this and a check can
    drop out of either with the page listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks") == [
        "asking_past_a_window_is_refused_with_a_retry_hint",
        "a_webhook_channel_receives_once_and_stops_both_ways",
        "documents_are_answered_in_their_department_only",
    ]
    assert checks_in("brain.ops.acceptance_oversight") == [
        "unusual_volume_is_found_per_person",
        "repeated_refusals_raise_a_denial_notice",
        "a_head_reads_their_own_peoples_audit_entries_only",
    ]
    oversight = {one.name: one.leaves for one in registered()}
    assert oversight["unusual_volume_is_found_per_person"] == ("M23.2.1",)
    assert oversight["repeated_refusals_raise_a_denial_notice"] == ("M23.2.2",)
    assert oversight["a_head_reads_their_own_peoples_audit_entries_only"] == ("M1.8.3",)


def test_a_module_that_registers_checks_is_placed_or_refused_and_never_skipped() -> None:
    """The three refusals `ordered_check_modules` makes, with its positive case beside them: a
    module registering checks with no key, a key with no checks, and a check registered outside
    the prefix are each refused; placed modules come back by key, ties by name. Delete this and
    a module that forgot its key drops out of the Install page with nothing saying so."""
    from brain.ops.acceptance import AcceptanceError, ordered_check_modules

    declared = {"b.late": 20, "b.one": 10, "b.also": 10, "b.first": 5, "b.helper": None}
    placed = ["b.late", "b.one", "b.also", "b.first"]
    assert ordered_check_modules(declared, placed) == ("b.first", "b.also", "b.one", "b.late")
    with pytest.raises(AcceptanceError, match="declare no CHECK_ORDER"):
        ordered_check_modules(declared, [*placed, "b.helper"])
    with pytest.raises(AcceptanceError, match="register no check"):
        ordered_check_modules(declared, ["b.one", "b.also", "b.first"])
    with pytest.raises(AcceptanceError, match="does not look in"):
        ordered_check_modules(declared, [*placed, "elsewhere"])


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


def test_a_model_call_that_stopped_a_check_is_named_by_how_it_ended_and_by_nothing_it_carried() -> (
    None
):
    """`A_MODEL_CALL_THAT_STOPS_A_CHECK_IS_NAMED_BY_HOW_IT_ENDED`. The moonshot check that timed
    out on the owner's install on 2026-09-29 was recorded as "stopped on ProviderUnavailable" and
    read as a planning fault until somebody read the worker's log. Every way a call can end has a
    reason in the Models screen's words, a timeout says it timed out, and neither the step's
    deployment nor the provider's own text reaches the reason. Delete this and the next provider
    failure on the install is a type name again, or a reason starts quoting what a provider said.
    """
    from brain.models.driver import DriverFailure, ProviderUnavailable

    said = "provider said: row 42 holds the cost 7.25"
    shapes = [
        DriverFailure(deployment_id="step-one", timed_out=True, detail=said),
        DriverFailure(deployment_id="step-one", connection_failed=True, detail=said),
        DriverFailure(deployment_id="step-one", context_exceeded=True, detail=said),
        DriverFailure(deployment_id="step-one", refused=True, status=400, detail=said),
        *(
            DriverFailure(deployment_id="step-one", status=one, detail=said)
            for one in (400, 401, 429, 503)
        ),
    ]
    reasons = [reason_for(ProviderUnavailable(one)) for one in shapes]
    assert all(outcome == FAILED for outcome, _ in reasons)
    assert all(
        reason.startswith(acceptance.A_MODEL_CALL_STOPPED_THE_CHECK) for _, reason in reasons
    )
    assert all("7.25" not in reason and "step-one" not in reason for _, reason in reasons)
    # Eight endings, eight sentences: no two ways of failing read the same.
    assert len({reason for _, reason in reasons}) == len(shapes)
    assert reasons[0] == (
        FAILED,
        "a model call stopped the check: The provider did not answer in time.",
    )


def test_a_planner_that_found_no_step_is_named_by_its_own_public_sentence() -> None:
    """The planner's refusal carries a sentence the product wrote for a person, and the reason is
    that sentence, while the detail naming each skipped step is left out. Delete this and a check
    stopped because no step was configured, or every step was resting, reads as a type name."""
    from brain.models.routing import NoCompliantRoute

    refused = NoCompliantRoute(
        "tier=main has no usable rung: step-one=circuit_open",
        public_message="No model is configured to handle that.",
    )
    assert reason_for(refused) == (
        FAILED,
        "no step of the ladder could be tried: No model is configured to handle that.",
    )


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
    "er.alias",
    "er.identifier",
    "er.link",
    "er.observation",
    "er.blocked_value",
    # The merge checks plant their own entities and merge and unmerge them (`0183`).
    "er.merge",
    "er.unmerge",
    "er.review_item",
    "proj.record",
    "proj.record_retired",
    "proj.source_epoch",
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
    "mem.persistent",
    "mem.adaptive",
    "mem.learning",
    "mem.correction",
    "auth.binding_code",
    "auth.session",
    "auth.service_account",
    "auth.api_key",
    "ops.credential_write",
    "gate.fast_path_rule",
    "agent.browser_envelope",
    "agent.browser_session",
    "obs.trace_step",
    "obs.trace_read",
    "mem.mark",
    "agent.learning_pause",
    "ops.operation",
    "ops.budget_version",
    "gate.role_grant",
    "auth.staff_member",
    "agent.manifest_draft",
    "agent.manifest_revision",
    "agent.manifest_act",
    "gate.elevation_request",
    "gate.break_glass_notice",
    # A Lark Base indexed by a check offers its table's grants on the grants screen.
    "gate.capability_registry",
    "gate.capability_pack",
    "gate.capability_pack_assignment",
    "gate.role_grant",
    "agent.artifact",
    "agent.artifact_change",
    "agent.leash_change",
    "agent.supervised_action",
    "agent.action_verdict",
    "agent.supervision_pin",
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
    person now that the events route reads chat bindings (0118); the three checks needing a cache
    say they were not run, the skill import says this install names no public skill, which is
    the declared default, and after both runs every table a check wrote to holds what it held
    before, while the result rows are there, one run each, keyed by the commit. Delete this and
    a check that commits, or one that cannot pass on a real schema, reaches the owner's server
    first."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance_ingest import offline_install

    with at_head("brain_acceptance_run") as url:
        before = counts(url)
        for name, value in INSTALL.items():
            monkeypatch.setenv(name, value)
        # The link answered by a recorded page and the queue driver's count stood in, as
        # `tests/unit/test_acceptance_ingest.py` runs them: a test never asks the network.
        offline_install(monkeypatch)
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
    # Every registered check ran, by name, and nothing else did: derived rather than counted,
    # so a package adding a check changes no line here.
    suite = [one.name for one in registered()]
    assert list(outcomes) == suite
    assert outcomes.pop("asking_past_a_window_is_refused_with_a_retry_hint")[0] == NOT_RUN
    # No vault here, so the start signed no built-in template;
    # `tests/unit/test_acceptance_templates.py` signs the catalogue on and runs it.
    assert outcomes.pop("every_built_in_template_is_on_file_and_installs_at_shadow")[0] == NOT_RUN
    assert outcomes.pop("the_rate_limits_screen_lists_the_windows_refusing_now")[0] == NOT_RUN
    assert outcomes.pop("rate_limits_and_capacity_answer_their_readers")[0] == NOT_RUN
    assert outcomes.pop("three_classes_share_one_budget_and_give_way_in_order")[0] == NOT_RUN
    # No cache here either; `tests/unit/test_acceptance_cache.py` runs it with a store in its place.
    assert outcomes.pop("a_cached_answer_reaches_only_the_reach_it_was_computed_for")[0] == NOT_RUN
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
    # The model pin's check plans its stand-ins only on a hosted install, and this one keeps text
    # at home; `tests/unit/test_acceptance_skill_pins.py` runs it with the hosted profile.
    assert (
        outcomes.pop("an_agent_s_pinned_model_is_tried_first_with_its_level_behind")[0] == NOT_RUN
    )
    # A follow-up is answered by a model too; `tests/unit/test_acceptance_threads.py` runs it.
    assert outcomes.pop("a_follow_up_is_answered_from_what_its_thread_cited")[0] == NOT_RUN
    assert (
        outcomes.pop("a_document_is_added_answered_replaced_and_falls_due_for_review")[0] == NOT_RUN
    )
    # Both escalation checks ask through the stand-in; `tests/unit/test_acceptance_escalation.py`
    # runs them with the hosted profile and a vault the test answers for.
    for escalation_check in registered(("brain.ops.acceptance_escalation",)):
        assert outcomes.pop(escalation_check.name)[0] == NOT_RUN, escalation_check.name
    # An agent's skill reaches a model too; `tests/unit/test_acceptance_skill_runs.py` runs it.
    assert outcomes.pop("an_agents_run_reads_its_assigned_skills_and_its_level")[0] == NOT_RUN
    # No antivirus and no object store here; `tests/unit/test_acceptance_ingest.py` runs both.
    assert outcomes.pop("the_antivirus_test_file_is_refused_as_malware")[0] == NOT_RUN
    # No optional service is switched on here; `tests/unit/test_acceptance_services.py` switches
    # each on and answers for it.
    assert outcomes.pop("the_detector_finds_every_entity_the_scrub_relies_on_it_for") == (
        NOT_RUN,
        acceptance_checks_services.NO_DETECTOR_HERE,
    )
    for ledger_check in (
        "the_trace_ledger_runs_as_its_five_services",
        "every_trace_ledger_service_runs_under_its_budgeted_limit",
        "a_run_sent_to_the_ledger_is_found_there_with_its_model_call",
    ):
        assert outcomes.pop(ledger_check) == (NOT_RUN, acceptance_checks_services.NO_LEDGER_HERE)
    # No class pooler runs here; `tests/unit/test_class_pools.py` stands a limited login in for
    # the batch pool, reports it running and passes.
    assert outcomes.pop("a_batch_job_holding_its_share_cannot_take_a_persons_connection") == (
        NOT_RUN,
        acceptance_checks_class_pools.NOT_RUNNING_HERE,
    )
    # No relay is saved here; `tests/unit/test_acceptance_channels.py` saves one and passes.
    email = "an_email_is_taken_signed_and_answered_by_the_install_s_relay"
    assert outcomes.pop(email) == (NOT_RUN, acceptance_checks_channels.NO_RELAY_IS_SAVED)
    assert outcomes.pop("mail_in_the_mailbox_is_read_answered_and_marked") == (
        NOT_RUN,
        acceptance_checks_channels.NO_RELAY_IS_SAVED_FOR_THE_MAILBOX,
    )
    # No relay here either; `tests/unit/test_acceptance_accounts.py` saves one and passes.
    assert outcomes.pop("forgot_password_is_sent_through_the_relay_on_notifications") == (
        NOT_RUN,
        acceptance_checks_accounts.NO_RELAY_FOR_THE_RESET_EMAIL,
    )
    assert outcomes.pop("a_queued_file_is_kept_in_the_store_and_read_by_the_worker")[0] == NOT_RUN
    # Every act, the chain, the trace and the export were seen, and no deploy is recorded here to
    # be kept out of the export: `tests/unit/test_acceptance_audit.py` records one and passes.
    assert outcomes.pop("each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught") == (
        NOT_RUN,
        acceptance_audit.NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT,
    )
    # The test process is not a worker container, so the checks that read the worker they run
    # in say so; `tests/unit/test_acceptance_deployment.py` runs them in a worker's environment.
    for worker_check in (
        "the_worker_serves_each_traffic_class_from_its_own_slots",
        "every_database_client_is_bounded_within_the_install_s_ceiling",
        "the_scrub_meets_its_budget_on_this_install_s_processor",
    ):
        assert outcomes.pop(worker_check) == (NOT_RUN, acceptance_deployment.NOT_IN_A_WORKER)
    # No worker has ticked here, so neither recovery sweep has a scheduled run to judge;
    # `tests/unit/test_acceptance_recovery.py` records one and both pass.
    for recovery_check in registered(("brain.ops.acceptance_checks_recovery",)):
        assert outcomes.pop(recovery_check.name) == (
            NOT_RUN,
            acceptance_checks_recovery.NO_SCHEDULED_RUN_YET,
        )
    # Nothing started the application against this database, so nothing furnished it;
    # `tests/unit/test_acceptance_operations_console.py` furnishes one and the check passes.
    assert outcomes.pop("the_install_was_furnished_once_by_the_product") == (
        NOT_RUN,
        acceptance_operations_console.NOTHING_HAS_FURNISHED_THIS_DATABASE,
    )
    assert outcomes == dict.fromkeys(outcomes, (PASSED, ""))
    assert after == before
    assert runs == [(2,)] and len(recorded) == 2 * len(suite)
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
