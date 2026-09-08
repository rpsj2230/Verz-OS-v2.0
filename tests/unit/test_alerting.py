"""Alert routing, severity, runbooks and the escalation ladder.

Task ids: M37.5.2.1, M37.5.2.2, M37.5.2.3
"""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest

from brain.core.field_policy import Classification
from brain.ops.alerting import (
    ESCALATION,
    ROUTES,
    SUPPLIER_CONTACT_SETTING,
    AlertingError,
    EscalationStep,
    Route,
    Runbook,
    Severity,
    Tier,
    disclosure_findings,
    escalation_gaps,
    escalation_path,
    route_for,
    routing_gaps,
    runbook_gaps,
    supplier_step,
)


def _route(
    severity: Severity,
    *,
    within: timedelta,
    carried_by: Classification = Classification.INTERNAL,
    wakes: bool = False,
) -> Route:
    return Route(
        severity=severity,
        audience=ROUTES[Severity.NOTICED].audience,
        carried_by=carried_by,
        acknowledge_within=within,
        wakes_somebody=wakes,
    )


# ----------------------------------------------------------------------- severity and routing
def test_every_severity_has_a_route() -> None:
    """Delete this and a severity can be added that reaches nobody.

    `route_for` raises on a severity with no row, and it raises only when somebody asks for
    it, which on a quiet estate is the day of the incident. This is the check that asks on
    every run instead.
    """
    assert routing_gaps() == ()
    for severity in Severity:
        assert route_for(severity).severity is severity


def test_a_louder_severity_is_acknowledged_faster_than_a_quieter_one() -> None:
    """Delete this and the three levels collapse into one meaning.

    Three severities that are all acknowledged within a day are three words for the same
    thing, and an operator with four alerts open has no order to work in. The property is
    asserted over consecutive pairs so it survives a fourth level being added.
    """
    ordered = [ROUTES[one] for one in sorted(Severity)]
    for quieter, louder in pairwise(ordered):
        assert louder.acknowledge_within < quieter.acknowledge_within
    assert len(ordered) == len(Severity)


def test_a_routing_table_where_being_louder_buys_nothing_is_reported() -> None:
    """Delete this and `routing_gaps` is only ever asked about the table that satisfies it.

    A check run against the constants beside it cannot be shown to fail, which is the reason
    every gap function in this package takes its subject as a parameter. This is the negative
    case for the ordering rule.
    """
    flat = {
        Severity.NOTICED: _route(Severity.NOTICED, within=timedelta(hours=1)),
        Severity.RAISED: _route(Severity.RAISED, within=timedelta(hours=1)),
        Severity.WOKEN: _route(Severity.WOKEN, within=timedelta(hours=1)),
    }
    findings = routing_gaps(flat)
    assert any("buys no faster response" in one for one in findings)


def test_a_row_filed_under_the_wrong_severity_is_reported() -> None:
    """Delete this and a copy-paste routes the loudest alerts by the quietest audience.

    This is the mistake that reads correctly in review: every severity is present, every
    window is plausible, and one row is under the wrong key. Nothing about the table looks
    wrong until an incident goes to a digest.
    """
    misfiled = {
        Severity.NOTICED: ROUTES[Severity.NOTICED],
        Severity.RAISED: ROUTES[Severity.WOKEN],
        Severity.WOKEN: ROUTES[Severity.WOKEN],
    }
    findings = routing_gaps(misfiled)
    assert any("is keyed to a row declaring" in one for one in findings)


def test_a_severity_with_no_row_is_reported_and_refused() -> None:
    """Delete this and an alert at an unrouted severity reaches nobody, silently."""
    partial = {Severity.NOTICED: ROUTES[Severity.NOTICED]}
    assert any("reaches nobody" in one for one in routing_gaps(partial))
    with pytest.raises(AlertingError, match="has no route"):
        route_for(Severity.WOKEN, partial)


