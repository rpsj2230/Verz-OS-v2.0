"""The two properties M29.2.6 asks for, and the one case that satisfies both and still widens.

The last test in this file is the most important thing in the package. It executes the case
this design cannot take: a connector plugin supplying a visibility predicate that is
restricted in shape and tautological in effect, which widens who may read a projected row
without touching an entitlement set at all, so neither this module nor
`brain.connectors.manifest` sees it.

Task ids: M29.2.6
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.connectors.manifest import (
    ChangeSignal,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.redaction import UNREDACTED_TYPE_NAMES
from brain.core.scope import Clause, Op, Scope
from brain.plugins.contract import (
    PluginContractError,
    assert_cannot_see_unredacted,
    plan_run,
    points_a_plugin_may_take,
    unmet,
    would_be_refused,
)
from brain.plugins.lifecycle import PLUGIN_NOT_AVAILABLE
from brain.plugins.manifest import PluginManifest
from brain.plugins.points import (
    A_CONNECTOR_PLUGIN_STILL_CANNOT_BE_HANDED_THE_VISIBILITY_PREDICATE,
    POINTS,
    Answer,
)

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
PACKAGE = Path(__file__).resolve().parents[2] / "src" / "brain" / "plugins"

#: A reach that holds one ordinary read, for a caller who is not an administrator.
READS_CLIENT_NAMES = EntitlementSet(
    principal_id="asker",
    grants=(Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),),
)


def _a_manifest(**overrides: object) -> PluginManifest:
    base: dict[str, object] = {
        "plugin_id": "probe",
        "version": "1.0.0",
        "point": "connector",
        "core_min": "1.0.0",
        "core_max": "1.4.0",
    }
    base.update(overrides)
    return PluginManifest(**base)  # type: ignore[arg-type]


# ------------------------------------------------------- a plugin cannot widen anything
def test_the_reach_a_plugin_runs_with_is_the_callers_own_whatever_it_asked_for() -> None:
    """**Half of M29.2.6.** The entitlement hash is the comparison
    `brain.ops.automation_piece.assert_same_reach` uses on its own path, and it is
    order-independent and covers the time bound, so two sets with the same hash admit the
    same things.

    Asked for with a capability the caller does hold, so the manifest cannot be refused on
    its way to proving the point. Delete this and somebody adds a union here and nothing
    compares the two sides."""
    manifest = _a_manifest(requires=(Capability(value="read:client.name"),))

    run = plan_run(manifest, caller=READS_CLIENT_NAMES, now=NOW)

    assert run.reach.ent_hash() == READS_CLIENT_NAMES.ent_hash()
    assert run.reach.grants == READS_CLIENT_NAMES.grants


def test_a_plugin_inherits_the_callers_expiry_and_cannot_outlive_it() -> None:
    """**A mutation found this.** Replacing the returned reach with a copy of the caller's
    that has `not_after` stripped survived every test in this package, because every caller
    built here had no time bound to strip. That mutation is a widening: it gives a plugin a
    reach with no end on behalf of a contractor whose access does end.

    `ent_hash` covers the time bound deliberately, which `brain.core.entitlement` explains as
    the reason an answer cached before an expiry is not served after it, so the hash
    comparison is the whole check once the caller actually has one.

    Delete this and the reach handed to a plugin can lose its expiry with the suite green."""
    bounded = EntitlementSet(
        principal_id="contractor",
        grants=READS_CLIENT_NAMES.grants,
        not_after=NOW + timedelta(days=30),
    )

    run = plan_run(_a_manifest(), caller=bounded, now=NOW)

    assert run.reach.not_after == bounded.not_after
    assert run.reach.ent_hash() == bounded.ent_hash()
    assert run.reach.ent_hash() != READS_CLIENT_NAMES.ent_hash()


def test_no_module_in_this_package_builds_an_entitlement_of_its_own() -> None:
    """**This test is the enforcement and the docstrings are its explanation.** A later edit
    that intersected two reaches or constructed a Grant would look entirely reasonable in the
    file it appeared in, which is what `tests/invariants/test_single_implementation.py` was
    written about after ten documents named the wrong module for the one intersection.

    A `Capability` is allowed and a `Grant` is not, and the distinction is the whole point: a
    capability is a name, and a grant is that name bound to a scope inside a set, which is
    what a principal holds. `PLUGIN_ADMIN` is a name.

    Parsed rather than grepped, so this file quoting `.intersect` in its own docstring does
    not fail it. Delete this and the package can grow a second source of grants."""
    forbidden = {"Grant", "EntitlementSet", "Scope"}
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Attribute) and called.attr == "intersect":
                found.append(f"{path.name}:{node.lineno} intersects")
            if isinstance(called, ast.Name) and called.id in forbidden:
                found.append(f"{path.name}:{node.lineno} builds a {called.id}")

    assert found == []


def test_a_capability_the_caller_lacks_is_reported_as_unmet_and_never_added() -> None:
    """`requires` is a question about the caller. A manifest asking for something the caller
    does not hold gets an answer, and the answer is a list for an operator rather than a
    grant for the plugin.

    Delete this and `unmet` could return an empty tuple always, which would make every
    manifest installable and every requirement meaningless."""
    manifest = _a_manifest(
        requires=(Capability(value="admin:everything"), Capability(value="read:client.name"))
    )

    assert unmet(manifest, READS_CLIENT_NAMES, now=NOW) == ("admin:everything",)


def test_an_expired_caller_meets_no_requirement_at_all() -> None:
    """An expired principal holds nothing whatever the grant table still says, so the time is
    what refuses rather than the grants. `now` is a parameter for this test to be possible.

    Delete this and a plugin runs for a contractor whose access ended, with the reach that
    ended with it."""
    expiring = EntitlementSet(
        principal_id="asker",
        grants=READS_CLIENT_NAMES.grants,
        not_after=NOW,
    )
    manifest = _a_manifest(requires=(Capability(value="read:client.name"),))

    assert unmet(manifest, expiring, now=NOW + timedelta(seconds=1)) == ("read:client.name",)


def test_a_plugin_whose_requirements_are_unmet_is_refused_without_naming_one() -> None:
    """Telling a caller that a plugin needs `read:invoice.total` tells them invoices exist,
    that they have totals, and that somebody may read them. The sentence a caller gets is the
    constant with nothing in it.

    Delete this and the refusal grows a helpful explanation, which is an enumeration tool."""
    manifest = _a_manifest(requires=(Capability(value="admin:everything"),))

    with pytest.raises(PluginContractError) as raised:
        plan_run(manifest, caller=READS_CLIENT_NAMES, now=NOW)

    assert str(raised.value) == PLUGIN_NOT_AVAILABLE


def test_a_plugin_at_a_point_that_takes_no_plugins_gets_the_same_sentence() -> None:
    """`scope_pack` is answered by configuration because a pack expands into grants, and
    `storage_backend` by a flag. Both refusals produce the sentence an unmet requirement
    produces and the sentence an unknown point produces, so the three are indistinguishable
    to whoever is asking.

    Delete this and the register becomes enumerable through the refusal messages."""
    for point in ("scope_pack", "storage_backend", "retriever", "not_a_point_at_all"):
        with pytest.raises(PluginContractError) as raised:
            plan_run(_a_manifest(point=point), caller=READS_CLIENT_NAMES, now=NOW)
        assert str(raised.value) == PLUGIN_NOT_AVAILABLE


# --------------------------------------- a plugin cannot see what it did not produce
@pytest.mark.parametrize("name", sorted(UNREDACTED_TYPE_NAMES))
def test_nothing_may_be_handed_a_type_carrying_what_the_gate_withheld(name: str) -> None:
    """Every one of these carries either data the gate has not walked or the record of what
    it withheld, and a plugin holding one is one serialisation away from a person. The names
    are imported from `brain.core.redaction` so there is one owner of the list.

    Delete this and a notification sink can declare that it accepts a `RedactionTrace`."""
    with pytest.raises(PluginContractError, match="would be handed"):
        assert_cannot_see_unredacted(_a_manifest(accepts=(name,)))


def test_a_producer_may_return_what_it_fetched() -> None:
    """A connector sees what it fetched, because fetching is what it is for, and the redactor
    runs on the far side of it. This is the asymmetry the leaf's own words describe: raw data
    may leave a producer and may never enter one.

    Delete this and the rule tightens to refuse every connector, which would make the one
    point CLAUDE.md names as a plugin the one point that cannot be one."""
    assert_cannot_see_unredacted(_a_manifest(point="connector", produces="TypedResult"))


def test_a_consumer_may_not_return_something_the_redactor_has_not_seen() -> None:
    """A sink is downstream of a gate that has already decided what this caller may see, so a
    sink returning a `TypedResult` is manufacturing unredacted data on the far side of the
    redactor.

    Delete this and the direction stops mattering and the asymmetry above becomes a
    permission rather than a rule."""
    with pytest.raises(PluginContractError, match="which is a"):
        assert_cannot_see_unredacted(_a_manifest(point="notification_sink", produces="TypedResult"))


def test_a_consumer_may_return_an_ordinary_type() -> None:
    """The positive sibling. Without it the return check is satisfied by refusing every
    consumer that returns anything at all, and an export format could never return bytes.

    Delete this and the rule could widen from the unredacted names to every name."""
    assert_cannot_see_unredacted(
        _a_manifest(point="notification_sink", accepts=("ChannelPayload",), produces="Receipt")
    )


def test_a_contract_check_against_a_point_that_does_not_exist_checks_nothing() -> None:
    """The point is looked up inside the function rather than passed in, because a caller
    supplying both a manifest and a point can supply a point the manifest does not name, and
    the check would then be made against the wrong direction while reading as made.

    Delete this and a manifest naming a nonexistent point passes the contract check
    silently."""
    with pytest.raises(PluginContractError, match="not an extension point"):
        assert_cannot_see_unredacted(_a_manifest(point="retreiver"))


def test_the_contract_check_runs_before_the_requirements_are_compared() -> None:
    """A manifest that would be handed a `RedactionTrace` is refused on that ground even when
    its requirements are met, so an author cannot discover the ordering by holding the right
    capabilities.

    Delete this and the two checks can be reordered so that a caller with wide reach gets a
    contract violation through."""
    manifest = _a_manifest(accepts=("RedactionTrace",))

    with pytest.raises(PluginContractError, match="would be handed"):
        plan_run(manifest, caller=READS_CLIENT_NAMES, now=NOW)


# ------------------------------------------------------- what M29 would and would not take
def test_the_points_a_plugin_may_take_are_the_seven_the_register_says() -> None:
    """The positive half of `would_be_refused`, which on its own is satisfied by a register
    that refuses everything. Seven of sixteen is the answer to the question M29 is asked, and
    it is asserted against the register rather than as a literal.

    Delete this and 'M29 keeps the promise' stops being a number."""
    takeable = points_a_plugin_may_take()

    assert len(takeable) == 7
    assert set(takeable) == {one.name for one in POINTS if one.answer is Answer.PLUGIN}


def test_would_be_refused_says_nothing_about_a_point_that_takes_a_plugin() -> None:
    """An empty string is the answer for the seven, and it has to be checkable separately
    from the nine, or a reader cannot tell a point that would be taken from one whose reason
    happens to be short.

    Delete this and the function's two meanings become one."""
    assert would_be_refused("connector") == ""
    assert would_be_refused("skill") == ""


