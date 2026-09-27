"""What a first administrator can open, and what a start grants one appointed before it existed.

The first half needs no database: the reads are held to `brain.console.screens` and
`brain.audit.view`, and every screen is opened, or refused, for a reach built from exactly what an
appointment writes. The decision about what to grant is a pure function and is tested there. The
second half runs the write against a scratch PostgreSQL and is skipped on a machine without one.

Task ids: M41.2.4, M42.5.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.ledger import SUBJECT_KINDS
from brain.audit.view import AUDIT_NOUN, CAPABILITY_BY_KIND
from brain.classification_routes import CLASSIFICATION_READ
from brain.console.reads import CONSOLE_CAPABILITY_PREFIX, Plane, permitted, plane_capability
from brain.console.screens import SCREENS, Screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.firstrun import GRANTED_BY
from brain.identity.administration_reconciliation import (
    RECONCILED_REASON,
    Reconciled,
    reconcile_first_administrators,
    to_grant,
)
from brain.identity.first_administrator import (
    ADMINISTRATION,
    AUDIT_KINDS_WITHHELD,
    GOVERNANCE,
    GRANTED_AT_APPOINTMENT,
    OVERSIGHT,
    SIGN_IN_AUTHORITY,
)
from brain.routing_routes import MATRIX_READ

#: Far from any wall clock, for the reason `tests/unit/test_scope_and_capability.py` gives.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

FINANCE = Scope.department("finance")

#: The reads of the two console pages no screen registers, taken from the routes that ask for them.
PAGE_READS = (CLASSIFICATION_READ.value, MATRIX_READ.value)

#: What an appointment granted before those two reads were added on 2026-09-17.
APPOINTED_BEFORE_THE_PAGE_READS = tuple(
    one for one in GRANTED_AT_APPOINTMENT if one not in PAGE_READS
)


def reach(*capabilities: str, scope: Scope | None = None, principal: str = "u_first") -> Any:
    """A principal holding these capabilities, all at one scope, everything by default."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope or Scope.unrestricted())
            for one in capabilities
        ),
    )


def administrative(screen: Screen) -> bool:
    """The line `OVERSIGHT` and `GOVERNANCE` draw, restated from the console's side."""
    capability = screen.read.requires.value
    verb = capability.split(":", 1)[0]
    held = verb in {"read", "admin"} or capability == "approve:grant"
    return held and screen.read.plane < Plane.CONTENT


# ================================================================= what the administrator reads
def test_every_administrative_screen_opens_for_a_fresh_first_administrator() -> None:
    """The defect, as the positive case, and the refusals beside it. A first administrator held
    every `admin:` capability and no screen's own read and no plane, so thirty-two screens
    refused the only administrator an install had. Delete this and the reads can go missing
    again, or grow to cover a content screen, and nothing notices either."""
    fresh = reach(*GRANTED_AT_APPOINTMENT)
    opened = {one.key for one in SCREENS if permitted(one.read, fresh, NOW)}

    assert opened == {one.key for one in SCREENS if administrative(one)}
    assert {"sessions", "audit", "halt", "recovery", "access_review"} <= opened
    assert "approvals" not in opened
    # Not vacuous: there are screens this line refuses, and they are refused.
    refused = {one.key for one in SCREENS if not administrative(one)}
    assert refused
    assert not refused & opened


def test_oversight_is_screen_reads_below_content_both_planes_the_audit_kinds_and_two_pages() -> (
    None
):
    """`OVERSIGHT` is written out because the identity package must not import the console, so
    this is what keeps it the console's line. The fourth part is the reads of the Routing and
    Classification pages, taken from their routes and held to be outside the registry, because a
    line drawn from the registry alone is how both refused every first administrator until
    2026-09-17. Delete this and a screen added next week is one no first administrator can open,
    a content screen's capability can be added by hand, or either page read can be dropped
    again."""
    screen_reads = {
        one.read.requires.value
        for one in SCREENS
        if administrative(one) and one.read.requires.value.startswith("read:")
    }
    planes = {plane_capability(one).value for one in Plane if one < Plane.CONTENT}
    kinds = {
        CAPABILITY_BY_KIND[one].value for one in SUBJECT_KINDS if one not in AUDIT_KINDS_WITHHELD
    }
    pages = set(PAGE_READS)

    assert not pages & {one.read.requires.value for one in SCREENS}
    assert set(OVERSIGHT) == screen_reads | planes | kinds | pages
    assert len(set(OVERSIGHT)) == len(OVERSIGHT)
    assert f"read:{AUDIT_NOUN}" in OVERSIGHT


