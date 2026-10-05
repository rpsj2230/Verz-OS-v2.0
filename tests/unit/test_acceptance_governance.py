"""The install checks for the governance surfaces, passing on PostgreSQL at head and failing where
they should.

The pure half holds the module to its page order and its leaves. The database half runs each check
as the worker would: it passes and leaves nothing. Then each is shown failing with the product
broken the way the leaf it proves would plausibly break: a route deciding for the wrong reader, a
refusal that lets everybody through, or a write that records nothing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M33.1.2.4, M33.2.2.2, M33.2.2.5, M33.2.2.3, M33.2.1.1, M33.2.2.1, M33.1.2.2, M33.4.1.1
Task ids: M33.3.1.1, M33.3.1.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_governance"

DISABLE = "a_super_admin_disables_a_person_and_nobody_else_may"
GRANT = "a_department_admin_grants_within_their_department_only"
DEPUTY = "a_department_admin_appoints_a_deputy_for_thirty_days_at_most"
ADOPT = "a_department_admin_adopts_an_agent_whose_owner_left"
NARROWED = "a_department_admin_sees_the_super_admin_view_of_their_department"
DEPARTMENT_APPROVES = "a_department_admin_approves_their_departments_publication"
SUPER_APPROVES = "a_super_admin_approves_a_departments_publication_request"
AUDIT = "an_auditor_reads_the_super_admins_own_acts"
OWN_AGENTS = "a_member_sees_their_own_agents_and_not_anybody_elses"
OWN_KNOWLEDGE = "a_member_sees_the_knowledge_they_added_and_nobody_elses"

#: Each check and the one leaf it proves.
LEAVES = {
    DISABLE: ("M33.1.2.4",),
    GRANT: ("M33.2.2.2",),
    DEPUTY: ("M33.2.2.5",),
    ADOPT: ("M33.2.2.3",),
    NARROWED: ("M33.2.1.1",),
    DEPARTMENT_APPROVES: ("M33.2.2.1",),
    SUPER_APPROVES: ("M33.1.2.2",),
    AUDIT: ("M33.4.1.1",),
    OWN_AGENTS: ("M33.3.1.1",),
    OWN_KNOWLEDGE: ("M33.3.1.2",),
}


# ------------------------------------------------------------------------ the figures
def test_the_governance_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, and the module
    is one the suite finds. Delete this and a check can drop out of the module, or the module out
    of the suite, with the page simply listing fewer rows."""
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


def test_each_check_claims_the_one_leaf_its_walk_proves() -> None:
    """Delete this and a check can be moved onto a leaf it does not walk, and that leaf closes on
    somebody else's evidence."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == LEAVES


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_governance") as url:
        yield url


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_named(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=[one for one in registered((MODULE,)) if not names or one.name in names],
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_named(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_governance_check_passes_on_an_install_and_leaves_nothing(
    install: str, configured: None
) -> None:
    """**The checks as the worker runs them.** Each passes, and nothing any of them wrote is left:
    the grants, the role rows, the drafts and agents, the documents and the disabled person. Delete
    this and a check that can never pass on a real schema, or one that commits a grant, reaches the
    owner's server first."""
    before = counts(install)
    assert run_named(install) == dict.fromkeys(LEAVES, (PASSED, ""))
    assert counts(install) == before


# ------------------------------------------------- each leaf, failing where it should
@pytest.mark.needs_db
def test_a_disable_decided_for_anybody_fails_the_disable_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`may_disable` answering yes for every row. Delete this and M33.1.2.4 closes with any
    department's admin able to switch off anybody in the company."""
    from brain import principal_state_routes

    monkeypatch.setattr(principal_state_routes, "may_disable", lambda *args, **kw: True)
    assert "another department disabled" in _failed(install, DISABLE)


