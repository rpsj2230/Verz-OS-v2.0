"""The install checks for the governance surfaces' second half, passing on PostgreSQL at head and
failing where they should.

The pure half holds the module to its page order and its leaves. The database half runs each check
as the worker would: it passes and leaves nothing. Then each is shown failing with the product
broken the way the leaf it proves would plausibly break: a connector route open to anybody, a key
kept nowhere, a card re-rendered from the tool call, a lapsed approval still offered, an elevation
kept with another reason, a notice to the wrong person, and a grant read past its lapse.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M33.5.1.1, M33.5.1.2, M33.6.1.2, M33.6.1.4, M33.7.1.2, M33.7.1.4, M33.7.1.5
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, check_modules, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_governance import run_named

MODULE = "brain.ops.acceptance_checks_governance_2"

CONNECTS = "a_connector_admin_installs_and_configures_a_connector"
ROTATES = "a_connector_admin_binds_and_rotates_a_key_reference"
ARTEFACT = "an_approver_reads_the_request_at_their_own_reach"
LAPSES = "an_approver_sees_when_each_approval_lapses_and_a_lapsed_one_goes"
ELEVATED = "a_partner_is_elevated_for_a_stated_reason_and_a_bounded_time"
TOLD = "every_elevation_is_told_to_the_standing_super_admins"
ENDS = "an_elevation_lapses_by_itself_and_can_be_revoked_before_it_does"

#: Each check and the one leaf it proves.
LEAVES = {
    CONNECTS: ("M33.5.1.1",),
    ROTATES: ("M33.5.1.2",),
    ARTEFACT: ("M33.6.1.2",),
    LAPSES: ("M33.6.1.4",),
    ELEVATED: ("M33.7.1.2",),
    TOLD: ("M33.7.1.4",),
    ENDS: ("M33.7.1.5",),
}


# ------------------------------------------------------------------------ the figures
def test_the_second_governance_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, and the module
    is one the suite finds. Delete this and a check can drop out of the module, or the module out
    of the suite, with the page simply listing fewer rows."""
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


def test_each_second_half_check_claims_the_one_leaf_its_walk_proves() -> None:
    """Delete this and a check can be moved onto a leaf it does not walk, and that leaf closes on
    somebody else's evidence."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == LEAVES


def test_the_approval_windows_lapse_in_another_order_than_they_are_raised() -> None:
    """The timeout check raises its three approvals in an order that is not the order they lapse
    in, so a queue in raised order cannot pass it. Delete this and the windows can be edited into
    ascending order, where a queue that ignores the lapse passes the check."""
    from brain.ops.acceptance_checks_governance_2 import WINDOWS

    assert list(WINDOWS) != sorted(WINDOWS)
    assert len(set(WINDOWS)) == len(WINDOWS)


def test_the_elevation_people_outlast_the_elevation_and_the_minute_after() -> None:
    """The partner and the authoriser last past the lapse and the minute after it, and the
    elevation is no longer than a partner's grant may be. Delete this and the people can be
    shortened until an authoriser may not grant the hour, or the minute after the lapse is
    judged on a person whose own end came first."""
    from brain.ops.acceptance_checks_governance_2 import EITHER_SIDE, ELEVATION_HOURS, OUTLASTS
    from brain.ops.acceptance_run import RESERVED_REACH_LASTS

    assert RESERVED_REACH_LASTS + timedelta(hours=ELEVATION_HOURS) + EITHER_SIDE < OUTLASTS
    assert timedelta(hours=ELEVATION_HOURS) <= timedelta(hours=4)


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_governance_2") as url:
        yield url


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def _run(url: str, *names: str) -> dict[str, tuple[str, str]]:
    return run_named(url, *names, module=MODULE)


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = _run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_second_half_check_passes_on_an_install_and_leaves_nothing(
    install: str, configured: None
) -> None:
    """**The checks as the worker runs them.** Each passes, and nothing any of them wrote is left:
    the connections and their credential writes, the suspensions, the elevation requests, their
    grants and notices, and the role rows. Delete this and a check that can never pass on a real
    schema, or one that commits a connection, reaches the owner's server first."""
    before = counts(install)
    assert _run(install) == dict.fromkeys(LEAVES, (PASSED, ""))
    assert counts(install) == before


# ------------------------------------------------- each leaf, failing where it should
@pytest.mark.needs_db
def test_a_connector_route_open_to_anybody_fails_the_install_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`may_connect_source` answering yes for everybody. Delete this and M33.5.1.1 closes with any
    member able to connect a source to the company's data."""
    from brain import connector_routes

    monkeypatch.setattr(connector_routes, "may_connect_source", lambda *args, **kw: True)
    assert "member without the connector authority connected" in _failed(install, CONNECTS)