def test_a_fresh_first_administrator_is_answered_the_routing_matrix_and_a_classification() -> None:
    """See `TWO_PAGES_OUTSIDE_THE_REGISTRY_READ_HOW_THE_SYSTEM_IS_SET_UP`. Both routes, served by
    the real application to a reach built from exactly what an appointment writes, answer 200; the
    same reach less the two page reads, which is every administrator appointed before 2026-09-17,
    is refused in the one sentence, which is the defect as it was measured on origin/main. Delete
    this and the two pages can go back to refusing the only administrator an install has, with the
    registry's own test still green because neither page is in the registry."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from brain.api import API_PREFIX
    from brain.app import Settings, create_app
    from brain.core.errors import Absent
    from brain.knowledge.columns import PRICE_LIST
    from tests.unit.test_routing_routes import StubSession
    from tests.unit.test_webhook_routes import headers, wiring

    def grants(capabilities: tuple[str, ...]) -> tuple[Grant, ...]:
        return tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        )

    app = create_app(Settings(env="development"))
    paths = (f"{API_PREFIX}/routing/rungs", f"{API_PREFIX}/classifications/{PRICE_LIST.entity}")
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wiring(
            {
                "u_admin": grants(GRANTED_AT_APPOINTMENT),
                "u_wide": grants(APPOINTED_BEFORE_THE_PAGE_READS),
            }
        )
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        fresh = [client.get(path, headers=headers("u_admin")) for path in paths]
        before = [client.get(path, headers=headers("u_wide")) for path in paths]

    assert [one.status_code for one in fresh] == [200, 200]
    assert "items" in fresh[0].json()
    assert fresh[1].json()["entity"] == PRICE_LIST.entity
    assert [one.status_code for one in before] == [404, 404]
    assert {one.json()["message"] for one in before} == {Absent.public_message}


def test_every_audit_kind_is_decided_and_the_ones_naming_business_records_are_withheld() -> None:
    """See `AN_ADMINISTRATOR_READS_HOW_THE_SYSTEM_IS_RUN_AND_NO_DATA`. Delete this and a kind added
    to the ledger is granted to every first administrator by default, and the two that name a
    business record or an artefact can be granted by a tidy-up nobody argued. `memory` joined them
    on 2026-09-17: a correction names a memory, and whether one exists is recall's to disclose."""
    assert set(AUDIT_KINDS_WITHHELD) <= SUBJECT_KINDS
    assert {"entity", "artifact", "memory"} == set(AUDIT_KINDS_WITHHELD)
    assert all(reason.strip() for reason in AUDIT_KINDS_WITHHELD.values())
    for kind in AUDIT_KINDS_WITHHELD:
        assert CAPABILITY_BY_KIND[kind].value not in OVERSIGHT


def test_the_first_administrator_holds_no_content_plane_and_approves_no_action() -> None:
    """The half of the line that keeps the invariant. Delete this and `read:console.content`,
    `approve:action` or any other decision verb can be added to what an appointment writes, which
    is every conversation and every memory in the company, or an agent's act over data nobody
    appointed them to read, handed to whoever held a setup code for an hour."""
    assert plane_capability(Plane.CONTENT).value not in GRANTED_AT_APPOINTMENT
    assert "approve:action" not in GRANTED_AT_APPOINTMENT
    decisions = [
        one for one in GRANTED_AT_APPOINTMENT if one.split(":", 1)[0] not in {"read", "admin"}
    ]
    assert decisions == list(GOVERNANCE) == ["approve:grant"]
    assert not any(one.endswith(".*") for one in GRANTED_AT_APPOINTMENT)
    console = {one for one in OVERSIGHT if one.startswith(CONSOLE_CAPABILITY_PREFIX)}
    assert console == {
        plane_capability(Plane.EXISTENCE).value,
        plane_capability(Plane.CONFIGURATION).value,
    }


def test_an_appointment_grants_the_administration_the_governance_and_the_oversight_once() -> None:
    """Delete this and `GRANTED_AT_APPOINTMENT` can drift from its three parts, so an appointment
    writes one list and a start reconciles another."""
    assert (*ADMINISTRATION, *GOVERNANCE, *OVERSIGHT) == GRANTED_AT_APPOINTMENT
    assert len(set(GRANTED_AT_APPOINTMENT)) == len(GRANTED_AT_APPOINTMENT)


