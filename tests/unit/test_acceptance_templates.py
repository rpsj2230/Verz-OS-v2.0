"""The built-in templates' acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head, signs this release's catalogue onto it the way the
application's start does, and runs the check as the worker would: every built-in on file as
shipped, and each installed from the gallery's own route as a reserved administrator. Then it is
run against the product broken where it proves: a stored template that is not the shipped one, an
install that leaves the new agent enabled, and a SEM agent that may commit a change. Each fails
with its own sentence, and an install with nothing on file is not run without a vault and fails
with one.

Task ids: M13.5.1, M13.5.2, M13.5.3, M13.5.4, M13.5.5, M13.5.6, M13.5.7, M13.5.8, M13.5.9
Task ids: M13.5.10, M13.5.11, M13.5.12, M13.5.13, M13.5.14, M13.5.15, M13.5.16, M13.5.17
Task ids: M13.5.19, M13.5.20, M13.5.21, M13.5.22, M13.5.23, M13.2.1, M13.2.3, M13.2.6, M13.4.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    check_modules,
    registered,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_templates"
NAME = "every_built_in_template_is_on_file_and_installs_at_shadow"
PINNED = "a_template_version_is_signed_kept_and_pins_what_was_installed"
#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("agent.agent", "agent.template_version", "agent.template_instance")
#: A signing key for the test's own start, never a real one.
KEY = "ab" * 32


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_template_check_is_registered_with_the_leaves_it_proves() -> None:
    """Every M13.5 leaf but the receivables chaser's, whose thirty-day review is no install.
    Delete this and the check can close a leaf it does not exercise, or name an id no task has."""
    leaves = mine()[NAME].leaves
    assert mine()[PINNED].leaves == ("M13.2.1", "M13.2.3", "M13.2.6", "M13.4.1")
    assert "M13.5.18" not in leaves
    assert set(leaves) == {f"M13.5.{n}" for n in range(1, 24)} - {"M13.5.18"}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    every = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(leaves) <= every


def test_the_template_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in page order, held in this module's own file. Delete
    this and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME, PINNED]
    assert MODULE in check_modules()


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a named literal that fits
    the result's. Delete this and a reason can be cut off mid-word on the page."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_templates as module

    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS
    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "CheckFailedError",
            "CheckNotRunError",
        }:
            [argument] = node.args
            value = (
                getattr(module, argument.id)
                if isinstance(argument, ast.Name)
                else ast.literal_eval(argument)
            )
            reasons.append(value)
    assert len(reasons) >= 8
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


def test_the_check_copies_a_template_under_its_own_id_and_changes_nothing_else() -> None:
    """The copy the check installs is the shipped manifest with a template id of its own, so its
    content digest differs only by that id. Delete this and the copy could drop a tool or the
    leash, and the check would prove an install of something the catalogue never shipped."""
    from brain.agents.catalogue import sem_agent
    from brain.ops.acceptance_checks_templates import _copy

    shipped = sem_agent()
    copied = _copy(shipped, "acceptance_copy")
    assert copied.identity.template_id == "acceptance_copy"
    assert copied.model_copy(update={"identity": shipped.identity}) == shipped


def signed_onto(url: str, catalogue: Sequence[Any] | None = None) -> None:
    """The catalogue signed onto the database the way the application's start signs it."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from brain.agents.catalogue import CATALOGUE
    from brain.db import normalise_database_url
    from brain.ops.builtin_templates import sign_built_ins
    from brain.session import make_app_engine

    async def sign() -> None:
        engine = make_app_engine(normalise_database_url(url))
        try:
            await sign_built_ins(
                async_sessionmaker(engine, expire_on_commit=False),
                key=KEY,
                at=datetime(2019, 1, 1, tzinfo=UTC),
                actor="u_start",
                trace_id="0" * 32,
                catalogue=CATALOGUE if catalogue is None else catalogue,
            )
        finally:
            await engine.dispose()

    asyncio.run(sign())


