"""Install, enable, disable, upgrade, rollback, and the drain that makes an upgrade safe.

**A plugin cannot arrive switched on, and that is a shape rather than a default.** CLAUDE.md
says a new feature "ships to everyone switched off", and the ordinary way to keep that promise
is a boolean defaulting to False. A boolean is a value somebody sets, and the company that
wrote the plugin is the company whose install has it set. So there is no transition from
`ABSENT` to `ENABLED` in `TRANSITIONS` at all: installing puts a plugin on the server and
enabling is a separate act by a person on that server. `brain.install` makes the same argument
about defaults belonging to nobody, and this is the version of it that a table cannot get
wrong.

**An upgrade is three events and the middle one is the drain.** The new version becomes the
one new work is given, the old version keeps the work already running, and only when nothing
in flight still names the old version may it be removed. Collapsing that into one event is
what produces the failure `brain.ops.queue` describes from the other direction: a previous
image draining a queue nothing enqueues onto. Here it would be the reverse and worse, a run
that started against version 1.2.0 finishing against 1.3.0's code, which is a plugin observing
a data shape from a version it was never tested against, halfway through a piece of work.

`version_for` is where that lives and it is deliberately the only place: a run already in
flight keeps the version it started on, and everything else gets the arriving one.

**A rollback goes only to a version this install has actually run.** Not to any older version
the author published. A version that has never been installed here has never had its config
supplied or its compatibility checked against this core, so rolling back to it is an install
wearing a rollback's clothes, performed at the moment somebody is trying to make an outage
stop. `rollback` refuses it, and the refusal names the versions that are available.

**DENIED and ABSENT are one answer.** `state_of` returns `ABSENT` for a plugin that is not
installed and for one the caller may not administer, and `PLUGIN_NOT_AVAILABLE` has nothing
interpolated into it, following `brain.ops.automation_piece.TOOL_NOT_AVAILABLE`. Two different
answers would let anybody with a console tab enumerate which plugins a company runs, one name
at a time, and which plugins a company runs is a fact about that company.

Rejected: a `FAILED` state for a plugin whose install did not complete. It reads as diligence
and it is a fourth answer to a question that has three, and the one place it would be observed
is the same place a person is deciding whether to enable something. An install either happened
or it did not.

Task ids: M29.2.3, M29.2.4
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.entitlement import Capability, EntitlementSet
from brain.plugins.manifest import PluginManifest

#: What administering plugins takes. One capability rather than one per verb, because install,
#: enable and rollback are the same authority exercised at different moments, and splitting
#: them would produce a person who may enable and may not disable.
PLUGIN_ADMIN: Final = Capability(value="admin:plugin")

#: The one sentence a caller ever gets about a plugin they may not be told about.
#:
#: A module-level constant with nothing interpolated into it, so it cannot come to vary with
#: the plugin, the reason or a count. `brain.ops.automation_piece.TOOL_NOT_AVAILABLE` is the
#: same construction for the same reason and the argument is worth restating: a refusal that
#: differed between "it is installed and you may not know" and "there is no such plugin" is an
#: enumeration tool, and the person holding it needs no permission at all to use it.
PLUGIN_NOT_AVAILABLE: Final = "no such plugin is available here"


class LifecycleError(Exception):
    """A lifecycle transition was asked for that cannot be made safe.

    Outside `brain.core.errors` for the reason the rest of this package's errors are: this is
    an operator holding it wrong, at install time, and it belongs in front of them.
    """


class PluginState(enum.StrEnum):
    """Where a plugin is on one install.

    `ABSENT` is a state rather than the absence of a record, because it is what a caller who
    may not be told anything is given, and a function that returned None for both would make
    the two distinguishable by their types.
    """

    ABSENT = "absent"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"


#: Every transition that exists. Anything not in here is refused.
#:
#: **Read the absences.** There is no `ABSENT -> ENABLED`, which is the whole of "ships
#: switched off". There is no `ENABLED -> INSTALLED`, because going back to installed from
#: enabled is what `DISABLED` means and two names for one state is how a console comes to show
#: a plugin as off while it is running.
TRANSITIONS: Final[frozenset[tuple[PluginState, PluginState]]] = frozenset(
    {
        (PluginState.ABSENT, PluginState.INSTALLED),
        (PluginState.INSTALLED, PluginState.ENABLED),
        (PluginState.ENABLED, PluginState.DISABLED),
        (PluginState.DISABLED, PluginState.ENABLED),
        (PluginState.DISABLED, PluginState.ABSENT),
    }
)

#: Why the boolean is absent rather than defaulted to False.
NOTHING_ARRIVES_ENABLED_BECAUSE_THERE_IS_NO_EDGE_THAT_WOULD_DO_IT: Final = (
    "A flag defaulting to off is a value somebody sets, and the company that wrote the plugin "
    "is the company whose install has it set. Removing the edge from ABSENT to ENABLED means "
    "there is no arrangement of the data that produces a plugin running on a server where "
    "nobody enabled it, which is a stronger claim than any default can make."
)

#: Why an upgrade is not one event.
IN_FLIGHT_WORK_FINISHES_ON_THE_VERSION_IT_STARTED_ON: Final = (
    "A run that began against one version of a plugin and finishes against the next has "
    "observed a data shape the arriving version was never tested against, halfway through. "
    "Nothing reports it: the run completes, the answer is plausible, and the only trace is a "
    "version number in a log nobody reads. So the arriving version takes new work, the "
    "retiring version keeps what it already has, and removal waits for the second to empty."
)

#: Why a rollback is not an install.
A_VERSION_THIS_INSTALL_HAS_NEVER_RUN_IS_NOT_SOMEWHERE_TO_ROLL_BACK_TO: Final = (
    "A version that has never been installed here has never had its config supplied or its "
    "compatibility checked against this core. Rolling back to it is an install performed at "
    "the moment somebody is trying to make an outage stop, which is the worst moment "
    "available to find out that a required config key was never set."
)


def _assert_aware(when: datetime, what: str) -> None:
    """Refuse a naive timestamp, at the boundary rather than at the comparison.

    A naive datetime compared against an aware one raises inside whichever function happens to
    compare them, which puts the failure a long way from the record that caused it.
    """
    if when.tzinfo is None:
        msg = f"{what} has no timezone, and a plugin record outlives the machine that wrote it"
        raise LifecycleError(msg)


@dataclass(frozen=True)
class Installed:
    """One plugin on one install: which version, in which state, since when.

    The manifest is carried rather than the plugin id alone, because every question worth
    asking of this record is a question about the manifest: which point it plugs into, which
    core versions it admits, what config it needs. A record holding an id and a version would
    send every reader back to a registry to answer them.
    """

    manifest: PluginManifest
    state: PluginState
    since: datetime
    #: Every version of this plugin this install has actually run, oldest first.
    history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _assert_aware(self.since, f"{self.manifest.plugin_id}'s state change")
        if self.state is PluginState.ABSENT:
            msg = (
                f"{self.manifest.plugin_id} is recorded as absent; absent is what state_of "
                "answers when there is no record, and a record saying it is what a person "
                "would read as installed"
            )
            raise LifecycleError(msg)
        if self.manifest.version not in self.history:
            msg = (
                f"{self.manifest.plugin_id} is at {self.manifest.version} and its history does "
                "not contain it, so a rollback would refuse the version currently running"
            )
            raise LifecycleError(msg)


def assert_transition(current: PluginState, wanted: PluginState) -> None:
    """Refuse a transition that is not in `TRANSITIONS`.

    A single function rather than a check inside each of the five verbs, because the five
    verbs are where somebody adds the sixth, and a table is the thing a reader can check
    against the paragraph above it. See
    `NOTHING_ARRIVES_ENABLED_BECAUSE_THERE_IS_NO_EDGE_THAT_WOULD_DO_IT`.
    """
    if (current, wanted) not in TRANSITIONS:
        msg = (
            f"a plugin cannot go from {current} to {wanted}; the transitions that exist are "
            f"{sorted((one.value, two.value) for one, two in TRANSITIONS)}"
        )
        raise LifecycleError(msg)


def install(manifest: PluginManifest, *, core_version: str, at: datetime) -> Installed:
    """Put a plugin on this install, switched off.

    The compatibility range is checked here and not at enable, because an incompatible plugin
    on the disk is a thing an operator can look at and decide about, whereas an incompatible
    plugin refused at enable is a button that does not work.
    """
    if not manifest.admits(core_version):
        msg = (
            f"{manifest.plugin_id} declares {manifest.core_min} to {manifest.core_max} and "
            f"this core is {core_version}"
        )
        raise LifecycleError(msg)
    assert_transition(PluginState.ABSENT, PluginState.INSTALLED)
    return Installed(
        manifest=manifest,
        state=PluginState.INSTALLED,
        since=at,
        history=(manifest.version,),
    )


def enable(record: Installed, *, at: datetime) -> Installed:
    """Switch a plugin on. A separate act, by a person, on the client's own server."""
    assert_transition(record.state, PluginState.ENABLED)
    return Installed(
        manifest=record.manifest,
        state=PluginState.ENABLED,
        since=at,
        history=record.history,
    )