def test_a_first_administrator_can_write_a_grant_and_run_an_access_review() -> None:
    """See `THE_FIRST_ADMINISTRATOR_LETS_THE_SECOND_PERSON_IN`. The two controls behind
    `approve:grant`, asked of the modules that decide them rather than of the screen list. Delete
    this and the first administrator can open Access review and People and press nothing, which
    is an install on which nobody is ever granted anything from the console."""
    from brain.console.elevation import ELEVATION_CONTROL
    from brain.console.scoped_authority import REACH_AUTHORITY

    fresh = reach(*GRANTED_AT_APPOINTMENT)
    for control in (REACH_AUTHORITY, ELEVATION_CONTROL):
        scope = fresh.scope_for(control, NOW)
        assert scope is not None and scope.is_unrestricted()


# =========================================================================== the decision
def test_a_first_administrator_is_granted_what_was_added_after_the_appointment() -> None:
    """The positive case. Delete this and `to_grant` can return nothing for everybody, and every
    refusal below passes."""
    held = reach(SIGN_IN_AUTHORITY.value, "admin:halt")
    wanted = (SIGN_IN_AUTHORITY.value, "admin:halt", "admin:session", "read:session")

    granted = to_grant(
        wanted, reach=held, live=True, ever_granted={SIGN_IN_AUTHORITY.value}, now=NOW
    )

    assert granted == ("admin:session", "read:session")


def test_a_capability_first_run_granted_before_is_not_given_back() -> None:
    """See `A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START`. `admin:halt` was granted
    at the appointment and has since been retired, so the reach no longer holds it. Delete this
    and every revocation of a first administrator's capability is undone at the next restart."""
    held = reach(SIGN_IN_AUTHORITY.value)
    ever = {SIGN_IN_AUTHORITY.value, "admin:halt"}

    granted = to_grant(
        (SIGN_IN_AUTHORITY.value, "admin:halt", "admin:session"),
        reach=held,
        live=True,
        ever_granted=ever,
        now=NOW,
    )

    assert granted == ("admin:session",)


def test_a_capability_held_at_any_scope_or_through_a_wildcard_is_left_alone() -> None:
    """See `A_HELD_CAPABILITY_IS_NOT_GRANTED_AGAIN`. Delete this and a capability a department
    grant or a wildcard already covers is written again, which the table refuses on the direct
    row and which could only narrow what a pack or a wildcard gives."""
    held = EntitlementSet(
        principal_id="u_first",
        grants=(
            Grant(capability=SIGN_IN_AUTHORITY, scope=Scope.unrestricted()),
            Grant(capability=Capability(value="read:audit"), scope=FINANCE),
            Grant(capability=Capability(value="read:audit.*"), scope=Scope.unrestricted()),
        ),
    )

    granted = to_grant(
        ("read:audit", "read:audit.principal", "read:session"),
        reach=held,
        live=True,
        ever_granted=(),
        now=NOW,
    )

    assert granted == ("read:session",)


@pytest.mark.parametrize(
    ("held", "live"),
    [
        (reach(SIGN_IN_AUTHORITY.value), False),
        (reach(SIGN_IN_AUTHORITY.value, scope=FINANCE), True),
        (reach("admin:halt"), True),
    ],
    ids=["not live", "sign-in over one department", "no sign-in authority"],
)
def test_nobody_but_a_live_administrator_over_everything_is_granted_anything(
    held: EntitlementSet, *, live: bool
) -> None:
    """The finishing screen's own test. Delete this and a disabled first administrator, or a
    department's sign-in steward, is handed every administration capability over the company at
    the next start."""
    assert to_grant(("admin:session",), reach=held, live=live, ever_granted=(), now=NOW) == ()


def test_an_administrator_appointed_before_the_page_reads_gets_both_and_not_a_retired_one() -> None:
    """The release that added the Routing and Classification reads, as the decision sees it. An
    administrator holding everything an earlier appointment wrote, all of it recorded as granted by
    first run, is granted exactly the two page reads; one who was since granted and then had the
    matrix read retired is granted the classification read only. Delete this and the two reads can
    fall out of what a start grants an existing install, which leaves both pages refusing its
    administrator until somebody appoints a new one, or a retired page read comes back."""
    before = reach(*APPOINTED_BEFORE_THE_PAGE_READS)

    arrived = to_grant(
        GRANTED_AT_APPOINTMENT,
        reach=before,
        live=True,
        ever_granted=APPOINTED_BEFORE_THE_PAGE_READS,
        now=NOW,
    )
    after_retirement = to_grant(
        GRANTED_AT_APPOINTMENT,
        reach=before,
        live=True,
        ever_granted={*APPOINTED_BEFORE_THE_PAGE_READS, MATRIX_READ.value},
        now=NOW,
    )

    assert arrived == ("read:field_classification", "read:routing_matrix")
    assert after_retirement == ("read:field_classification",)


