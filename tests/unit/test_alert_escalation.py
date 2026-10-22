"""The ladder an alert climbs is shown on its runbook, ending at the supplier the company named.

`brain.ops.alerting` has built the ladder and refused a supplier rung with no contact since it was
written, and nothing showed it to anyone. The runbook of every alert now carries it. The contact is
the install's own setting and never a value in this repository, so the tests hand one in.

Task ids: M37.5.2.3
"""

from __future__ import annotations

from brain.help_routes import NO_SUPPLIER_CONTACT_ENTERED, escalation_rungs
from brain.install import BY_NAME
from brain.ops.alerting import ESCALATION, SUPPLIER_CONTACT_SETTING, Tier

#: A made-up contact, written the way a supplier might give one.
MADE_UP: str = "support@example.invalid"


def test_the_ladder_starts_above_whoever_is_on_call_and_ends_at_the_supplier() -> None:
    """The order is the point. Delete this and the first rung shown is the one the reader is
    already on, or the supplier is not last."""
    rungs = escalation_rungs(MADE_UP)
    assert [one.who for one in rungs] == ["installation owner", "supplier"]
    assert rungs[0].can_do == ESCALATION[1].can_do


def test_a_contact_that_was_entered_is_shown_on_the_supplier_rung_and_only_there() -> None:
    """The positive case. Delete this and the contact never reaches a reader, or reaches the rung
    inside the install that has no contact to give."""
    rungs = escalation_rungs(MADE_UP)
    assert MADE_UP in rungs[1].reached_by
    assert "who may be told" in rungs[1].reached_by
    assert rungs[0].reached_by == ""


def test_with_no_contact_the_supplier_rung_is_still_shown_and_says_nobody_is_under_it() -> None:
    """A ladder hiding its top rung reads as complete. Delete this and the last step vanishes on
    exactly the installs that have not set it up, or a placeholder is shown as an address."""
    for unset in ("unset", "", "   "):
        rungs = escalation_rungs(unset)
        assert rungs[-1].who == "supplier"
        assert rungs[-1].reached_by == NO_SUPPLIER_CONTACT_ENTERED
        assert "unset" not in rungs[-1].reached_by.replace("Install, Settings", "")


def test_the_setting_the_ladder_reads_is_a_declared_installation_value_defaulting_to_unset() -> (
    None
):
    """The name is held to the declaration. Delete this and the ladder reads a setting nobody can
    configure, and the supplier rung is never reachable."""
    assert SUPPLIER_CONTACT_SETTING in BY_NAME
    assert BY_NAME[SUPPLIER_CONTACT_SETTING].default == "unset"
    assert {one.tier for one in ESCALATION} >= {Tier.INSTALLATION_OWNER, Tier.SUPPLIER}
