"""A new install opens furnished, and the furniture is nobody's data.

Every test here is about one of the two ways this goes wrong. Either the starter set is empty,
so a client spends their first hour inventing decisions this product has already made, or it
carries the demonstration with it, so a fictitious company's records land in a real one's
database looking exactly like their own.

Task ids: M41.2.7 M41.2.8
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
from pathlib import Path

import pytest

from brain.agents.catalogue import CATALOGUE
from brain.demo import DEMO_PREFIX, principal_rows, record_rows
from brain.identity.roles import Role
from brain.ops.starter import (
    APPLIED_BY,
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


# --- where the starter set is applied, and where it is not -------------------------------------


def test_the_seed_command_does_not_apply_the_starter_set() -> None:
    """**The refusal M41.2.8 asks for, stated against the one command that would break it.**
    `brain.seed` is the obvious host: it is the only thing in this repository that writes rows
    at install time, and `make seed` is already in the Makefile. Wiring the starter set into it
    would mean a client who wanted the six roles had to load Northwind Facilities to get them,
    which is the conflation this module exists to refuse.

    There is a second reason, measured on 2026-09-11 against a real PostgreSQL and recorded in
    `A_FURNISHED_SYSTEM_AND_A_DEMONSTRATION_HAVE_OPPOSITE_PRECONDITIONS`: the seed refuses a
    database holding rows it does not own, and the database the starter set is wanted in holds
    the first administrator already. A seed that applied it would refuse exactly when it was
    needed.

    Asserted on the import graph rather than on a substring, because a module that reaches this
    one through another module has the same effect and reads as unrelated.

    Delete this and the two deliveries can become one command, and the symptom is invented
    contract values in a real company's database looking exactly like their own.
    """
    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "seed.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # **`from brain.ops import starter` is the form that got past the first version
            # of this test, and a mutation is how that was found.** Reading `node.module`
            # alone sees `brain.ops`, which is not the starter set by any spelling, so the
            # assertion below passed with that import sitting in the file. The name has to be
            # rejoined to the module for the dotted path to be what is checked.
            where = node.module or ""
            imported.add(where)
            imported.update(f"{where}.{alias.name}".strip(".") for alias in node.names)

    assert imported, "nothing parsed, so this test proves nothing"
    assert not any(one.startswith("brain.ops.starter") for one in imported), sorted(imported)
    assert "starter" not in {one.rsplit(".", 1)[-1] for one in imported}

    # And the other direction, which catches a wiring that does not go through an import: the
    # seed writes none of the tables the furniture lives in. Somebody applying the starter set
    # from here would have to add one of these to `brain.demo.TABLES` to do it.
    import brain.seed as seed_mod

    furniture = {
        "gate.capability_pack",
        "gate.capability_pack_assignment",
        "agent.template_instance",
        "agent.template_version",
        "ops.setting",
    }
    assert seed_mod.WRITES, "the seed writes nothing, so this test proves nothing"
    assert not furniture & set(seed_mod.WRITES), sorted(furniture & set(seed_mod.WRITES))
    assert not furniture & set(seed_mod.REMOVAL_KEYS)


def test_the_module_the_starter_set_is_applied_by_exists_and_can_say_it_is_done() -> None:
    """**A paragraph naming somewhere is a paragraph that outlives it.** `APPLIED_BY` names
    `brain.deployment.installer` and the field on its `Step` that makes a write safe to run
    twice, and this fails if either goes away, which is the shape `brain.seed.THE_ONLY_TAKER`
    and `brain.ops.controls.NOT_A_SCHEDULE` both take for the same reason.

    The `already_done` field is the load-bearing half.
    `A_MIGRATION_THAT_INSERTS_ROWS_TAKES_THEM_BACK_ON_THE_NEXT_UPGRADE` argues the starter set
    is applied once, at install, and `Step` is the only place in this repository where "applied
    once" is a property a step must declare rather than a convention somebody keeps. Naming a
    host that could not express that would be naming the wrong host.

    Delete this and the decision becomes prose pointing at a module that may not exist, which
    is how a leaf comes to be claimed with nothing behind it.
    """
    module_name, field = APPLIED_BY
    module = importlib.import_module(module_name)

    step = module.Step
    assert dataclasses.is_dataclass(step)
    fields = {one.name for one in dataclasses.fields(step)}
    assert field in fields, f"{module_name}.Step has no {field!r}: {sorted(fields)}"
    assert "changes" in fields, "nothing marks a step as writing, so `already_done` guards what?"

    # And it is a plan rather than a single function, so there is somewhere for a step to go.
    assert module.PLAN, "the install plan is empty"
    assert all(one.already_done for one in module.PLAN if one.changes), (
        "a step that writes cannot say it is done, so 'applied once at install' is not a "
        "property this plan can express"
    )


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
