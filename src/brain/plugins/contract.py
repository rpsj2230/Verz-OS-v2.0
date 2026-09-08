"""The two properties every plugin has to hold, checked before one runs.

M29.2.6 asks for a core contract test: a plugin cannot see an unredacted result it did not
produce, and cannot widen entitlements. Both halves are enforced here by refusing a shape
rather than by watching behaviour, because behaviour is what a plugin supplies.

**Cannot widen.** `plan_run` takes the caller's reach and hands it back unchanged. There is no
arithmetic in this module and there is deliberately no call to `EntitlementSet.intersect`:
`E_run(caller, agent) = E(caller) intersect agent_ceiling` is computed by the gate, in
`brain.gate.leash.decide` and `resume`, and a plugin is not an agent with a ceiling of its
own. What a manifest declares in `requires` is a question about the caller, answered by
`unmet`, and the answer is never added to anything. The property a test can hold is the one
`brain.ops.automation_piece.assert_same_reach` uses on its own path: the entitlement hash of
the reach a plugin runs with equals the hash of the reach that was handed in, for every
manifest, including one requiring `admin:everything`.

`tests/unit/test_plugins_contract.py` asserts that no module in this package constructs a
`Grant`, an `EntitlementSet` or a `Scope`, and calls no `.intersect`. That test is the
enforcement and this paragraph is only its explanation: a later edit that added the arithmetic
would look reasonable in the file it appeared in, which is exactly what
`tests/invariants/test_single_implementation.py` was written about.

**Cannot see an unredacted result it did not produce**, and the leaf's own words are the
mechanism once the direction is known. Raw data may leave a producer and may never enter one:
a connector fetches records and the redactor runs downstream of it, which
`brain.connectors.__init__` already states as the reason a connector holds no permission
logic. So the rule is two lines. Nothing may be **handed** one of `UNREDACTED_TYPE_NAMES`,
whatever the point. Only a `PRODUCES` point may **return** one.

The type names are imported from `brain.core.redaction` rather than listed again. That list is
the one thing here that will change, because it changes whenever somebody adds a type carrying
values the gate has not walked, and a second copy of it would be a copy that agreed on the day
it was written.

Rejected: reading the plugin's Python signature, the way `redaction.assert_channel_adapter`
reads a channel adapter's. It is the stronger check where it applies and it applies to one of
the seven plugin points: a sidecar and a sandbox have no Python function to inspect, and the
manifest is the only thing that exists at all three isolation tiers. An in-process adapter
still goes through `assert_channel_adapter`, which is not replaced here and should not be.

Rejected: checking the type names against the classes they name. It would need an import of
whatever module the plugin claims, which is running a plugin's code to find out whether the
plugin may run.

Task ids: M29.2.6
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.core.redaction import UNREDACTED_TYPE_NAMES
from brain.plugins.lifecycle import PLUGIN_NOT_AVAILABLE
from brain.plugins.manifest import PluginManifest
from brain.plugins.points import POINTS, Answer, Direction, ExtensionPoint, point_named


class PluginContractError(Exception):
    """A plugin was declared or asked to run in a way the core contract refuses."""


#: Why the reach handed to a plugin is the caller's own, unmodified.
A_PLUGIN_IS_NOT_A_PRINCIPAL_AND_HAS_NO_CEILING_OF_ITS_OWN: Final = (
    "An agent is a lens with a ceiling, and the gate narrows the caller's reach by it. A "
    "plugin is not a second lens: it is code running inside a request that already has a "
    "reach, so there is nothing for it to narrow and nothing for it to contribute. A plugin "
    "with a ceiling would be a second thing the run reach is a function of, and the day the "
    "two disagree the wider one is the one in production."
)

#: Why raw data may leave a producer and never enter one.
RAW_DATA_LEAVES_A_PRODUCER_AND_ENTERS_NOTHING: Final = (
    "A connector sees what it fetched, because fetching is what it is for, and the redactor "
    "runs on the far side of it. Nothing else has a claim on unredacted values: a sink, a "
    "format, a model provider and a template are all downstream of a gate that has already "
    "decided what this caller may see, and handing one of them a TypedResult puts the "
    "withheld fields one serialisation away from a person."
)

#: Why an unmet requirement produces the same sentence as an unknown plugin.
AN_UNMET_REQUIREMENT_NAMES_A_CAPABILITY_AND_THEREFORE_NAMES_A_THING: Final = (
    "Telling a caller that a plugin needs read:invoice.total tells them invoices exist, that "
    "they have totals, and that somebody may read them. The refusal a caller sees is one "
    "sentence with nothing in it. Which capabilities were missing is an operator's question, "
    "answered by unmet, behind admin:plugin."
)


@dataclass(frozen=True)
class PluginRun:
    """What a plugin is handed: the caller's reach, and nothing this module computed.

    `reach` is the caller's own set, carried rather than derived. The field exists so that the
    property is assertable: a test compares its `ent_hash` against the caller's and holds the
    whole of "cannot widen entitlements" in one comparison. See
    `A_PLUGIN_IS_NOT_A_PRINCIPAL_AND_HAS_NO_CEILING_OF_ITS_OWN`.
    """

    plugin_id: str
    point: str
    reach: EntitlementSet


def unmet(manifest: PluginManifest, reach: EntitlementSet, *, now: datetime) -> tuple[str, ...]:
    """Capabilities the manifest asks for that this reach does not hold, sorted.

    An operator's answer and never a caller's. See
    `AN_UNMET_REQUIREMENT_NAMES_A_CAPABILITY_AND_THEREFORE_NAMES_A_THING`.

    `now` is a parameter rather than a clock read here, for the reason `brain.ops.admission`
    takes one: an expired principal holds nothing, and a test that could not set the time
    could not check that the expiry is what refuses rather than the grants.
    """
    return tuple(sorted(one.value for one in manifest.requires if not reach.holds(one, now)))


def assert_cannot_see_unredacted(manifest: PluginManifest) -> None:
    """Refuse a manifest that would be handed, or would return, something it may not.

    Two refusals and they are not symmetric, which is the whole content of "it did not
    produce". See `RAW_DATA_LEAVES_A_PRODUCER_AND_ENTERS_NOTHING`.

    The point is looked up here rather than passed in, because a caller who supplies both a
    manifest and a point can supply a point the manifest does not name, and the check would
    then be made against the wrong direction while reading as though it had been made.
    """
    point = point_named(manifest.point)
    if point is None:
        msg = (
            f"{manifest.plugin_id} names {manifest.point!r}, which is not an extension point; "
            "a contract check against a point that does not exist checks nothing"
        )
        raise PluginContractError(msg)

    handed = tuple(sorted(set(manifest.accepts) & UNREDACTED_TYPE_NAMES))
    if handed:
        msg = (
            f"{manifest.plugin_id} would be handed {list(handed)}, which carries values the "
            f"gate has not walked or the record of what it withheld. "
            f"{RAW_DATA_LEAVES_A_PRODUCER_AND_ENTERS_NOTHING}"
        )
        raise PluginContractError(msg)

    if manifest.produces in UNREDACTED_TYPE_NAMES and point.direction is not Direction.PRODUCES:
        msg = (
            f"{manifest.plugin_id} returns {manifest.produces} at {point.name}, which is a "
            f"{point.direction} point; only a point where raw records enter the system may "
            "return something the redactor has not yet seen"
        )
        raise PluginContractError(msg)


def plan_run(
    manifest: PluginManifest,
    *,
    caller: EntitlementSet,
    now: datetime,
) -> PluginRun:
    """Everything that has to be true before a plugin is given a caller's reach.

    Three of the four refusals produce one sentence, `PLUGIN_NOT_AVAILABLE`, with nothing in
    it: somebody able to tell "that point takes no plugins" from "that plugin needs a
    capability you lack" can enumerate the register and the caller's own reach by difference.
    The fourth, the contract check, keeps its own message, because a manifest declaring a
    type it may not be handed is a defect whose every word its own author wrote.

    The reach comes back unchanged. There is no branch in which it does not, and that is the
    property `test_plugins_contract.py` asserts rather than this docstring.
    """
    point = point_named(manifest.point)
    if point is None or point.answer is not Answer.PLUGIN:
        raise PluginContractError(PLUGIN_NOT_AVAILABLE)
    assert_cannot_see_unredacted(manifest)
    if unmet(manifest, caller, now=now):
        raise PluginContractError(PLUGIN_NOT_AVAILABLE)
    return PluginRun(plugin_id=manifest.plugin_id, point=point.name, reach=caller)


def would_be_refused(point_name: str) -> str:
    """Why a plugin at this point would be refused, for whoever was sent here by a refusal.

    An empty string when it would not be. This is the function a module elsewhere is really
    pointing at when its docstring says the answer is a plugin: it says whether M29 would in
    fact take the request, and for nine of the sixteen points the honest answer is no.

    Not a refusal path and never on one. `plan_run` is where a plugin is actually turned away,
    and it says one sentence to everybody. This is documentation with a test behind it, read
    by a person holding the repository open, and it names points rather than data.
    """
    point = point_named(point_name)
    if point is None:
        return f"{point_name!r} is not an extension point"
    if point.answer is Answer.PLUGIN:
        return ""
    if point.answer is Answer.UNDECIDED:
        return (
            f"{point.name} has no contract in this repository and no decision about one. "
            f"{point.why}"
        )
    return f"{point.name} is answered by {point.answer}, not by a plugin. {point.why}"


def points_a_plugin_may_take(points: Sequence[ExtensionPoint] = POINTS) -> tuple[str, ...]:
    """Every point `plan_run` would actually accept a plugin at, sorted.

    The positive half of `would_be_refused`, and it exists because the negative half on its
    own is satisfied by a register that refuses everything. A count of seven against sixteen
    is the answer to the question M29 is asked, and it is one a test can hold to.

    `points` is a parameter defaulting to the register for the reason
    `brain.ops.halt.halt_gaps` takes its own sequence: a check over a module-level constant
    can only ever be tested against whatever that constant currently holds, so the branch
    that refuses is unreachable from a test until the register happens to contain one.
    """
    return tuple(sorted(one.name for one in points if one.answer is Answer.PLUGIN))