def disable(record: Installed, *, at: datetime) -> Installed:
    """Switch a plugin off, leaving it installed.

    Disabling rather than removing is the reversible half, and it is what a rollback needs:
    the history survives, so the versions this install has run are still known.
    """
    assert_transition(record.state, PluginState.DISABLED)
    return Installed(
        manifest=record.manifest,
        state=PluginState.DISABLED,
        since=at,
        history=record.history,
    )


def upgrade(
    record: Installed, arriving: PluginManifest, *, core_version: str, at: datetime
) -> Installed:
    """Move a plugin to a later version of itself.

    Three refusals, and the first two are about identity rather than about the upgrade. A
    manifest for a different plugin is a mistake that would silently replace one plugin with
    another under the first one's name; a version that is not later is either a rollback,
    which has its own function and its own rule, or a no-op recorded as an upgrade.

    The state is not changed here. An upgrade of a disabled plugin leaves it disabled, because
    upgrading is not a way to switch something on, and an operator who disabled a plugin and
    then upgraded it has not asked for it back.
    """
    if arriving.plugin_id != record.manifest.plugin_id:
        msg = (
            f"{arriving.plugin_id} is not an upgrade of {record.manifest.plugin_id}; it would "
            "replace one plugin with another under the first one's name"
        )
        raise LifecycleError(msg)
    if not arriving.is_newer_than(record.manifest):
        msg = (
            f"{arriving.plugin_id} {arriving.version} is not later than "
            f"{record.manifest.version}; a rollback is a different act with a different rule"
        )
        raise LifecycleError(msg)
    if not arriving.admits(core_version):
        msg = (
            f"{arriving.plugin_id} {arriving.version} declares {arriving.core_min} to "
            f"{arriving.core_max} and this core is {core_version}"
        )
        raise LifecycleError(msg)
    return Installed(
        manifest=arriving,
        state=record.state,
        since=at,
        history=(*record.history, arriving.version),
    )