# ========================================================================== the database
FIRST = "u_first"
LATER = "read:a_capability_added_later"


def reconcile(url: str, *, wanted: tuple[str, ...], trace: str) -> tuple[Reconciled, ...]:
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> tuple[Reconciled, ...]:
        engine = app_engine(url)
        try:
            return await reconcile_first_administrators(
                make_session_factory(engine), now=NOW, trace_id=trace, wanted=wanted
            )
        finally:
            await engine.dispose()

    return run(go)


def test_a_capability_added_after_the_appointment_is_granted_once_audited_and_not_again() -> None:
    """The write, end to end: appointed with everything that existed, then a start that knows one
    capability more grants exactly that one, over everything, from first run with a reason of its
    own, and the grant trigger records it under this start's trace. A second start grants nothing.
    Delete this and the write can grant under another author, narrower, unaudited, or on every
    start."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_first_administrator import appoint, audited

    with audited("brain_fa_reconciled") as url:
        assert appoint(url) == "appointed"
        wanted = (*GRANTED_AT_APPOINTMENT, LATER)
        first = reconcile(url, wanted=wanted, trace="startup.reconcile.first")
        second = reconcile(url, wanted=wanted, trace="startup.reconcile.second")
        rows = sql(
            url,
            "SELECT scope, granted_by, reason FROM gate.capability_grant"
            " WHERE principal_id = %s AND capability = %s AND deleted_at IS NULL",
            FIRST,
            LATER,
        )
        entries = sql(
            url,
            "SELECT actor_id, trace_id FROM obs.audit_entry"
            " WHERE action = 'grant' AND details ->> 'capability' = %s",
            LATER,
        )
        total = sql(url, "SELECT count(*) FROM gate.capability_grant WHERE deleted_at IS NULL")

    assert first == (Reconciled(principal_id=FIRST, granted=(LATER,)),)
    assert second == ()
    [(scope, granted_by, reason)] = rows
    assert Scope.model_validate(scope).is_unrestricted()
    assert (granted_by, reason) == (GRANTED_BY, RECONCILED_REASON)
    assert entries == [(GRANTED_BY, "startup.reconcile.first")]
    assert total == [(len(GRANTED_AT_APPOINTMENT) + 1,)]


def test_a_capability_retired_from_the_first_administrator_stays_retired_after_a_start() -> None:
    """See `A_CAPABILITY_TAKEN_AWAY_IS_NOT_GIVEN_BACK_AT_THE_NEXT_START`, against the real policy
    that hides the retired row. Delete this and the ledger read can be dropped, and a revocation
    lasts until the next restart."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_first_administrator import appoint, audited

    with audited("brain_fa_revoked") as url:
        assert appoint(url) == "appointed"
        sql(
            url,
            "UPDATE gate.capability_grant SET deleted_at = now()"
            " WHERE principal_id = %s AND capability = 'admin:halt'",
            FIRST,
        )
        done = reconcile(url, wanted=GRANTED_AT_APPOINTMENT, trace="startup.reconcile.revoked")
        live = sql(
            url,
            "SELECT count(*) FROM gate.capability_grant"
            " WHERE capability = 'admin:halt' AND deleted_at IS NULL",
        )

    assert done == ()
    assert live == [(0,)]


