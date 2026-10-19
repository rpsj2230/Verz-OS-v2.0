"""The personal agent checks: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs both checks as the worker would. Then each is
run against the product broken where it proves: oversight told to a reader whose audit reach does
not cover the agent, an overseen agent on the auditor's roster, a switch that is ignored, an account
attached by somebody who is not the owner, a department's agent given an account or reading one, and
a personal agent that reads before anything is attached.

Task ids: M39.10.3, M39.10.4
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_personal_agents"
OVERSIGHT = "an_auditor_is_told_of_a_personal_agent_and_may_not_use_it"
OWN_ACCOUNT = "a_persons_own_google_account_is_on_their_agent_for_them_alone"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

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


def test_the_personal_agent_checks_are_listed_with_the_leaves_they_prove() -> None:
    """Delete this and a check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [OVERSIGHT, OWN_ACCOUNT]
    assert MODULE in check_modules()
    assert mine()[OVERSIGHT].leaves == ("M39.10.3",)
    assert mine()[OWN_ACCOUNT].leaves == ("M39.10.4",)


@pytest.mark.needs_db
def test_on_a_real_database_oversight_and_the_owners_account_hold_and_nothing_is_left() -> None:
    """**Both checks as the worker runs them.** Delete this and an auditor's oversight, a person's
    own account on their agent and every refusal between them can stop working with nothing on an
    install saying so."""
    with at_head("brain_acceptance_personal_agents") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {OVERSIGHT: (PASSED, ""), OWN_ACCOUNT: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_the_own_account_check_steps_aside_where_the_install_has_workspace_connected() -> None:
    """The check stands a made-up Workspace up, so on an install with a real one it does not, and
    says why in the one sentence. Delete this and it could disturb the owner's own connection, or a
    skipped check could read as a passed one.

    The sentence also says what it cannot prove: a real person's sign-in at Google."""
    import brain.ops.acceptance_checks_personal_agents as module
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_personal_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('google_workspace', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[OWN_ACCOUNT],))
    assert outcome[OWN_ACCOUNT] == (NOT_RUN, module.NOT_RUN_WITH_A_REAL_WORKSPACE)


def _may_audit_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agents.oversight as oversight

    monkeypatch.setattr(oversight, "may_audit", lambda *_args, **_kwargs: True)


def _the_roster_lists_every_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_routes as routes

    monkeypatch.setattr(
        routes,
        "visible_agent_ids",
        lambda records, _viewer: frozenset(one.agent_id for one in records),
    )


def _the_oversight_switch_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_oversight_routes as routes

    async def always(_sessions: object) -> bool:
        return True

    monkeypatch.setattr(routes, "oversight_is_on", always)


def _anybody_attaches_to_any_personal_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_own_workspace_routes as routes

    monkeypatch.setattr(routes, "visible", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(routes, "owns", lambda *_args, **_kwargs: True)


def _a_team_agent_may_be_given_an_account(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_own_workspace_routes as routes

    monkeypatch.setattr(routes, "attach_refusal", lambda *_args, **_kwargs: None)


def _a_team_agent_keeps_the_connectors_that_read_one_persons_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import brain.agents.model as model

    monkeypatch.setattr(model, "bound_connectors", lambda record: record.authority.connectors)


def _a_personal_agent_carries_the_read_without_naming_the_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import brain.agents.model as model
    from brain.core.entitlement import Capability

    monkeypatch.setattr(
        model, "own_reads", lambda _record: (Capability(value="read:google_workspace"),)
    )


def _the_own_account_switch_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_own_workspace_routes as routes

    async def always(_sessions: object) -> bool:
        return True

    monkeypatch.setattr(routes, "own_workspace_is_on", always)


BREAKS: dict[str, tuple[Any, str, str]] = {
    "told_beyond_the_audit_reach": (_may_audit_everywhere, OVERSIGHT, "TOLD_TO_ANOTHER"),
    "overseen_on_the_roster": (_the_roster_lists_every_agent, OVERSIGHT, "OVERSEEN_IS_LISTED"),
    "oversight_switch_ignored": (
        _the_oversight_switch_is_ignored,
        OVERSIGHT,
        "OVERSIGHT_IGNORES_THE_SWITCH",
    ),
    "anybody_attaches": (
        _anybody_attaches_to_any_personal_agent,
        OWN_ACCOUNT,
        "ANOTHER_ATTACHED_IT",
    ),
    "team_agent_given_an_account": (
        _a_team_agent_may_be_given_an_account,
        OWN_ACCOUNT,
        "TEAM_AGENT_ATTACHED",
    ),
    "team_agent_reads": (
        _a_team_agent_keeps_the_connectors_that_read_one_persons_accounts,
        OWN_ACCOUNT,
        "TEAM_AGENT_READ",
    ),
    "read_without_attaching": (
        _a_personal_agent_carries_the_read_without_naming_the_connector,
        OWN_ACCOUNT,
        "READ_BEFORE_ATTACHING",
    ),
    "own_account_switch_ignored": (
        _the_own_account_switch_is_ignored,
        OWN_ACCOUNT,
        "SWITCH_IGNORED",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_personal_agent_checks_fail_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found, in its own words. Delete this and a check can
    pass over oversight told too widely, an account attached by a stranger, or a department's agent
    that reads one person's mail."""
    import brain.ops.acceptance_checks_personal_agents as module

    setup, which, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_personal_{broken}") as url:
        outcome = run_checks(url, (mine()[which],))
    assert outcome[which] == (FAILED, getattr(module, reason))
