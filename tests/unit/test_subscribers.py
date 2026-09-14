"""The subscriber screen's decisions: who is shown the list, and who may change it.

Every test here builds the reader from grants rather than from a boolean, because the one
question this module asks is `brain.ops.outbox.may_manage`, and a test that handed it a
pre-decided answer would be a test of the screen's layout rather than of who sees it.

Task ids: M17.5.3
"""

from __future__ import annotations

import inspect
from dataclasses import fields
from datetime import UTC, datetime

import pytest

from brain.console.subscribers import (
    NOT_AVAILABLE,
    SubscriberConsoleError,
    SubscriberLine,
    deactivation,
    findings,
    registration,
    subscriber_lines,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.outbox import MANAGE_SUBSCRIBERS, EventKind, Subscriber, subscriber_gaps
from brain.ops.secrets import SecretRef, VaultRole

#: Instants chosen so no wall clock ever crosses them. The reader's grant lapses between the
#: two, which is what lets a test tell a check made at `now` from one made at the process clock.
BEFORE_LAPSE = datetime(2400, 1, 1, tzinfo=UTC)
LAPSES = datetime(2500, 1, 1, tzinfo=UTC)
AFTER_LAPSE = datetime(2600, 1, 1, tzinfo=UTC)

SECRET_REF = SecretRef(path="webhooks/creds/finance", role=VaultRole.APPLICATION)


def manager(principal_id: str = "u_weiling") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(Grant(capability=MANAGE_SUBSCRIBERS, scope=Scope.unrestricted()),),
        not_after=LAPSES,
    )


def bystander() -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_aaron",
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
    )


def a_subscriber(subscriber_id: str, **overrides: object) -> Subscriber:
    defaults: dict[str, object] = {
        "subscriber_id": subscriber_id,
        "endpoint": f"https://hooks.example.com/{subscriber_id}",
        "secret_ref": SECRET_REF,
        "kinds": (EventKind.AUTOMATION_RUN_FINISHED, EventKind.APPROVAL_REQUESTED),
        "created_by": "u_rupash",
    }
    defaults.update(overrides)
    return Subscriber(**defaults)  # type: ignore[arg-type]


REGISTERED = (a_subscriber("sub_zeta"), a_subscriber("sub_alpha", active=False))


def test_a_manager_sees_every_subscriber_in_id_order_with_when_it_last_delivered() -> None:
    """The positive case, and what every refusal below is withholding.

    Delete this and a `subscriber_lines` that returned nothing to everybody would satisfy
    every other test in this file."""
    lines = subscriber_lines(manager(), REGISTERED, {"sub_zeta": BEFORE_LAPSE}, now=BEFORE_LAPSE)

    assert [one.subscriber_id for one in lines] == ["sub_alpha", "sub_zeta"]
    assert [one.active for one in lines] == [False, True]
    assert lines[1].kinds == ("approval.requested", "automation.run_finished")
    assert lines[1].last_delivered_at == BEFORE_LAPSE


def test_a_subscriber_never_delivered_to_says_so_rather_than_showing_an_old_date() -> None:
    """Absent from the delivered map means never, and the line carries None for it.

    Delete this and a default of some instant makes a subscriber that has never received
    anything look like one that went quiet."""
    lines = subscriber_lines(manager(), REGISTERED, {}, now=BEFORE_LAPSE)

    assert [one.last_delivered_at for one in lines] == [None, None]


def test_a_reader_who_may_not_manage_is_shown_what_an_install_with_none_shows() -> None:
    """No list and no findings, and the same empty answer an install with no subscribers gives.

    Delete this and the map of where the company's identifiers are sent is a console tab away
    from anybody holding any grant at all."""
    assert subscriber_lines(bystander(), REGISTERED, {}, now=BEFORE_LAPSE) == ()
    assert subscriber_lines(manager(), (), {}, now=BEFORE_LAPSE) == ()
    assert findings(bystander(), REGISTERED, now=BEFORE_LAPSE) == ()