@pytest.mark.needs_db
def test_a_key_kept_nowhere_fails_the_rotation_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route's keeper answering as though it kept a key it did not. Delete this and M33.5.1.2
    closes on a connection bound to a slot holding nothing."""
    from brain import connector_routes

    async def nowhere(*args: Any, **kw: Any) -> Any:
        return SimpleNamespace(set_at=None)

    monkeypatch.setattr(connector_routes, "keep_credential", nowhere)
    assert "key was not kept in its source's slot" in _failed(install, ROTATES)


def _card_saying(monkeypatch: pytest.MonkeyPatch, words: Any) -> None:
    """Every approval card's request replaced by `words(suspension)`, minted as the product's own
    terms are, so the break is a wrong text and never a refused construction."""
    from dataclasses import replace

    from brain import approval_routes
    from brain.gate.approval_request import render_terms

    real = approval_routes.shown_card

    def saying(suspension: Any, reach: Any, *args: Any, **kw: Any) -> Any:
        shown = real(suspension, reach, *args, **kw)
        if shown is None:
            return None
        return replace(shown, request=render_terms(words(suspension), reach))

    monkeypatch.setattr(approval_routes, "shown_card", saying)


@pytest.mark.needs_db
def test_a_card_carrying_the_tool_call_fails_the_request_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card whose words are the tool, its capability and its arguments. Delete this and
    M33.6.1.2 closes with an approver deciding on how rather than what."""

    def the_call(suspension: Any) -> str:
        tool = suspension.action.tool
        return f"{tool.name} {tool.required_capability} {suspension.action.args}"

    _card_saying(monkeypatch, the_call)
    from brain.ops import acceptance_checks_governance_2 as module

    assert _failed(install, ARTEFACT) == module.SHOWN_THE_TOOL_CALL


@pytest.mark.needs_db
def test_a_card_showing_the_requesters_artefact_fails_the_request_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The leak #381 closed.** A card carrying the requester's artefact, which names the value
    the approver may not read. Delete this and the check can pass with the requester's words on
    the approver's card again."""
    _card_saying(monkeypatch, lambda suspension: suspension.artefact)
    from brain.ops import acceptance_checks_governance_2 as module

    assert _failed(install, ARTEFACT) == module.SHOWN_A_LOCKED_FIELD


@pytest.mark.needs_db
def test_a_card_rendered_at_another_reach_fails_the_request_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card drawn by the one render but not at the approver's reach: the lock is where it should
    be and the words still differ. Delete this and the check passes a card rendered for anybody."""
    _card_saying(
        monkeypatch, lambda suspension: f"{suspension.action.tool.name}\n  status: Restricted"
    )
    from brain.ops import acceptance_checks_governance_2 as module

    assert _failed(install, ARTEFACT) == module.NOT_THE_ONE_RENDER


@pytest.mark.needs_db
def test_a_lapsed_approval_still_offered_fails_the_timeout_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The approver's queue judged as though nothing ever lapsed. Delete this and M33.6.1.4
    closes with an approval somebody can still act on hours after it expired."""
    from brain.console import approvals, role_surfaces

    real = role_surfaces.pending_for

    def forever(entitlement: Any, suspensions: Any, now: datetime) -> Any:
        return real(entitlement, suspensions, now - timedelta(days=1))

    monkeypatch.setattr(approvals, "pending_for", forever)
    assert "soonest first" in _failed(install, LAPSES)


@pytest.mark.needs_db
def test_an_elevation_kept_with_another_reason_fails_the_elevation_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request kept with a reason other than the one stated. Delete this and M33.7.1.2 closes
    with an elevation whose recorded reason nobody gave."""
    from brain import govern_people_routes
    from brain.identity.roles import BreakGlassReason

    real = govern_people_routes.elevation_records_of

    def another_reason(request: Any) -> Any:
        store = real(request)
        filing = store.file

        async def file(**kw: Any) -> Any:
            return await filing(**{**kw, "reason": BreakGlassReason.LOCKOUT.value})

        # A method replaced on this one store, which is the breakage under test.
        setattr(store, "file", file)  # noqa: B010
        return store

    monkeypatch.setattr(govern_people_routes, "elevation_records_of", another_reason)
    assert "did not carry the reason it was asked for" in _failed(install, ELEVATED)


@pytest.mark.needs_db
def test_a_notice_sent_to_the_authoriser_fails_the_notification_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The company told through whoever allowed the elevation rather than its Super Admins.
    Delete this and M33.7.1.4 closes with an elevation the company never hears of."""
    from brain import govern_people_routes

    def the_authoriser(role_grants: Any, *, subject_id: str, authorised_by: str, now: Any) -> Any:
        return (authorised_by,)

    monkeypatch.setattr(govern_people_routes, "client_recipients", the_authoriser)
    assert "did not say the Super Admin was told" in _failed(install, TOLD)


@pytest.mark.needs_db
def test_a_grant_read_past_its_lapse_fails_the_expiry_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resolver asked a few minutes behind the instant it is given, so a lapse arrives late.
    Delete this and M33.7.1.5 closes on an elevation that outlives the hour it was given."""
    from brain.gate import entitlement_store

    real = entitlement_store.StoredEntitlements.load

    async def late(self: Any, principal_id: str, now: Any) -> Any:
        return await real(self, principal_id, now - timedelta(minutes=3))

    monkeypatch.setattr(entitlement_store.StoredEntitlements, "load", late)
    assert "still held after its lapse" in _failed(install, ENDS)