def run_checks(url: str, checks: Sequence[Check], **settings: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **settings}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_on_a_real_database_every_built_in_installs_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head with the catalogue signed
    on.** It passes, and the agents, versions and instances hold what they held before. Delete
    this and a built-in template can stop installing with nothing on the owner's install saying
    so, or a check that commits an agent can reach his server."""
    with at_head("brain_acceptance_templates") as url:
        signed_onto(url)
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, ""), PINNED: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_with_nothing_on_file_the_check_is_not_run_without_a_vault_and_fails_with_one() -> None:
    """**No key signs nothing, and a key that signed nothing is a start that failed.** Delete this
    and an install with a vault and an empty catalogue would read as not run, which is the
    failure the owner most needs to see."""
    from brain.ops.acceptance_checks_templates import (
        NOTHING_ON_FILE_AND_NO_VAULT,
        NOTHING_ON_FILE_WITH_A_VAULT,
    )

    with at_head("brain_acceptance_templates_empty") as url:
        without = run_checks(url, (mine()[NAME],))
        with_vault = run_checks(
            url, (mine()[NAME],), BRAIN_VAULT_ADDRESS="http://vault.invalid:8200"
        )
    assert without[NAME] == (NOT_RUN, NOTHING_ON_FILE_AND_NO_VAULT)
    assert with_vault[NAME] == (FAILED, NOTHING_ON_FILE_WITH_A_VAULT)


@pytest.mark.needs_db
def test_a_stored_template_that_is_not_the_shipped_one_fails_the_check() -> None:
    """A built-in on file whose persona differs from this release's. Delete this and an install
    could serve an edited or stale template under a built-in's name with the check green."""
    from brain.agents.catalogue import CATALOGUE
    from brain.ops.acceptance_checks_templates import NOT_AS_SHIPPED

    edited = tuple(
        one.model_copy(update={"persona": one.persona + " Edited."}) if index == 0 else one
        for index, one in enumerate(CATALOGUE)
    )
    with at_head("brain_acceptance_templates_edited") as url:
        signed_onto(url, edited)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_AS_SHIPPED)


@pytest.mark.needs_db
def test_an_install_that_leaves_the_agent_enabled_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path writing the new agent enabled rather than disabled at Shadow. Delete
    this and a template agent could start answering the moment it is installed."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_templates import NOT_AT_SHADOW

    kept = install_store.agent_values

    def enabled(record: Any) -> dict[str, Any]:
        return {**kept(record), "disabled_at": None}

    monkeypatch.setattr(install_store, "agent_values", enabled)
    with at_head("brain_acceptance_templates_enabled") as url:
        signed_onto(url)
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, NOT_AT_SHADOW)
    assert after == before


@pytest.mark.needs_db
def test_a_sem_agent_that_may_commit_a_change_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalogue's SEM agent shipped able to write: on file and installed exactly as shipped,
    and still not what its leaf asks. Delete this and "a human commits budget changes" would rest
    on nothing but the catalogue's own docstring."""
    import brain.agents.catalogue as catalogue
    from brain.core.envelope import SideEffect
    from brain.ops.acceptance_checks_templates import SEM_WRITES

    writes = tuple(
        one.model_copy(
            update={
                "guardrails": one.guardrails.model_copy(
                    update={"max_side_effect": SideEffect.WRITE}
                )
            }
        )
        if one.identity.template_id == "sem_agent"
        else one
        for one in catalogue.CATALOGUE
    )
    monkeypatch.setattr(catalogue, "CATALOGUE", writes)
    with at_head("brain_acceptance_templates_sem") as url:
        signed_onto(url, writes)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, SEM_WRITES)