def test_would_be_refused_gives_the_reason_for_each_of_the_nine_it_would_not_take() -> None:
    """This is what a module elsewhere is really pointing at when its docstring says the
    answer is a plugin. For nine of the sixteen points the honest answer is no, and each of
    the nine says which of the other answers it takes or that there is no answer yet.

    Delete this and the refusals elsewhere in this repository go on reading as satisfied."""
    refused = {one.name: would_be_refused(one.name) for one in POINTS}
    given = {name: why for name, why in refused.items() if why}

    assert len(given) == 9
    assert "answered by configuration" in given["scope_pack"]
    assert "answered by flag" in given["storage_backend"]
    assert "no contract in this repository" in given["retriever"]
    assert (
        would_be_refused("nothing_of_the_sort") == "'nothing_of_the_sort' is not an extension point"
    )


# ------------------------------- the case this design cannot take, executed rather than asserted
def test_a_connector_plugin_can_still_widen_a_projection_without_holding_any_grant() -> None:
    """**The finding, and it is a known gap rather than a property this package holds.**

    `brain.connectors.manifest.ProjectedEntity` refuses a visibility predicate that is
    unrestricted and one that enumerates principals, and both refusals are right. Neither
    refuses a predicate that is restricted in shape and tautological in effect: the plugin
    projects a field it sets itself, then names that field as the predicate. Every guard
    passes, and every row in the projection is readable by anybody holding the entity's
    capability.

    Nothing in `brain.plugins` sees it either, because no entitlement set is touched: the
    widening happens in what a row *is*, not in what a caller *holds*. That is why the
    connector point's `why` says the point is a plugin for fetching and not for the
    predicate.

    Executed rather than asserted in prose, following `test_single_implementation.py`'s
    `KNOWN_SECOND_RENDERER`: a recorded exception with a test behind it is a fact, and a
    paragraph is a claim. **When somebody closes this gap this test goes red, and the right
    response is to delete it and the constant it checks**, not to loosen it.

    Delete this without closing the gap and the register's own caveat becomes unverified."""
    tautology = Scope(clauses=(Clause(field="is_visible", op=Op.EQ, value="true"),))

    assert not tautology.is_unrestricted()

    projection = ProjectedEntity(
        entity="widget",
        fields=(ProjectedField(name="is_visible", shape=FieldShape.LABEL, uses=(HotUse.FILTER,)),),
        change_signal=ChangeSignal.WEBHOOK,
        visibility=tautology,
    )

    assert projection.visibility == tautology
    assert projection.visibility.matches({"is_visible": "true"})
    assert "widening it needs no grant" in (
        A_CONNECTOR_PLUGIN_STILL_CANNOT_BE_HANDED_THE_VISIBILITY_PREDICATE
    )