def test_a_start_grants_an_earlier_administrator_the_page_reads_and_a_retired_one_stays_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The release that added the Routing and Classification reads, end to end. An administrator
    appointed while `OVERSIGHT` lacked them is reconciled by a start calling exactly as the lifespan
    calls, with no list of its own, and is granted both over everything by first run under that
    start's trace. The matrix read is then retired, and the next start grants nothing and leaves it
    retired, with the classification read still live. Delete this and the default a start
    reconciles against can stop carrying the page reads, which only this test exercises, or a
    retired page read can be written back at every restart."""
    from brain.identity import first_administrator
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_first_administrator import appoint, audited

    def start(url: str, trace: str) -> tuple[Reconciled, ...]:
        async def go() -> tuple[Reconciled, ...]:
            engine = app_engine(url)
            try:
                return await reconcile_first_administrators(
                    make_session_factory(engine), now=NOW, trace_id=trace
                )
            finally:
                await engine.dispose()

        return run(go)

    def live(url: str, capability: str) -> list[tuple[Any, ...]]:
        return sql(
            url,
            "SELECT scope, granted_by FROM gate.capability_grant"
            " WHERE principal_id = %s AND capability = %s AND deleted_at IS NULL",
            FIRST,
            capability,
        )

    earlier = tuple(one for one in OVERSIGHT if one not in PAGE_READS)
    with audited("brain_fa_page_reads") as url:
        with monkeypatch.context() as appointed_earlier:
            appointed_earlier.setattr(first_administrator, "OVERSIGHT", earlier)
            assert appoint(url) == "appointed"
        held_before = [live(url, one) for one in PAGE_READS]
        first = start(url, "startup.reconcile.pages")
        granted = {one: live(url, one) for one in PAGE_READS}
        entries = sql(
            url,
            "SELECT details ->> 'capability', actor_id, trace_id FROM obs.audit_entry"
            " WHERE action = 'grant' AND trace_id = 'startup.reconcile.pages'"
            " ORDER BY details ->> 'capability'",
        )
        sql(
            url,
            "UPDATE gate.capability_grant SET deleted_at = now()"
            " WHERE principal_id = %s AND capability = %s",
            FIRST,
            MATRIX_READ.value,
        )
        second = start(url, "startup.reconcile.after_retirement")
        retired = live(url, MATRIX_READ.value)
        kept = live(url, CLASSIFICATION_READ.value)

    assert held_before == [[], []]
    assert first == (
        Reconciled(
            principal_id=FIRST, granted=("read:field_classification", "read:routing_matrix")
        ),
    )
    for rows in granted.values():
        [(scope, granted_by)] = rows
        assert Scope.model_validate(scope).is_unrestricted()
        assert granted_by == GRANTED_BY
    assert entries == [
        ("read:field_classification", GRANTED_BY, "startup.reconcile.pages"),
        ("read:routing_matrix", GRANTED_BY, "startup.reconcile.pages"),
    ]
    assert second == ()
    assert retired == []
    assert len(kept) == 1


def test_an_administrator_made_by_hand_is_not_reconciled() -> None:
    """An administrator over everything who was not appointed by first run has the grants their
    maker chose. Delete this and a start adds every capability the product declares to anybody an
    operator made an administrator, which is a grant nobody wrote."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_grant, a_principal
    from tests.unit.test_first_administrator import audited

    with audited("brain_fa_by_hand") as url:
        a_principal(url, "u_by_hand")
        a_grant(url, "u_by_hand", SIGN_IN_AUTHORITY.value)
        done = reconcile(url, wanted=(SIGN_IN_AUTHORITY.value, LATER), trace="startup.reconcile.h")
        held = sql(
            url, "SELECT capability FROM gate.capability_grant WHERE principal_id = 'u_by_hand'"
        )

    assert done == ()
    assert held == [(SIGN_IN_AUTHORITY.value,)]


def test_a_head_already_holding_an_oversight_read_is_appointed_and_keeps_it_at_its_own_scope() -> (
    None
):
    """See `AN_OVERSIGHT_READ_ALREADY_HELD_IS_KEPT`. A principal the directory made a department
    head holds `read:audit` over their department before the wizard finishes. Delete this and the
    appointment can go back to refusing on the table's unique index, so a head who finished the
    wizard after the first sync can never be appointed."""
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_entitlement_store import a_grant, a_principal
    from tests.unit.test_first_administrator import appoint, audited

    with audited("brain_fa_head_in_place") as url:
        a_principal(url, FIRST)
        a_grant(url, FIRST, "read:audit", scope=FINANCE)
        outcome = appoint(url)
        rows = sql(
            url,
            "SELECT capability, scope FROM gate.capability_grant"
            " WHERE principal_id = %s AND deleted_at IS NULL ORDER BY capability",
            FIRST,
        )

    assert outcome == "appointed"
    assert [one[0] for one in rows] == sorted(GRANTED_AT_APPOINTMENT)
    [kept] = [
        Scope.model_validate(scope) for capability, scope in rows if capability == "read:audit"
    ]
    assert kept == FINANCE