#: Each break to the database under the pinned check, and the sentence it must fail with. The
#: statements run as the database's owner on the test's own database, never on an install.
SCHEMA_BREAKS: dict[str, tuple[tuple[str, ...], str]] = {
    "mutable": (
        (
            "GRANT UPDATE ON agent.template_version TO brain_app",
            "CREATE POLICY acceptance_mutable ON agent.template_version FOR UPDATE TO brain_app"
            " USING (true) WITH CHECK (true)",
        ),
        "NOT_IMMUTABLE",
    ),
    "repinned": (
        (
            "CREATE FUNCTION agent.acceptance_repin() RETURNS trigger LANGUAGE plpgsql AS $$"
            " BEGIN UPDATE agent.template_instance SET effective_hash = repeat('0', 64)"
            " WHERE template_id = NEW.template_id; RETURN NEW; END $$",
            "CREATE TRIGGER acceptance_repin AFTER INSERT ON agent.template_version"
            " FOR EACH ROW EXECUTE FUNCTION agent.acceptance_repin()",
        ),
        "MOVED_BY_A_NEW_VERSION",
    ),
    "unpinned": (
        (
            "CREATE FUNCTION agent.acceptance_unpin() RETURNS trigger LANGUAGE plpgsql AS $$"
            " BEGIN NEW.content_digest := repeat('0', 64); RETURN NEW; END $$",
            "CREATE TRIGGER acceptance_unpin BEFORE INSERT ON agent.template_instance"
            " FOR EACH ROW EXECUTE FUNCTION agent.acceptance_unpin()",
        ),
        "NOT_PINNED",
    ),
    "unsealed": (
        (
            "ALTER TABLE agent.template_instance DROP CONSTRAINT"
            " ck_template_instance_sealed_paths_are_absent",
            "ALTER TABLE agent.template_instance DROP CONSTRAINT"
            " ck_template_instance_overlay_paths_are_settable",
        ),
        "NOT_SEALED",
    ),
    "oversealed": (
        (
            "ALTER TABLE agent.template_instance ADD CONSTRAINT acceptance_no_persona"
            " CHECK (NOT overlay ? 'persona')",
        ),
        "SEALED_TOO_WIDELY",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(SCHEMA_BREAKS))
def test_the_pinned_check_fails_where_the_database_is_broken(broken: str) -> None:
    """Five breaks, one per property: a published version the application may update (M13.2.1),
    an installed instance moved by a new version (M13.4.1), an instance that does not carry the
    digest it was installed from (M13.2.3), the seal dropped and the seal widened to a settable
    path (M13.2.6). Each fails with its own sentence. Delete this and the check can pass with
    the property gone."""
    import brain.ops.acceptance_checks_templates as module
    from tests.fixtures.scratch_postgres import sql

    statements, reason = SCHEMA_BREAKS[broken]
    with at_head(f"brain_acceptance_templates_{broken}") as url:
        for statement in statements:
            sql(url, statement)
        outcome = run_checks(url, (mine()[PINNED],))
    assert outcome[PINNED] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_a_gallery_that_installs_a_version_it_did_not_sign_fails_the_pinned_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The signature check gone from the install path (M13.2.1). Delete this and a template
    nobody on the install published could become an agent with the check green."""
    import brain.agents.template as template
    from brain.ops.acceptance_checks_templates import NOT_SIGNED

    def trusting(signed: Any, *, key: str) -> None:
        del signed, key

    monkeypatch.setattr(template, "verify", trusting)
    with at_head("brain_acceptance_templates_unsigned") as url:
        outcome = run_checks(url, (mine()[PINNED],))
    assert outcome[PINNED] == (FAILED, NOT_SIGNED)


@pytest.mark.needs_db
def test_a_shadow_pinned_agent_whose_leash_can_be_changed_fails_the_template_check() -> None:
    """The seal dropped under the catalogue check: the accountant and SEM agents install at Shadow
    and their leash can then be overlaid away. Delete this and "Shadow-pinned" would mean only
    "starts at Shadow", which every template already does."""
    from brain.ops.acceptance_checks_templates import NOT_PINNED_AT_SHADOW
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_templates_unpinned_leash") as url:
        signed_onto(url)
        for statement in SCHEMA_BREAKS["unsealed"][0]:
            sql(url, statement)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_PINNED_AT_SHADOW)


@pytest.mark.needs_db
def test_a_shipped_template_missing_from_the_install_fails_the_template_check() -> None:
    """The catalogue signed on without its last template. Delete this and a release whose start
    dropped a built-in would pass, the gallery simply listing one fewer."""
    from brain.agents.catalogue import CATALOGUE
    from brain.ops.acceptance_checks_templates import MISSING

    with at_head("brain_acceptance_templates_missing") as url:
        signed_onto(url, CATALOGUE[:-1])
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, MISSING)


@pytest.mark.needs_db
def test_an_install_that_widens_the_ceiling_fails_the_template_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path granting the new agent a capability its template never declared. Delete
    this and an installed template could reach more than its manifest says with the check green."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_templates import NOT_ITS_CEILING

    kept = install_store.agent_values

    def widened(record: Any) -> dict[str, Any]:
        found = kept(record)
        return {**found, "capabilities": [*found["capabilities"], "read:everything.else"]}

    monkeypatch.setattr(install_store, "agent_values", widened)
    with at_head("brain_acceptance_templates_widened") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_ITS_CEILING)


@pytest.mark.needs_db
def test_an_install_that_lands_outside_the_installer_s_department_fails_the_template_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path writing the new agent with no department when its installer asked for
    one for their department. Delete this and an install could land an agent nobody in the
    department is shown."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_templates import NOT_IN_ITS_DEPARTMENT

    kept = install_store.agent_values

    def nowhere(record: Any) -> dict[str, Any]:
        return {**kept(record), "department": None, "visibility": "personal"}

    monkeypatch.setattr(install_store, "agent_values", nowhere)
    with at_head("brain_acceptance_templates_nowhere") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_IN_ITS_DEPARTMENT)


@pytest.mark.needs_db
def test_an_install_that_raises_the_side_effect_ceiling_fails_the_template_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path letting every new agent write, whatever its template declared. Delete
    this and the side-effect half of the ceiling could drift with only the capabilities watched."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_templates import NOT_ITS_CEILING

    kept = install_store.agent_values

    def writes(record: Any) -> dict[str, Any]:
        return {**kept(record), "max_side_effect": "write"}

    monkeypatch.setattr(install_store, "agent_values", writes)
    with at_head("brain_acceptance_templates_writes") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_ITS_CEILING)
