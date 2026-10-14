"""The role templates' acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head, signs this release's catalogue onto it the way the
application's start does, and runs the check as the worker would. Then it runs the check against
the product broken where it proves: a stored template that is not the shipped one, a template
declaring a connector this release does not ship, a skill pinned at a digest nothing furnishes, a
tool nothing binds, an install that leaves the agent enabled and a gate that starts no run. Each
fails with its own sentence.

Task ids: M13.7.9, M13.8.7, M13.8.8
"""

from __future__ import annotations

import json
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
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks, signed_onto, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_role_templates"
NAME = "the_role_templates_declare_their_sources_and_would_answer"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_role_template_check_is_registered_with_the_three_leaves_it_proves() -> None:
    """The maintenance agent's leaf, the SEO agent's and the four-role catalogue leaf, each a
    leaf the work breakdown holds. Delete this and the check can close a leaf it does not
    exercise or name an id no task has."""
    leaves = mine()[NAME].leaves
    assert set(leaves) == {"M13.7.9", "M13.8.7", "M13.8.8"}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    every = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(leaves) <= every


def test_the_role_template_check_is_listed_in_its_page_order() -> None:
    """The one check this module registers, held in this module's own file and found by the
    suite. Delete this and the check can drop out of the module with the page listing one fewer
    row."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a named literal that fits
    the result's. Delete this and a reason can be cut off mid-word on the page."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_role_templates as module

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
    assert len(reasons) >= 10
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


@pytest.mark.needs_db
def test_on_a_real_database_every_role_template_is_on_file_binds_installs_and_starts_a_run() -> (
    None
):
    """**The check as the worker runs it, against PostgreSQL at head with the catalogue signed
    on.** It passes, and the agents, versions and instances hold what they held before. Delete
    this and a role template can stop answering on every install with nothing saying so, or a
    check that commits an agent can reach the owner's server."""
    with at_head("brain_acceptance_role_templates") as url:
        signed_onto(url)
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_with_nothing_on_file_the_check_is_not_run_without_a_vault_and_fails_with_one() -> None:
    """**No key signs nothing, and a key that signed nothing is a start that failed.** Delete this
    and an install with a vault and an empty catalogue would read as not run, which is the
    failure the owner most needs to see."""
    from brain.ops.acceptance_checks_role_templates import (
        NOTHING_ON_FILE_AND_NO_VAULT,
        NOTHING_ON_FILE_WITH_A_VAULT,
    )

    with at_head("brain_acceptance_role_templates_empty") as url:
        without = run_checks(url, (mine()[NAME],))
        with_vault = run_checks(
            url, (mine()[NAME],), BRAIN_VAULT_ADDRESS="http://vault.invalid:8200"
        )
    assert without[NAME] == (NOT_RUN, NOTHING_ON_FILE_AND_NO_VAULT)
    assert with_vault[NAME] == (FAILED, NOTHING_ON_FILE_WITH_A_VAULT)


def _broken(monkeypatch: pytest.MonkeyPatch, template_id: str, **update: Any) -> tuple[Any, ...]:
    """The catalogue with one template changed, the module's own copy replaced so the check reads
    the changed one as the release's shipped one."""
    import brain.agents.catalogue as catalogue

    changed = tuple(
        one.model_copy(update=update) if one.identity.template_id == template_id else one
        for one in catalogue.CATALOGUE
    )
    monkeypatch.setattr(catalogue, "CATALOGUE", changed)
    return changed


@pytest.mark.needs_db
def test_a_stored_role_template_that_is_not_the_shipped_one_fails_the_check() -> None:
    """A role template on file whose persona differs from this release's. Delete this and an
    install could serve an edited or stale maintenance agent under the built-in's name with the
    check green."""
    from brain.agents.catalogue import CATALOGUE
    from brain.ops.acceptance_checks_role_templates import NOT_AS_SHIPPED

    edited = tuple(
        one.model_copy(update={"persona": one.persona + " Edited."})
        if one.identity.template_id == "maintenance_agent"
        else one
        for one in CATALOGUE
    )
    with at_head("brain_acceptance_role_templates_edited") as url:
        signed_onto(url, edited)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_AS_SHIPPED)


@pytest.mark.needs_db
def test_a_role_template_the_release_ships_and_the_install_does_not_hold_fails_the_check() -> None:
    """The catalogue signed onto the install without the maintenance agent, as an install started
    by an older release would hold it. Delete this and an install missing a role template reads
    as passing while its gallery does not offer the agent."""
    from brain.agents.catalogue import CATALOGUE
    from brain.ops.acceptance_checks_role_templates import MISSING

    without = tuple(one for one in CATALOGUE if one.identity.template_id != "maintenance_agent")
    with at_head("brain_acceptance_role_templates_missing") as url:
        signed_onto(url, without)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, MISSING)


@pytest.mark.needs_db
def test_an_install_whose_agent_starts_above_shadow_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route answering that the new agent's leash holds a rung above the bottom one. Delete
    this and a role agent could start with autonomy nobody has watched it earn, with the check
    green because the agent is merely disabled."""
    import brain.agent_lifecycle_routes as routes
    from brain.ops.acceptance_checks_role_templates import NOT_AT_SHADOW

    kept = routes.leash_view

    def raised(leash: Any) -> Any:
        return [one.model_copy(update={"rung": "assisted"}) for one in kept(leash)] or [
            routes.LeashRungView(target="x", rung="assisted")
        ]

    monkeypatch.setattr(routes, "leash_view", raised)
    with at_head("brain_acceptance_role_templates_rung") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_AT_SHADOW)


@pytest.mark.needs_db
def test_a_role_template_that_is_incomplete_with_its_sources_serving_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connectors never serving in the finished install, so the badge is incomplete even
    with everything a template needs. Delete this and the step that proves a template could
    answer once connected is a step that can be skipped without a test noticing."""
    import brain.ops.acceptance_checks_role_templates as module
    from brain.connectors.registry import ConnectorRegistry
    from brain.ops.acceptance_checks_role_templates import NOT_COMPLETE_WITH_ITS_CONNECTORS

    monkeypatch.setattr(module, "_serving", lambda names, at: ConnectorRegistry())
    with at_head("brain_acceptance_role_templates_serving") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_COMPLETE_WITH_ITS_CONNECTORS)