def rollback(record: Installed, previous: PluginManifest, *, at: datetime) -> Installed:
    """Return a plugin to a version this install has already run.

    See `A_VERSION_THIS_INSTALL_HAS_NEVER_RUN_IS_NOT_SOMEWHERE_TO_ROLL_BACK_TO`. The history
    is not truncated: rolling back from 1.3.0 to 1.2.0 and then forward again is two ordinary
    moves, and a history that forgot 1.3.0 would refuse the second one.
    """
    if previous.plugin_id != record.manifest.plugin_id:
        msg = (
            f"{previous.plugin_id} is not a version of {record.manifest.plugin_id}, so this "
            "is a replacement rather than a rollback"
        )
        raise LifecycleError(msg)
    if previous.version not in record.history:
        msg = (
            f"{previous.plugin_id} {previous.version} has never run on this install; the "
            f"versions it has run are {list(record.history)}. "
            f"{A_VERSION_THIS_INSTALL_HAS_NEVER_RUN_IS_NOT_SOMEWHERE_TO_ROLL_BACK_TO}"
        )
        raise LifecycleError(msg)
    return Installed(
        manifest=previous,
        state=record.state,
        since=at,
        history=record.history,
    )


@dataclass(frozen=True)
class InFlight:
    """One piece of work already running, and the plugin version it started against."""

    run_id: str
    version: str

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "a run with no id cannot be found again, so a drain could never end"
            raise LifecycleError(msg)


