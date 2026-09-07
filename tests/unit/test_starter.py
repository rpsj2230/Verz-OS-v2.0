"""A new install opens furnished, and the furniture is nobody's data.

Every test here is about one of the two ways this goes wrong. Either the starter set is empty,
so a client spends their first hour inventing decisions this product has already made, or it
carries the demonstration with it, so a fictitious company's records land in a real one's
database looking exactly like their own.

Task ids: M41.2.7 M41.2.8
"""

from __future__ import annotations

import pytest

from brain.agents.catalogue import CATALOGUE
from brain.demo import DEMO_PREFIX, principal_rows, record_rows
from brain.identity.roles import Role
from brain.ops.starter import (
    DEFAULTS,
    PACKS,
    Default,
    agents,
    roles,
    starter_gaps,
)


def test_a_new_install_is_furnished_rather_than_blank() -> None:
    """The leaf's own words: a client opens a furnished system rather than a blank one. Four
    things arrive, and each is a decision somebody would otherwise take on their first day
    with no information.

    Asserted as non-empty in all four rather than as one count, because a starter set that
    furnished roles and no agents would still leave the console empty, and the failure would
    be invisible in a total.

    Delete this and the starter set can quietly become an empty tuple, which is exactly the
    state the leaf describes."""
    assert roles()
    assert agents()
    assert PACKS
    assert DEFAULTS
    assert starter_gaps() == ()


def test_the_six_roles_are_the_ones_every_permission_decision_is_written_against() -> None:
    """Not a list kept here. `roles()` reads the enum, so it cannot disagree with the type the
    resolver, the console and every grant are written against.

    Pinned at six by name rather than by count, because a seventh role is a decision about the
    permission model and this is where it should be argued, and because a count alone passes
    when one role is renamed.

    Delete this and a starter set can furnish five roles on an install whose code expects
    six, which presents as one role nobody can assign and no error anywhere."""
    assert set(roles()) == set(Role)
    assert [one.value for one in roles()] == [
        "super_admin",
        "department_admin",
        "member",
        "auditor",
        "connector_admin",
        "approver",
    ]


def test_the_agents_are_the_catalogue_rather_than_a_second_list_of_it() -> None:
    """A second list of what this product ships is a list that drifts, and it drifts silently:
    both are plausible, and the one that is short is discovered by a client asking where an
    agent went.

    Asserted against the catalogue's own ids, so adding a template furnishes it automatically
    and removing one stops furnishing it.

    Delete this and the starter set becomes a hand-kept copy of the catalogue."""
    assert set(agents()) == {manifest.identity.template_id for manifest in CATALOGUE}
    assert len(agents()) == len(CATALOGUE), "two manifests share a template id"


# --- the starter set is not the demo -----------------------------------------------------------


def test_nothing_the_starter_set_furnishes_carries_the_demonstration_with_it() -> None:
    """**M41.2.8, and the reason it is a leaf of its own.** A client wants the roles and does
    not want Northwind Facilities. The two arrive in the same repository, so separate entry
    points are not enough on their own: somebody loading both because they came together puts
    invented clients and invented contract values into a real company's database, where they
    look exactly like the company's own records.

    Checked against the demo's own prefix rather than against a list of demo names, so a fifth
    invented client added tomorrow is covered without editing this.

    Delete this and the furnished system and the demonstration become one delivery."""
    for template in agents():
        assert not template.startswith(DEMO_PREFIX), template
    for pack in PACKS:
        assert not pack.slug.startswith(DEMO_PREFIX), pack.slug
    for one in DEFAULTS:
        assert not one.name.startswith(DEMO_PREFIX), one.name


def test_the_demo_and_the_starter_set_share_no_row_at_all() -> None:
    """The other direction, and the one that catches a real overlap rather than a naming
    convention. The demo produces principals and records; the starter set produces none of
    either, and every identifier it does produce is disjoint from every identifier the demo
    produces.

    The positive half matters as much: the demo really does produce rows, so this is not
    satisfied by a demo that seeds nothing.

    Delete this and the two can grow into each other one identifier at a time."""
    demo_ids = {str(row["id"]) for row in principal_rows()} | {
        str(row["source_id"]) for row in record_rows()
    }

    assert demo_ids, "the demo seeds nothing, so this test proves nothing"
    assert not demo_ids & set(agents())
    assert not demo_ids & {pack.slug for pack in PACKS}
    assert not demo_ids & {one.name for one in DEFAULTS}