def test_a_louder_alert_may_not_be_carried_somewhere_a_quieter_one_may_not() -> None:
    """Delete this and the alert that says a guarantee has stopped holding is the one widened
    to reach somebody quickly.

    The direction the leak runs. A loud alert is the one somebody puts on a channel that
    reaches people fastest, and that is generally the least fit channel there is.
    """
    inverted = {
        Severity.NOTICED: _route(
            Severity.NOTICED,
            within=timedelta(days=7),
            carried_by=Classification.CONFIDENTIAL,
        ),
        Severity.RAISED: _route(Severity.RAISED, within=timedelta(days=1)),
        Severity.WOKEN: _route(Severity.WOKEN, within=timedelta(hours=1)),
    }
    assert any("may go somewhere the quieter one may not" in one for one in routing_gaps(inverted))


def test_a_route_acknowledged_in_no_time_is_refused() -> None:
    """Delete this and a severity can be declared whose alerts are overdue on arrival."""
    with pytest.raises(AlertingError, match="closed before the alert was raised"):
        _route(Severity.NOTICED, within=timedelta(0))


def test_only_the_loudest_route_wakes_somebody() -> None:
    """Delete this and every level becomes one that interrupts somebody at night.

    A severity that wakes people is an authority delegated deliberately, and the way it
    stops being deliberate is one level at a time.
    """
    assert [one for one in Severity if ROUTES[one].wakes_somebody] == [Severity.WOKEN]


def test_waking_somebody_needs_a_grant_that_reading_a_digest_does_not() -> None:
    """Delete this and the two audiences can be made the same capability with nothing failing.

    This is the `hubspot.CEILING_NAME` shape: two constants that are supposed to differ, in a
    table whose other checks never compare them, so pointing one at the other passes every
    test in the file. Being woken at three in the morning is an authority somebody delegates
    deliberately, and one grant for both means anybody who may read the weekly digest is on
    the rota.
    """
    assert ROUTES[Severity.WOKEN].audience != ROUTES[Severity.NOTICED].audience
    assert ROUTES[Severity.RAISED].audience == ROUTES[Severity.NOTICED].audience


def test_the_alert_that_wakes_somebody_is_carried_more_carefully_than_a_digest_line() -> None:
    """Delete this and the loudest alert can be routed at the sensitivity of a digest.

    A digest line saying a sweep is behind is an internal operational fact. An alert saying a
    guarantee about somebody's data has stopped holding is not a sentence for a consumer
    messaging application on a personal phone, which is the argument
    `brain.ops.denial_alerts.ALERT_CLASSIFICATION` makes in the same words about its own.
    `routing_gaps` only refuses a louder alert carried *lower*, so equal passes it and this is
    what pins the step.
    """
    assert ROUTES[Severity.WOKEN].carried_by.rank > ROUTES[Severity.NOTICED].carried_by.rank
    assert ROUTES[Severity.WOKEN].carried_by is not Classification.RESTRICTED


# ------------------------------------------------------------------ what a body may say
def test_an_alert_body_naming_a_capability_is_refused() -> None:
    """Delete this and the operational alert becomes the place the entitlement model leaks.

    `read:client.contract_value` in a sentence says the field exists to whoever is holding
    the phone, and the phone is frequently not the reader's. The grammar applied is
    `brain.core.entitlement.CAPABILITY_RE` itself rather than a fourth copy of it, because
    three copies of the tool-name grammar disagreed in this repository and CI passed a name
    the registry refused.
    """
    findings = disclosure_findings("the sweep is behind and nobody may read:client.value now")
    assert len(findings) == 1
    assert "read:client.value" in findings[0]


def test_an_alert_body_using_a_structural_word_is_refused() -> None:
    """Delete this and the helpful sentence gets added back.

    Literal sentences rather than a loop over the word list, because a loop over the list
    asserts the list against itself and passes for every list it could possibly hold. These
    three fail individually if the corresponding entry is removed.
    """
    assert disclosure_findings("the digest is behind for one principal") != ()
    assert disclosure_findings("4 hidden items were not swept") != ()
    assert disclosure_findings("the run left a grant in place") != ()