@dataclass(frozen=True)
class Drain:
    """An upgrade in progress: which version is retiring, which is arriving, what is running.

    A value rather than a process, for the reason `brain.ops.limits` holds the sliding window
    and no connection: the question "may the old version be removed yet" has a boundary case
    that is always wrong, and it cannot be tested through something that opens a socket.
    """

    plugin_id: str
    retiring: str
    arriving: str
    running: tuple[InFlight, ...] = ()

    def __post_init__(self) -> None:
        if self.retiring == self.arriving:
            msg = (
                f"{self.plugin_id} is draining {self.retiring} to itself, which finishes "
                "immediately and reads in a log as an upgrade that completed"
            )
            raise LifecycleError(msg)


def still_running(drain: Drain) -> tuple[str, ...]:
    """Every run still on the retiring version, sorted.

    The ids rather than a count, and that is the one place in this package where naming things
    is right: a drain that will not finish is an operator's problem and the runs holding it
    open are what they need. Nobody outside the operator sees this.
    """
    return tuple(sorted(one.run_id for one in drain.running if one.version == drain.retiring))


def may_remove(drain: Drain) -> bool:
    """True when nothing in flight still names the retiring version.

    See `IN_FLIGHT_WORK_FINISHES_ON_THE_VERSION_IT_STARTED_ON`. This is the whole of M29.2.4
    and it is one comparison, which is the point: the difficulty of a drain is never the
    arithmetic, it is that somebody removed the old version before asking.
    """
    return not still_running(drain)


def version_for(drain: Drain, run_id: str) -> str:
    """Which version a piece of work runs against during the drain.

    A run already in flight keeps the version it started on; anything else gets the arriving
    one. The two branches are the whole semantic of a drain, and they are here rather than at
    each call site so that a caller cannot accidentally implement half of it.
    """
    for one in drain.running:
        if one.run_id == run_id:
            return one.version
    return drain.arriving


def state_of(
    plugin_id: str,
    records: dict[str, Installed],
    *,
    reach: EntitlementSet,
    now: datetime,
) -> PluginState:
    """What a caller may be told about one plugin, which is `ABSENT` unless they administer.

    Both refusals collapse into `ABSENT` and neither says which it was. See
    `PLUGIN_NOT_AVAILABLE`, and `brain.core.errors.to_public`, which makes the same collapse
    for the same reason on every other path in this system.
    """
    if not reach.holds(PLUGIN_ADMIN, now):
        return PluginState.ABSENT
    record = records.get(plugin_id)
    if record is None:
        return PluginState.ABSENT
    return record.state


def administered(
    records: dict[str, Installed], *, reach: EntitlementSet, now: datetime
) -> tuple[str, ...]:
    """Every plugin this caller may be told about, sorted, or nothing at all.

    An empty tuple rather than a partial list, because there is no partial case: administering
    plugins is one capability, so a caller either sees the register or does not, and a filtered
    view would be a count of hidden items with the count left as an exercise.
    """
    if not reach.holds(PLUGIN_ADMIN, now):
        return ()
    return tuple(sorted(records))