def test_the_starter_set_creates_no_account() -> None:
    """A principal is somebody real, and the only account an install may create is the first
    administrator, from a value the installer supplies. Anything furnished with an account is
    an account with no owner and nothing in the audit trail saying where it came from.

    Asserted over the module's public surface rather than by reading its code, so a function
    added later that returns principals fails here.

    Delete this and a starter set can ship a service account, which is the shape of default
    credential this repository spent today removing."""
    import brain.ops.starter as starter

    # Callables only. The named reason constants exist precisely to say the word "account" in
    # a sentence explaining why there is not one, so scanning every public name would refuse
    # the module for documenting itself, which is the shape of check that gets switched off.
    functions = [
        name
        for name in dir(starter)
        if not name.startswith("_") and callable(getattr(starter, name)) and not name[0].isupper()
    ]
    forbidden = ("principal", "account", "user", "password", "secret", "credential")

    assert functions, "nothing public to check"
    for name in functions:
        assert not any(one in name.lower() for one in forbidden), name

    produced = [*roles(), *agents(), *PACKS, *DEFAULTS]
    assert not any(type(one).__name__ == "Principal" for one in produced)


# --- a default has to be a value somebody can act on -------------------------------------------


def test_a_default_with_no_value_or_no_meaning_cannot_be_constructed() -> None:
    """An empty value is an unset setting wearing a value, which is the failure
    `brain.config` records from `DATABASE_URL`. A default with no meaning is one an
    administrator changes to whatever the first incident suggests, because nothing tells them
    what it was for.

    Delete this and the starter set can furnish a blank, which reads on a settings screen as
    a decision somebody made."""
    with pytest.raises(ValueError, match="empty default"):
        Default(name="a", value="  ", meaning="something")

    with pytest.raises(ValueError, match="no meaning"):
        Default(name="a", value="1", meaning="  ")


def test_no_setting_is_defaulted_twice() -> None:
    """Two rows naming one setting make which value applies a property of iteration order.

    Delete this and a merge that keeps both halves of a rename ships an install whose session
    timeout depends on dictionary ordering."""
    names = [one.name for one in DEFAULTS]

    assert len(names) == len(set(names)), sorted(names)
    assert starter_gaps() == ()


def test_the_diagnostic_refuses_a_demo_row_and_a_setting_defaulted_twice() -> None:
    """**Two mutations survived until this existed, and neither check was wrong.** Switching
    off the demo-prefix refusal and the duplicate-setting refusal changed nothing observable,
    because on today's data there is nothing for either to report, and `starter_gaps` read the
    module constants so no test could hand it a bad case.

    A diagnostic that can only be run against the real tree cannot be tested for its refusals.
    So it takes its inputs now, defaulting to the real ones, which is the same argument
    `connections.undeclared_clients` and `handover.handover_gaps` make about theirs.

    Delete this and both refusals go back to being unreachable, and the module reports a clean
    starter set whatever is in it."""
    demo_template = starter_gaps(templates=(f"{DEMO_PREFIX}agent",))
    assert any("carries the demo's prefix" in one for one in demo_template), demo_template

    twice = (
        Default(name="same", value="1", meaning="the first"),
        Default(name="same", value="2", meaning="the second"),
    )
    duplicated = starter_gaps(defaults=twice)
    assert any("defaulted twice" in one for one in duplicated), duplicated

    empty = starter_gaps(templates=())
    assert any("opens blank" in one for one in empty), empty

    assert starter_gaps() == ()


def test_a_new_install_starts_by_asking_a_person_rather_than_trusting_itself() -> None:
    """The one default worth a test of its own. `approval_required_above` is zero, so every
    action carrying a side effect is approved by a person until somebody raises it.

    A new install trusting itself is the wrong default for a reason that has nothing to do
    with the software: nobody has watched it work yet. Raising it is a decision made with
    evidence, and lowering it later is a decision made after something went wrong.

    Delete this and the threshold can be raised in a tidy-up, and the first automated action
    a client sees is one nobody approved."""
    by_name = {one.name: one.value for one in DEFAULTS}

    assert by_name["approval_required_above"] == "0"
    assert by_name["knowledge_visibility"] == "department"