def test_an_alert_body_about_a_mechanism_passes() -> None:
    """Delete this and the check is satisfied by a function that refuses everything.

    Every refusal test needs a sibling proving the thing still works, and this one is not
    decoration: the list carried `department` and `record` when it was first written and
    refused two ordinary sentences about a roster sync and a queue, which is how a check
    ends up with an exemption list or gets routed around.
    """
    assert (
        disclosure_findings(
            "the retention sweep has not run for 3 days and nothing calls it in this installation"
        )
        == ()
    )


# ------------------------------------------------------------------------- runbooks
def test_a_runbook_that_escalates_inside_the_acknowledgement_window_is_reported() -> None:
    """Delete this and every alert escalates automatically.

    A runbook climbing while the first responder is still inside the time they were given
    makes the rung above them the first responder, and the rung below stops reading its own
    alerts within a fortnight.
    """
    route = ROUTES[Severity.RAISED]
    too_soon = Runbook(
        first_check=("look",),
        then_do=("fix",),
        escalate_after=route.acknowledge_within,
    )
    assert runbook_gaps(too_soon, route) != ()
    in_time = Runbook(
        first_check=("look",),
        then_do=("fix",),
        escalate_after=route.acknowledge_within * 2,
    )
    assert runbook_gaps(in_time, route) == ()


def test_a_runbook_with_nothing_to_check_is_refused() -> None:
    """Delete this and a runbook can send somebody to fix a thing before establishing that it
    is happening, which is how an alert about a deployment becomes an outage."""
    with pytest.raises(AlertingError, match="nothing to check"):
        Runbook(first_check=(), then_do=("fix",), escalate_after=timedelta(hours=1))


def test_a_runbook_with_nothing_to_do_is_refused() -> None:
    """Delete this and a notification can be filed as a runbook."""
    with pytest.raises(AlertingError, match="nothing to do"):
        Runbook(first_check=("look",), then_do=(), escalate_after=timedelta(hours=1))


def test_a_runbook_step_with_no_words_in_it_is_refused() -> None:
    """Delete this and a blank step reads as a step somebody skipped.

    The empty string and a string of spaces are both refused. A dataclass validator tested
    only with `""` passes with `strip()` removed, which is the mutation this covers.
    """
    with pytest.raises(AlertingError, match="no words in it"):
        Runbook(first_check=("look", ""), then_do=("fix",), escalate_after=timedelta(hours=1))
    with pytest.raises(AlertingError, match="no words in it"):
        Runbook(first_check=("look", " "), then_do=("fix",), escalate_after=timedelta(hours=1))


def test_a_runbook_that_escalates_before_it_is_read_is_refused() -> None:
    """Delete this and a runbook can be declared that makes the rung above the first
    responder."""
    with pytest.raises(AlertingError, match="escalated"):
        Runbook(first_check=("look",), then_do=("fix",), escalate_after=timedelta(0))


# ------------------------------------------------------------------------- escalation
def test_the_ladder_climbs_and_ends_outside_the_installation() -> None:
    """Delete this and the ladder can end at the owner, which reads as complete right up to
    the incident nobody at the client can fix."""
    assert escalation_gaps() == ()
    assert [one.tier for one in ESCALATION] == sorted(Tier)
    assert ESCALATION[-1].tier is Tier.SUPPLIER


def test_a_ladder_with_no_way_to_reach_the_outside_rung_is_reported() -> None:
    """Delete this and the last rung is a sentence with no telephone number under it.

    The finding that fails at exactly the moment it is used: `Tier.SUPPLIER` is not somebody
    the entitlement model can resolve, so a rung with no setting naming them is a rung nobody
    can climb to.
    """
    unreachable = (
        ESCALATION[0],
        ESCALATION[1],
        EscalationStep(
            tier=Tier.SUPPLIER,
            can_do="change the software",
            may_be_told="the name of the mechanism",
        ),
    )
    findings = escalation_gaps(unreachable)
    assert any("nothing under it" in one for one in findings)