def test_the_reader_is_judged_at_the_instant_they_ask_and_not_at_the_process_clock() -> None:
    """The manager's grant lapses in 2500. Asked in 2400 they see the list; asked in 2600 they
    see nothing. A check that dropped `now` would consult today's clock and show both.

    Delete this and a lapsed administrator keeps the screen until somebody deletes the grant."""
    assert subscriber_lines(manager(), REGISTERED, {}, now=BEFORE_LAPSE)
    assert subscriber_lines(manager(), REGISTERED, {}, now=AFTER_LAPSE) == ()
    assert findings(manager(), REGISTERED, now=AFTER_LAPSE) == ()
    with pytest.raises(SubscriberConsoleError):
        deactivation(manager(), REGISTERED[0], now=AFTER_LAPSE)
    with pytest.raises(SubscriberConsoleError):
        registration(
            manager(),
            subscriber_id="sub_new",
            endpoint="https://hooks.example.com/new",
            secret_ref=SECRET_REF,
            kinds=(EventKind.OPERATION_SETTLED,),
            now=AFTER_LAPSE,
        )


def test_a_line_carries_no_vault_path() -> None:
    """The exact fields of a line, read off the type, and the path absent from what is drawn.

    Delete this and a `secret_ref` field added for convenience puts the shape of the company's
    vault on an administrator's screen."""
    assert {one.name for one in fields(SubscriberLine)} == {
        "subscriber_id",
        "endpoint",
        "kinds",
        "active",
        "created_by",
        "last_delivered_at",
    }
    lines = subscriber_lines(manager(), REGISTERED, {}, now=BEFORE_LAPSE)
    assert SECRET_REF.path not in repr(lines)


def test_a_manager_is_given_the_outbox_findings_whole() -> None:
    """The findings are `subscriber_gaps`, compared with that function rather than restated.

    Delete this and a findings function that returned nothing to a manager too would hide two
    subscriptions delivering everything twice to one endpoint."""
    doubled = (
        a_subscriber("sub_one", endpoint="https://hooks.example.com/same"),
        a_subscriber("sub_two", endpoint="https://hooks.example.com/same"),
    )

    found = findings(manager(), doubled, now=BEFORE_LAPSE)
    assert found == subscriber_gaps(doubled)
    assert any("sub_one" in one and "sub_two" in one for one in found)


def test_the_registering_reader_is_the_creator_and_nobody_else_can_be_named() -> None:
    """`created_by` comes from the entitlement and there is no parameter to pass it through.

    Delete this and a `created_by` argument added to the form lets whoever registers a
    subscription write somebody else's name on it."""
    made = registration(
        manager("u_weiling"),
        subscriber_id="sub_new",
        endpoint="https://hooks.example.com/new",
        secret_ref=SECRET_REF,
        kinds=(EventKind.OPERATION_SETTLED,),
        now=BEFORE_LAPSE,
    )

    assert made.created_by == "u_weiling"
    assert made.active
    assert "created_by" not in inspect.signature(registration).parameters


def test_a_reader_who_may_not_manage_is_refused_a_change_in_words_that_name_nothing() -> None:
    """Both changes refuse a bystander with one fixed sentence.

    Delete this and a refusal that named the subscriber would confirm that it exists to
    somebody who may not be told."""
    with pytest.raises(SubscriberConsoleError) as refused_registration:
        registration(
            bystander(),
            subscriber_id="sub_new",
            endpoint="https://hooks.example.com/new",
            secret_ref=SECRET_REF,
            kinds=(EventKind.OPERATION_SETTLED,),
            now=BEFORE_LAPSE,
        )
    with pytest.raises(SubscriberConsoleError) as refused_deactivation:
        deactivation(bystander(), REGISTERED[0], now=BEFORE_LAPSE)

    assert str(refused_registration.value) == NOT_AVAILABLE
    assert str(refused_deactivation.value) == NOT_AVAILABLE
    assert "sub_" not in NOT_AVAILABLE


def test_deactivation_switches_a_subscriber_off_once() -> None:
    """Off, and then refused a second time rather than handed back unchanged.

    Delete this and a second deactivation reaches the store, which would record a new instant
    for when the subscription ended."""
    off = deactivation(manager(), REGISTERED[0], now=BEFORE_LAPSE)

    assert not off.active
    assert off.subscriber_id == REGISTERED[0].subscriber_id
    with pytest.raises(SubscriberConsoleError):
        deactivation(manager(), off, now=BEFORE_LAPSE)
