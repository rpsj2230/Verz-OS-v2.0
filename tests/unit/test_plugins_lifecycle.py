"""Install, enable, disable, upgrade, rollback, and the drain that makes an upgrade safe.

The two tests worth reading first are the one proving nothing can arrive enabled and the one
proving a run keeps the version it started on. Both are properties a boolean and a comment
would have expressed, and both are here as shapes instead.

Task ids: M29.2.3, M29.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.plugins.lifecycle import (
    PLUGIN_ADMIN,
    PLUGIN_NOT_AVAILABLE,
    TRANSITIONS,
    Drain,
    InFlight,
    Installed,
    LifecycleError,
    PluginState,
    administered,
    assert_transition,
    disable,
    enable,
    install,
    may_remove,
    rollback,
    state_of,
    still_running,
    upgrade,
    version_for,
)
from brain.plugins.manifest import PluginManifest

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
CORE = "1.2.0"


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


def _an_admin() -> EntitlementSet:
    return EntitlementSet(
        principal_id="operator",
        grants=(Grant(capability=PLUGIN_ADMIN, scope=Scope.unrestricted()),),
    )


def _somebody_else() -> EntitlementSet:
    return EntitlementSet(
        principal_id="anybody",
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
    )


def _installed(**overrides: object) -> Installed:
    manifest = _a_manifest()
    base: dict[str, object] = {
        "manifest": manifest,
        "state": PluginState.INSTALLED,
        "since": NOW,
        "history": (manifest.version,),
    }
    base.update(overrides)
    return Installed(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------ nothing arrives enabled
def test_there_is_no_transition_that_installs_a_plugin_already_running() -> None:
    """**The whole of "ships to everyone switched off", as a shape rather than a default.**
    A boolean defaulting to False is a value somebody sets, and the company that wrote the
    plugin is the company whose install has it set. There being no edge means no arrangement
    of the data produces a plugin running on a server where nobody enabled it.

    Asserted against the table rather than by calling `install`, because the claim is about
    what is reachable at all and not about what one function happens to return.

    Delete this and somebody adds the edge as a convenience for a first-run script."""
    assert (PluginState.ABSENT, PluginState.ENABLED) not in TRANSITIONS

    reachable_without_a_person = {to for source, to in TRANSITIONS if source is PluginState.ABSENT}
    assert reachable_without_a_person == {PluginState.INSTALLED}


def test_installing_leaves_a_plugin_switched_off() -> None:
    """The positive half of the rule above, and the one a reader would check first. Delete
    this and `install` could return ENABLED with the table still saying it should not."""
    record = install(_a_manifest(), core_version=CORE, at=NOW)

    assert record.state is PluginState.INSTALLED


def test_enabling_is_a_separate_act() -> None:
    """Two calls rather than one, so switching a plugin on is a thing a person did at a
    moment that is recorded. Delete this and enable becomes something install can imply."""
    record = enable(install(_a_manifest(), core_version=CORE, at=NOW), at=LATER)

    assert record.state is PluginState.ENABLED
    assert record.since == LATER


def test_a_transition_that_is_not_in_the_table_is_refused() -> None:
    """The table is the enforcement and `assert_transition` is the one reader of it, so the
    five verbs cannot each grow their own idea of what is allowed.

    Delete this and a sixth verb can move a plugin anywhere it likes."""
    with pytest.raises(LifecycleError, match="cannot go from"):
        assert_transition(PluginState.ABSENT, PluginState.ENABLED)


def test_the_ordinary_round_trip_is_allowed() -> None:
    """Install, enable, disable, enable again. Without this the transition table is
    satisfied by one that refuses everything, and a plugin could never be switched back on
    after being switched off.

    Delete this and the table can tighten to something no operator can work with."""
    record = enable(install(_a_manifest(), core_version=CORE, at=NOW), at=NOW)
    record = disable(record, at=LATER)
    assert record.state is PluginState.DISABLED

    record = enable(record, at=LATER)
    assert record.state is PluginState.ENABLED


def test_an_incompatible_plugin_is_refused_at_install_rather_than_at_enable() -> None:
    """An incompatible plugin on the disk is something an operator can look at and decide
    about. One refused at enable is a button that does not work.

    Delete this and the check drifts to the moment somebody is trying to switch it on."""
    with pytest.raises(LifecycleError, match="this core is"):
        install(_a_manifest(core_min="2.0.0", core_max="2.1.0"), core_version=CORE, at=NOW)


# --------------------------------------------------------------- the record itself
def test_a_record_cannot_say_a_plugin_is_absent() -> None:
    """`ABSENT` is what `state_of` answers when there is no record and when the caller may
    not be told. A record saying it would read to a person as installed.

    Delete this and the two meanings of absent become indistinguishable in storage."""
    with pytest.raises(LifecycleError, match="recorded as absent"):
        _installed(state=PluginState.ABSENT)


def test_a_record_whose_history_omits_its_own_version_is_refused() -> None:
    """A rollback reads the history, so a record at 1.1.0 whose history holds only 1.0.0
    would refuse a rollback to the version currently running.

    Delete this and the rollback rule can be defeated by a malformed record."""
    with pytest.raises(LifecycleError, match="history does not contain it"):
        _installed(history=("0.9.0",))


def test_a_state_change_with_no_timezone_is_refused() -> None:
    """A plugin record outlives the machine that wrote it, and a naive datetime compared
    against an aware one raises inside whichever function happens to compare them, a long
    way from the record that caused it.

    Delete this and a naive timestamp fails somewhere that cannot say why."""
    with pytest.raises(LifecycleError, match="no timezone"):
        _installed(since=datetime(2026, 9, 8, 12, 0))


# --------------------------------------------------------------- upgrade and rollback
def test_an_upgrade_moves_the_version_and_leaves_the_state_alone() -> None:
    """Upgrading is not a way to switch something on. An operator who disabled a plugin and
    then upgraded it has not asked for it back.

    Delete this and an upgrade quietly re-enables what somebody deliberately turned off."""
    record = disable(enable(_installed(), at=NOW), at=NOW)

    upgraded = upgrade(record, _a_manifest(version="1.1.0"), core_version=CORE, at=LATER)

    assert upgraded.state is PluginState.DISABLED
    assert upgraded.manifest.version == "1.1.0"
    assert upgraded.history == ("1.0.0", "1.1.0")


def test_an_upgrade_to_a_different_plugin_is_refused() -> None:
    """It would replace one plugin with another under the first one's name, and everything
    downstream would go on calling it by the name it was installed under.

    Delete this and a manifest with the wrong id silently swaps a plugin out."""
    with pytest.raises(LifecycleError, match="not an upgrade of"):
        upgrade(_installed(), _a_manifest(plugin_id="other"), core_version=CORE, at=LATER)


def test_an_upgrade_that_does_not_move_the_version_forward_is_refused() -> None:
    """It is either a rollback, which has its own function and its own rule, or a no-op
    recorded in the history as an upgrade.

    Delete this and a rollback can be performed through `upgrade`, skipping the check that a
    version has actually run here."""
    with pytest.raises(LifecycleError, match="is not later than"):
        upgrade(_installed(), _a_manifest(version="0.9.0"), core_version=CORE, at=LATER)


def test_an_upgrade_to_an_incompatible_version_is_refused() -> None:
    """The arriving manifest's range is checked, not the installed one's. A plugin that was
    compatible when installed says nothing about the version arriving.

    Delete this and an upgrade can install something this core cannot run."""
    arriving = _a_manifest(version="2.0.0", core_min="2.0.0", core_max="2.1.0")

    with pytest.raises(LifecycleError, match="this core is"):
        upgrade(_installed(), arriving, core_version=CORE, at=LATER)


def test_a_rollback_goes_only_to_a_version_this_install_has_run() -> None:
    """A version never installed here has never had its config supplied or its compatibility
    checked, so rolling back to it is an install performed at the moment somebody is trying
    to make an outage stop.

    Delete this and a rollback becomes the least tested install path in the system, taken
    under the most pressure."""
    record = upgrade(_installed(), _a_manifest(version="1.1.0"), core_version=CORE, at=LATER)

    with pytest.raises(LifecycleError, match="has never run on this install"):
        rollback(record, _a_manifest(version="0.9.0"), at=LATER)


def test_a_rollback_to_a_version_that_did_run_is_allowed_and_keeps_the_history() -> None:
    """The positive half. The history is not truncated, because rolling back and then
    forward again is two ordinary moves and a history that forgot the newer version would
    refuse the second one.

    Delete this and the rollback rule is satisfied by refusing every rollback."""
    record = upgrade(_installed(), _a_manifest(version="1.1.0"), core_version=CORE, at=LATER)

    back = rollback(record, _a_manifest(version="1.0.0"), at=LATER)

    assert back.manifest.version == "1.0.0"
    assert back.history == ("1.0.0", "1.1.0")


def test_a_rollback_to_another_plugin_is_a_replacement_and_is_refused() -> None:
    """The same argument as the upgrade check, and it needs its own test because the history
    of a different plugin could coincidentally contain the version asked for.

    Delete this and a rollback can swap a plugin for another whose versions happen to line
    up."""
    with pytest.raises(LifecycleError, match="not a version of"):
        rollback(_installed(), _a_manifest(plugin_id="other"), at=LATER)


# ------------------------------------------------------------------------ the drain
def test_work_already_running_finishes_on_the_version_it_started_on() -> None:
    """**This is M29.2.4.** A run that began against one version and finishes against the
    next has observed a data shape the arriving version was never tested against, halfway
    through, and nothing reports it: the run completes and the answer is plausible.

    Delete this and an upgrade becomes one event, which is the state where the failure is
    invisible."""
    drain = Drain(
        plugin_id="probe",
        retiring="1.0.0",
        arriving="1.1.0",
        running=(InFlight(run_id="run-a", version="1.0.0"),),
    )

    assert version_for(drain, "run-a") == "1.0.0"
    assert version_for(drain, "run-b") == "1.1.0"


def test_the_old_version_may_not_be_removed_while_anything_still_names_it() -> None:
    """The whole of the drain is one comparison, and the difficulty is never the arithmetic:
    it is that somebody removed the old version before asking.

    Delete this and `may_remove` can return True unconditionally, which is exactly what a
    deployment script would then do."""
    drain = Drain(
        plugin_id="probe",
        retiring="1.0.0",
        arriving="1.1.0",
        running=(InFlight(run_id="run-a", version="1.0.0"),),
    )

    assert still_running(drain) == ("run-a",)
    assert not may_remove(drain)


def test_an_empty_drain_and_one_holding_only_new_work_are_both_finished() -> None:
    """The positive case, and the second half of it matters on its own: work that started
    after the upgrade names the arriving version and must not hold the drain open, or an
    upgrade on a busy system never completes.

    Delete this and `may_remove` could return False always with the suite green."""
    empty = Drain(plugin_id="probe", retiring="1.0.0", arriving="1.1.0")
    only_new = Drain(
        plugin_id="probe",
        retiring="1.0.0",
        arriving="1.1.0",
        running=(InFlight(run_id="run-b", version="1.1.0"),),
    )

    assert may_remove(empty)
    assert may_remove(only_new)
    assert still_running(only_new) == ()


def test_a_drain_from_a_version_to_itself_is_refused() -> None:
    """It finishes immediately and reads in a log as an upgrade that completed, which is the
    worst available combination: no work is moved and the record says it was.

    Delete this and a no-op upgrade leaves a drain entry claiming success."""
    with pytest.raises(LifecycleError, match="to itself"):
        Drain(plugin_id="probe", retiring="1.0.0", arriving="1.0.0")


def test_a_run_with_no_id_could_never_be_found_again() -> None:
    """A drain ends when nothing in flight names the old version, and a run with a blank id
    is one nothing can match, so the drain would either never end or end wrongly.

    Delete this and a blank id sits in a drain holding it open for ever."""
    with pytest.raises(LifecycleError, match="could never end"):
        InFlight(run_id="  ", version="1.0.0")


# ---------------------------------------------------- denied and absent are one answer
def test_a_caller_who_may_not_administer_plugins_is_told_nothing_exists() -> None:
    """**DENIED and ABSENT are indistinguishable.** Two different answers would let anybody
    with a console tab enumerate which plugins a company runs, one name at a time, and which
    plugins a company runs is a fact about that company.

    Delete this and the register becomes readable by anybody who can guess a name."""
    records = {"probe": _installed(state=PluginState.ENABLED)}

    assert state_of("probe", records, reach=_somebody_else(), now=NOW) is PluginState.ABSENT
    assert state_of("nothing", records, reach=_somebody_else(), now=NOW) is PluginState.ABSENT


def test_an_administrator_is_told_the_real_state() -> None:
    """The positive half, without which `state_of` is satisfied by returning ABSENT always
    and no console could show anything.

    Delete this and the refusal above can widen to everybody."""
    records = {"probe": _installed(state=PluginState.ENABLED)}

    assert state_of("probe", records, reach=_an_admin(), now=NOW) is PluginState.ENABLED
    assert state_of("other", records, reach=_an_admin(), now=NOW) is PluginState.ABSENT


def test_the_refusal_sentence_names_nothing() -> None:
    """A refusal that varied with the plugin, the reason or a count would be an enumeration
    tool. `brain.ops.automation_piece.TOOL_NOT_AVAILABLE` is the same construction, and the
    property is that the constant has nothing interpolated into it.

    Delete this and somebody helpfully adds the plugin name to the message."""
    assert "{" not in PLUGIN_NOT_AVAILABLE
    assert "probe" not in PLUGIN_NOT_AVAILABLE
    assert PLUGIN_NOT_AVAILABLE.strip() == PLUGIN_NOT_AVAILABLE


def test_a_caller_who_may_not_administer_sees_no_plugin_list_at_all() -> None:
    """Not a filtered list, because a filtered list is a count of hidden items with the
    count left as an exercise. Administering plugins is one capability, so a caller either
    sees the register or does not.

    Delete this and somebody returns the subset they are allowed, which is the subtraction
    CLAUDE.md warns about."""
    records = {"probe": _installed(), "other": _installed()}

    assert administered(records, reach=_somebody_else(), now=NOW) == ()
    assert administered(records, reach=_an_admin(), now=NOW) == ("other", "probe")


def test_an_expired_administrator_holds_nothing() -> None:
    """An expired principal's grants stay on file and the set knows it is expired, so the
    time is what refuses rather than the grants. `now` is a parameter here for exactly this
    test to be possible.

    Delete this and an operator whose access ended keeps reading the plugin register."""
    expiring = EntitlementSet(
        principal_id="operator",
        grants=(Grant(capability=PLUGIN_ADMIN, scope=Scope.unrestricted()),),
        not_after=NOW,
    )
    records = {"probe": _installed(state=PluginState.ENABLED)}

    assert state_of("probe", records, reach=expiring, now=LATER) is PluginState.ABSENT
    assert administered(records, reach=expiring, now=LATER) == ()