@pytest.mark.needs_db
def test_a_role_template_declaring_a_connector_nobody_ships_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SEO agent naming a console that is not a connector, on file exactly as shipped. Delete
    this and a mistyped connector makes an agent that waits for a binding nobody can make."""
    from brain.ops.acceptance_checks_role_templates import NOT_A_CONNECTOR_OF_THIS_RELEASE

    changed = _broken(monkeypatch, "seo_agent", connectors=("google_analytics", "search_consol"))
    with at_head("brain_acceptance_role_templates_connector") as url:
        signed_onto(url, changed)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_A_CONNECTOR_OF_THIS_RELEASE)


@pytest.mark.needs_db
def test_a_role_template_pinning_a_skill_nothing_furnishes_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The support agent pinning ticket analysis at a digest the starter pack no longer holds.
    Delete this and a reworded starter skill leaves agents pinned to a skill the install does not
    have, learned at the first question."""
    from brain.agents.template import SkillRef
    from brain.ops.acceptance_checks_role_templates import NOT_THE_SKILL_FURNISHED

    changed = _broken(
        monkeypatch,
        "support_ticket_agent",
        skills=(SkillRef(name="ticket-analysis", digest="0" * 64),),
    )
    with at_head("brain_acceptance_role_templates_skill") as url:
        signed_onto(url, changed)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_THE_SKILL_FURNISHED)


@pytest.mark.needs_db
def test_a_role_template_declaring_a_tool_nothing_binds_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finance agent asking for a search no source registers, which is exactly what its
    version 2 did. Delete this and a role template can install disabled for ever, on every
    install, because a declared tool binds to nothing."""
    from brain.agents.catalogue import catalogue_by_id
    from brain.ops.acceptance_checks_role_templates import A_TOOL_BINDS_NOTHING

    held = catalogue_by_id()["accountant_agent"]
    tools = (*held.authority.allowed_tools, "xero_invoice.search")
    changed = _broken(
        monkeypatch,
        "accountant_agent",
        authority=held.authority.model_copy(update={"allowed_tools": tools}),
        guardrails=held.guardrails.model_copy(
            update={
                "leash": (
                    *held.guardrails.leash,
                    held.guardrails.leash[0].model_copy(update={"target": "xero_invoice.search"}),
                )
            }
        ),
    )
    with at_head("brain_acceptance_role_templates_tool") as url:
        signed_onto(url, changed)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, A_TOOL_BINDS_NOTHING)


@pytest.mark.needs_db
def test_an_install_that_leaves_the_role_agent_enabled_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path writing the new agent enabled rather than disabled. Delete this and a
    role agent could start answering the moment it is installed, before its sources are
    connected."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_role_templates import NOT_AT_SHADOW

    kept = install_store.agent_values

    def enabled(record: Any) -> dict[str, Any]:
        return {**kept(record), "disabled_at": None}

    monkeypatch.setattr(install_store, "agent_values", enabled)
    with at_head("brain_acceptance_role_templates_enabled") as url:
        signed_onto(url)
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, NOT_AT_SHADOW)
    assert after == before


@pytest.mark.needs_db
def test_an_install_that_drops_the_connectors_a_role_template_declares_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path writing the new agent with no connectors named. Delete this and an agent
    can be installed that never reads the sources its template is written around, and reads the
    knowledge library alone."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_role_templates import NOT_ITS_CONNECTORS

    kept = install_store.agent_values

    def unbound(record: Any) -> dict[str, Any]:
        return {**kept(record), "connectors": []}

    monkeypatch.setattr(install_store, "agent_values", unbound)
    with at_head("brain_acceptance_role_templates_unbound") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_ITS_CONNECTORS)


@pytest.mark.needs_db
def test_an_install_that_drops_the_skills_a_role_template_pins_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install path writing the instance with no skills in its effective document. Delete
    this and an agent can be installed without the skills its role is asked through, and nothing
    on the install says so."""
    import brain.agents.install_store as install_store
    from brain.ops.acceptance_checks_role_templates import NOT_ITS_SKILLS

    kept = install_store.instance_values

    def skilless(installation: Any) -> dict[str, Any]:
        values = kept(installation)
        return {**values, "effective_document": {**values["effective_document"], "skills": []}}

    monkeypatch.setattr(install_store, "instance_values", skilless)
    with at_head("brain_acceptance_role_templates_skilless") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_ITS_SKILLS)


@pytest.mark.needs_db
def test_a_gate_that_starts_no_run_through_a_role_agent_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rehearsal reporting that no run started for a holder of the whole ceiling. Delete this
    and a role template can be complete on paper and refused by the gate at its first question."""
    from types import SimpleNamespace

    import brain.agents.install as install
    from brain.ops.acceptance_checks_role_templates import NOT_STARTED

    def refused(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return SimpleNamespace(started=False)

    monkeypatch.setattr(install, "rehearse", refused)
    with at_head("brain_acceptance_role_templates_gate") as url:
        signed_onto(url)
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, NOT_STARTED)