def test_a_ladder_out_of_order_is_reported() -> None:
    """Delete this and a reader follows the ladder in the order it is written, which is down."""
    backwards = (ESCALATION[2], ESCALATION[1], ESCALATION[0])
    assert any("does not climb" in one for one in escalation_gaps(backwards))


def test_a_missing_tier_is_reported() -> None:
    """Delete this and a rung can go missing, and the one that goes missing is the last."""
    assert any("is not on the ladder" in one for one in escalation_gaps((ESCALATION[0],)))


def test_the_path_never_goes_downward() -> None:
    """Delete this and an incident can be sent back to somebody who has already said they
    cannot fix it.

    Starting at a rung and being offered the rung below is how an escalation loops, and it
    loops silently because each hand-off looks correct on its own.
    """
    assert [one.tier for one in escalation_path(from_tier=Tier.INSTALLATION_OWNER)] == [
        Tier.INSTALLATION_OWNER,
        Tier.SUPPLIER,
    ]
    assert [one.tier for one in escalation_path(from_tier=Tier.SUPPLIER)] == [Tier.SUPPLIER]


def test_a_rung_that_adds_no_authority_is_refused() -> None:
    """Delete this and a rung can be added that adds delay and nothing else."""
    with pytest.raises(AlertingError, match="adds delay"):
        EscalationStep(tier=Tier.SUPPLIER, can_do="  ", may_be_told="the mechanism's name")


def test_a_rung_that_does_not_say_what_it_may_be_told_is_refused() -> None:
    """Delete this and the rung nobody wrote a limit for is the rung somebody widens under
    pressure, which is how a supplier with no account ends up holding a description of the
    estate."""
    with pytest.raises(AlertingError, match="does not say what it may be told"):
        EscalationStep(tier=Tier.SUPPLIER, can_do="change the software", may_be_told="")
    with pytest.raises(AlertingError, match="does not say what it may be told"):
        EscalationStep(tier=Tier.SUPPLIER, can_do="change the software", may_be_told=" ")


def test_a_rung_whose_own_words_disclose_something_is_refused() -> None:
    """Delete this and the escalation ladder becomes the one place in this system where a
    capability is written down in prose that gets forwarded outside the installation."""
    with pytest.raises(AlertingError, match="disclose"):
        EscalationStep(
            tier=Tier.SUPPLIER,
            can_do="change the software",
            may_be_told="everything under read:client.contract_value",
        )


# ------------------------------------------------------------------------- the supplier
def test_the_supplier_contact_is_a_setting_and_this_module_holds_no_address() -> None:
    """Delete this and a support address ships to every company that installs this.

    The flavour of client value that survives review, because it reads as ours rather than as
    theirs. `SUPPLIER_CONTACT_SETTING` is a name; the value arrives as a parameter, so there
    is nowhere in the module for an address to be written down.
    """
    assert SUPPLIER_CONTACT_SETTING == "support_contact"
    line = supplier_step("whatever the installation was told")
    assert "whatever the installation was told" in line
    assert Tier.SUPPLIER.name in line


def test_an_unset_supplier_contact_is_refused_rather_than_defaulted() -> None:
    """Delete this and a placeholder becomes an address a message is sent to.

    The send succeeds, the escalation reads as done in every log, and nobody outside the
    installation ever hears. That is the failure this whole module exists to make impossible,
    arriving through the one field that has no sensible default.
    """
    with pytest.raises(AlertingError, match="is not set"):
        supplier_step("")
    with pytest.raises(AlertingError, match="is not set"):
        supplier_step("   ")


def test_a_ladder_with_no_supplier_rung_cannot_produce_a_supplier_step() -> None:
    """Delete this and `supplier_step` answers for a ladder that ends inside the
    installation, which is a contact for a rung that does not exist."""
    with pytest.raises(AlertingError, match="nobody outside"):
        supplier_step("a contact", (ESCALATION[0], ESCALATION[1]))