@pytest.mark.needs_db
def test_a_grant_written_without_its_authority_fails_the_grant_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_grant` handing back whatever was proposed. Delete this and M33.2.2.2 closes with a
    department admin granting over somebody else's department."""
    from brain import govern_routes

    monkeypatch.setattr(govern_routes, "write_grant", lambda proposed, *args, **kw: proposed)
    assert "over another department" in _failed(install, GRANT)


@pytest.mark.needs_db
def test_a_deputy_appointed_outside_the_admins_scope_fails_the_deputy_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`appoint` without its scope question. Delete this and M33.2.2.5 closes with any admin able
    to put a deputy in front of another department's approvals."""
    from brain import govern_role_routes
    from brain.identity.roles import appoint_deputy

    def anywhere(standing: Any, admin: Any, deputy: str, **kw: Any) -> Any:
        return appoint_deputy(standing, deputy, **kw)

    monkeypatch.setattr(govern_role_routes, "appoint", anywhere)
    assert "deputised for an approver here" in _failed(install, DEPUTY)


@pytest.mark.needs_db
def test_a_leavers_agent_offered_to_everybody_fails_the_adoption_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`transfers_for` ignoring the reader. Delete this and M33.2.2.3 closes with a leaver's agent
    handed to an admin whose reach it does not fit."""
    from brain import staff_source_routes
    from brain.agents.lifecycle import agents_needing_transfer

    def everybody(records: Any, *, leavers: Any, reader: Any, now: Any = None) -> Any:
        by_id = {one.agent_id: one for one in records}
        return tuple(by_id[one] for one in agents_needing_transfer(records, departing=leavers))

    monkeypatch.setattr(staff_source_routes, "transfers_for", everybody)
    assert "listed to another department's admin" in _failed(install, ADOPT)


@pytest.mark.needs_db
def test_role_holders_shown_unnarrowed_fail_the_narrowed_view_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`role_holders` returning every holder. Delete this and M33.2.1.1 closes with a department
    admin's view that is the Super Admin's, unnarrowed."""
    from brain import govern_role_routes

    monkeypatch.setattr(govern_role_routes, "role_holders", lambda placed, *args, **kw: placed)
    assert "listed another department" in _failed(install, NARROWED)


@pytest.mark.needs_db
def test_a_publication_approvable_by_anybody_fails_the_department_approval_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`approval_refusal` refusing nobody. Delete this and M33.2.2.1 closes with a publication
    approved by a builder whose own access does not cover what the agent reads."""
    from brain import agent_builder_routes

    monkeypatch.setattr(agent_builder_routes, "approval_refusal", lambda **kw: None)
    assert "cannot read what an agent reads" in _failed(install, DEPARTMENT_APPROVES)


@pytest.mark.needs_db
def test_a_waiting_list_that_offers_nothing_fails_the_super_admin_approval_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's waiting publications read as none. Delete this and M33.1.2.2 closes on a
    request no Super Admin is ever shown."""
    from brain.builder import draft_store

    async def none(self: Any) -> tuple[Any, ...]:
        return ()

    monkeypatch.setattr(draft_store.StoredAgentDrafts, "waiting", none)
    assert "not on their list" in _failed(install, SUPER_APPROVES)


@pytest.mark.needs_db
def test_an_audit_screen_open_to_anybody_fails_the_audit_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audit screen's question answering yes for everybody. Delete this and M33.4.1.1 closes
    with the whole ledger readable by any member."""
    from brain import audit_routes

    monkeypatch.setattr(audit_routes, "permitted", lambda *args, **kw: True)
    assert "member without the audit screen" in _failed(install, AUDIT)


@pytest.mark.needs_db
def test_an_audit_trail_that_hides_an_administrators_acts_fails_the_audit_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ledger's page read with every entry dropped. Delete this and M33.4.1.1 closes on an
    audit trail with the Super Admin's acts missing from it."""
    from brain import audit_routes

    real = audit_routes.read_page

    async def hiding(*args: Any, **kw: Any) -> Any:
        return (await real(*args, **kw)).model_copy(update={"rows": ()})

    monkeypatch.setattr(audit_routes, "read_page", hiding)
    assert "did not read the Super Admin's own acts" in _failed(install, AUDIT)


@pytest.mark.needs_db
def test_a_workspace_listing_every_agent_fails_the_own_agents_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every enabled agent counted as one this person can call. Delete this and M33.3.1.1 closes
    with a member's workspace listing a colleague's own agent."""
    from brain import member_activity

    monkeypatch.setattr(
        member_activity,
        "runnable_agent_ids",
        lambda records, viewer: frozenset(one.agent_id for one in records if one.is_selectable),
    )
    assert "somebody else's own agent" in _failed(install, OWN_AGENTS)


@pytest.mark.needs_db
def test_a_workspace_that_owns_nothing_fails_the_own_knowledge_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every stewarded row read as somebody else's. Delete this and M33.3.1.2 closes on a
    workspace that never shows a member what they added."""
    from brain import mine_routes

    monkeypatch.setattr(mine_routes, "is_own", lambda *args: False)
    assert "did not list what they added" in _failed(install, OWN_KNOWLEDGE)
