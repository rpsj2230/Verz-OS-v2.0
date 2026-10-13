"""Install checks for the plugin registry: a manifest is recorded and moved through its states by an
administrator, the interfaces a plugin may implement are listed with the tier each runs at, and a
plugin is handed the caller's own reach and nothing a caller could not see.

Every check calls the route the Features and plugins page calls, as the reader that page serves, in
the shape `brain.ops.acceptance_operations_console` sets out
(`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`): an application holding the check's sessions, and the
asking the gate would hand the route for a reserved person on the console, with a second factor for
anybody pressing an administrator's button.

**The stand-in plugin is a manifest and nothing else.** No code is named, fetched or run, because
none is: `brain.plugin_routes` records the document and moves its state, and no runner exists for
the points that take code. What is proved is the registry's half on an install: the tables of
migration 0032 accept what the lifecycle decides, in the states it allows, with the document that
ran kept for ever. **Nothing is proved about a plugin running**, and these checks do not claim
M29.2.4 (a drain) or M29.2.5 (an isolation tier enforced by a host), which need one.

**The switch is set explicitly in both directions and never assumed.** An install that already
has `plugin_registry` on is not the empty state the check might have been written against, so the
check turns it off through the route, shows the four writes that open a state refused, and turns it
on, which is the same set of acts on either kind of install and is rolled back with the rest.

Task ids: M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12, M29.2.1, M29.2.2, M29.2.3, M29.2.6
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2230

A, _B = RESERVED_DEPARTMENTS

#: The authorities the checks' administrators hold. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
ADMINISTERS_PLUGINS: Final = "admin:plugin"
SWITCHES_FEATURES: Final = "admin:feature"

#: A capability the stand-in plugin asks its caller to hold, and one nobody on the install holds.
HELD: Final = "read:ticket.status"
NOT_HELD: Final = "read:payroll.total"

#: What the six interfaces named by M29.1 are on this release: leaf, tier. Restated here so a
#: change to the register fails the check rather than moving with it.
INTERFACES: Final = {
    "connector": ("M29.1.2", "sidecar"),
    "skill": ("M29.1.3", "sandbox"),
    "template": ("M29.1.4", "in_process"),
    "model_provider": ("M29.1.5", "sidecar"),
    "field_classifier": ("M29.1.7", "sandbox"),
    "notification_sink": ("M29.1.12", "sidecar"),
}

NO_CORE_VERSION: Final = (
    "this install carries the product as a package that cannot say its own version, which a "
    "manifest's compatibility range is judged against"
)
NOT_LISTED_FOR_AN_ADMINISTRATOR: Final = "an administrator of plugins was not shown the registry"
LISTED_FOR_ANYBODY: Final = "a person without the authority over plugins was shown the registry"
WRITES_ALLOWED_WITH_THE_SWITCH_OFF: Final = (
    "a write that opens a plugin's state was accepted while the registry was switched off"
)
A_MANIFEST_WAS_NOT_RECORDED: Final = "a manifest the registry should accept was not recorded"
NOT_STORED: Final = "a recorded plugin was not in the install's tables with the document it ran"
A_BAD_MANIFEST_WAS_RECORDED: Final = "a manifest the registry must refuse was recorded"
THE_STATE_DID_NOT_MOVE: Final = "a plugin did not move to the state its transition leads to"
THE_UPGRADE_CHANGED_THE_STATE: Final = "an upgrade changed whether a plugin was switched on"
A_VERSION_WAS_FORGOTTEN: Final = "a version a plugin ran was not kept after it moved on"
A_ROLLBACK_TO_A_STRANGER_WAS_ACCEPTED: Final = (
    "a plugin was returned to a version this install never ran"
)
AN_ENABLED_PLUGIN_WAS_REMOVED: Final = "a plugin that was switched on was removed"
A_REMOVED_PLUGIN_WAS_LISTED: Final = "a removed plugin was still listed on the install"
AN_INTERFACE_IS_MISSING: Final = "an interface a plugin may implement was not listed as one"
AN_INTERFACE_DIFFERS: Final = "an interface was listed with another tier or leaf than its register"
AN_INTERFACE_HAS_NO_CONTRACT: Final = "an interface names a contract no module defines"
THE_REACH_WAS_NOT_THE_CALLERS: Final = (
    "a plugin that could run was not handed the reach of the person who asked"
)
A_PLUGIN_WAS_PLANNED_FOR_A_STRANGER: Final = (
    "a plugin that needs a capability the caller lacks was planned to run"
)
THE_REFUSAL_SAID_MORE_THAN_ONE_THING: Final = (
    "a refusal named something other than the one sentence every refusal is"
)
AN_UNREDACTED_TYPE_WAS_ACCEPTED: Final = (
    "a plugin to be handed a value the gate has not walked was recorded"
)


def _manifest(h: Harness, version: str = "1.0.0", **overrides: Any) -> dict[str, Any]:
    """The stand-in's manifest: this run's name, an existing point, a capability asked for."""
    document: dict[str, Any] = {
        "plugin_id": f"acceptance-{h.run}".lower(),
        "version": version,
        "point": "connector",
        "requires": [{"value": HELD}],
        "core_min": "0.0.1",
        "core_max": "9999.0.0",
    }
    document.update(overrides)
    return document


async def _administrator(h: Harness, role: str = "plugins") -> str:
    """A reserved principal holding the plugin authority and the feature one, over everything, and
    the capability the stand-in asks its caller to hold."""
    made = h.principal(A, role)
    await h.person(
        made,
        department=A,
        grants=(
            (ADMINISTERS_PLUGINS, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
            (HELD, Scope.unrestricted()),
        ),
    )
    return made


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    """The registry's switch, through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features import PLUGIN_REGISTRY

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            PLUGIN_REGISTRY.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


class _Routes:
    """The plugin routes, each asked as one reserved person and one way (`strong` or not)."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.console = console_for(h)

    async def page(self, who: str) -> Any:
        from brain.plugin_routes import plugins

        return await plugins(self.console.request(), await asking_as(self.h, who, strong=True))

    async def install(self, who: str, manifest: dict[str, Any]) -> Any:
        from brain.plugin_routes import ManifestAsked, install_plugin

        return await install_plugin(
            self.console.request("POST"),
            ManifestAsked(manifest=manifest),
            await asking_as(self.h, who, strong=True),
        )

    async def move(self, who: str, verb: str, plugin_id: str) -> Any:
        from brain import plugin_routes

        call = {
            "enable": plugin_routes.enable_plugin,
            "disable": plugin_routes.disable_plugin,
            "remove": plugin_routes.remove_plugin,
        }[verb]
        return await call(
            self.console.request("POST"), plugin_id, await asking_as(self.h, who, strong=True)
        )

    async def upgrade(self, who: str, plugin_id: str, manifest: dict[str, Any]) -> Any:
        from brain.plugin_routes import ManifestAsked, upgrade_plugin

        return await upgrade_plugin(
            self.console.request("POST"),
            plugin_id,
            ManifestAsked(manifest=manifest),
            await asking_as(self.h, who, strong=True),
        )

    async def rollback(self, who: str, plugin_id: str, version: str) -> Any:
        from brain.plugin_routes import RollbackAsked, rollback_plugin

        return await rollback_plugin(
            self.console.request("POST"),
            plugin_id,
            RollbackAsked(version=version),
            await asking_as(self.h, who, strong=True),
        )

    async def plan(self, who: str, plugin_id: str) -> Any:
        from brain.plugin_routes import PlanAsked, plan_plugin

        return await plan_plugin(
            self.console.request("POST"),
            plugin_id,
            PlanAsked(),
            await asking_as(self.h, who, strong=True),
        )


async def _recorded(routes: _Routes, who: str, manifest: dict[str, Any]) -> Any:
    """A manifest the registry should accept, recorded, or the check's sentence when it was not."""
    from brain.core.errors import Absent

    try:
        return await routes.install(who, manifest)
    except Absent:
        raise CheckFailedError(A_MANIFEST_WAS_NOT_RECORDED) from None


def _core_known() -> None:
    from brain.plugin_routes import core_version

    if core_version() is None:
        raise CheckNotRunError(NO_CORE_VERSION)


async def _stored(h: Harness, plugin_id: str) -> tuple[str, str, int]:
    """The install row's version and state, and how many versions the install has run."""
    row = (
        await h.execute(
            text(
                "SELECT version, state FROM ops.plugin_install"
                " WHERE plugin_id = :id AND removed_at IS NULL"
            ).bindparams(id=plugin_id)
        )
    ).one_or_none()
    ran = (
        await h.execute(
            text("SELECT count(*) FROM ops.plugin_version WHERE plugin_id = :id").bindparams(
                id=plugin_id
            )
        )
    ).scalar_one()
    if row is None:
        raise CheckFailedError(NOT_STORED)
    return str(row[0]), str(row[1]), int(ran)


# ----------------------------------------- 1. recorded and moved (M29.2.1, M29.2.2, M29.2.3)
@check(
    leaves=("M29.2.1", "M29.2.2", "M29.2.3"),
    sentence=(
        "An administrator of plugins records a stand-in manifest through the console's route: "
        "the writes that open a state are refused while the switch is off; the plugin arrives "
        "switched off, is enabled, upgraded, returned and disabled, and every version it ran is "
        "kept; a manifest asking for reach or for a point no plugin may take is refused."
    ),
)
async def a_plugin_is_recorded_and_moved_through_its_states(h: Harness) -> None:
    from brain.plugin_routes import PluginView

    _core_known()
    await h.found_departments()
    admin, other = await _administrator(h), h.principal(A, "other")
    await h.person(other, department=A)
    routes = _Routes(h)
    if not await refused(routes.page(other)):
        raise CheckFailedError(LISTED_FOR_ANYBODY)

    manifest = _manifest(h)
    plugin_id = str(manifest["plugin_id"])
    await _switched(h, admin, on=False, n=1)
    opening_writes: tuple[Callable[[], Coroutine[Any, Any, Any]], ...] = (
        lambda: routes.install(admin, manifest),
        lambda: routes.upgrade(admin, plugin_id, manifest),
        lambda: routes.rollback(admin, plugin_id, "1.0.0"),
        lambda: routes.move(admin, "enable", plugin_id),
    )
    for opening in opening_writes:
        if not await refused(opening()):
            raise CheckFailedError(WRITES_ALLOWED_WITH_THE_SWITCH_OFF)
    await _switched(h, admin, on=True, n=2)

    # What the registry must refuse, in the words the product's own rules give.
    for bad in (
        {**manifest, "grants": [HELD]},
        {**manifest, "point": "storage_backend"},
        {**manifest, "version": "not a version"},
    ):
        if not await refused(routes.install(admin, bad)):
            raise CheckFailedError(A_BAD_MANIFEST_WAS_RECORDED)

    made: PluginView = await _recorded(routes, admin, manifest)
    if made.state != "installed" or made.version != "1.0.0":
        raise CheckFailedError(A_MANIFEST_WAS_NOT_RECORDED)
    if await _stored(h, plugin_id) != ("1.0.0", "installed", 1):
        raise CheckFailedError(NOT_STORED)
    if not await refused(routes.install(admin, manifest)):
        raise CheckFailedError(A_BAD_MANIFEST_WAS_RECORDED)
    listed = await routes.page(admin)
    if not any(one.plugin_id == plugin_id for one in listed.plugins):
        raise CheckFailedError(NOT_LISTED_FOR_AN_ADMINISTRATOR)

    if (await routes.move(admin, "enable", plugin_id)).state != "enabled":
        raise CheckFailedError(THE_STATE_DID_NOT_MOVE)
    later = await routes.upgrade(admin, plugin_id, _manifest(h, "1.1.0"))
    if later.version != "1.1.0":
        raise CheckFailedError(THE_STATE_DID_NOT_MOVE)
    if later.state != "enabled":
        raise CheckFailedError(THE_UPGRADE_CHANGED_THE_STATE)
    if not await refused(routes.upgrade(admin, plugin_id, _manifest(h, "1.0.0"))):
        raise CheckFailedError(A_BAD_MANIFEST_WAS_RECORDED)
    if not await refused(routes.rollback(admin, plugin_id, "9.9.9")):
        raise CheckFailedError(A_ROLLBACK_TO_A_STRANGER_WAS_ACCEPTED)
    back = await routes.rollback(admin, plugin_id, "1.0.0")
    if back.version != "1.0.0" or back.history != ["1.0.0", "1.1.0"]:
        raise CheckFailedError(A_VERSION_WAS_FORGOTTEN)

    if not await refused(routes.move(admin, "remove", plugin_id)):
        raise CheckFailedError(AN_ENABLED_PLUGIN_WAS_REMOVED)
    if (await routes.move(admin, "disable", plugin_id)).state != "disabled":
        raise CheckFailedError(THE_STATE_DID_NOT_MOVE)
    if await _stored(h, plugin_id) != ("1.0.0", "disabled", 2):
        raise CheckFailedError(A_VERSION_WAS_FORGOTTEN)
    await routes.move(admin, "remove", plugin_id)
    if any(one.plugin_id == plugin_id for one in (await routes.page(admin)).plugins):
        raise CheckFailedError(A_REMOVED_PLUGIN_WAS_LISTED)


# ------------------------------------------------ 2. the interfaces (M29.1.2 to M29.1.12)
@check(
    leaves=("M29.1.2", "M29.1.3", "M29.1.4", "M29.1.5", "M29.1.7", "M29.1.12"),
    sentence=(
        "The plugin registry lists the connector, skill, template, model provider, field "
        "classifier and notification sink as interfaces a plugin may implement, each with the "
        "leaf that names it, the tier it would run at and a contract that a module of this "
        "release defines."
    ),
)
async def plugin_interfaces_are_listed_with_their_contracts(
    h: Harness,
) -> None:
    await h.found_departments()
    admin = await _administrator(h)
    listed = {one.name: one for one in (await _Routes(h).page(admin)).points}
    for name, (leaf, tier) in INTERFACES.items():
        point = listed.get(name)
        if point is None or point.answer != "plugin":
            raise CheckFailedError(AN_INTERFACE_IS_MISSING)
        if (point.leaf, point.tier) != (leaf, tier):
            raise CheckFailedError(AN_INTERFACE_DIFFERS)
        module_name, _, symbol = point.contract.partition(":")
        try:
            defined = hasattr(importlib.import_module(module_name), symbol)
        except ImportError:
            defined = False
        if not defined:
            raise CheckFailedError(AN_INTERFACE_HAS_NO_CONTRACT)


# ----------------------------------------------- 3. the core contract (M29.2.6)
@check(
    leaves=("M29.2.6",),
    sentence=(
        "A stand-in plugin asking for a capability the caller holds is planned to run with a "
        "reach that hashes the same as the caller's own; one asking for a capability the caller "
        "lacks is refused with the one sentence every refusal is and naming nothing; and a "
        "plugin to be handed a value the gate has not walked is refused when it is recorded."
    ),
)
async def a_plugin_gets_the_callers_own_reach_and_nothing_unredacted(h: Harness) -> None:
    from brain.plugins.lifecycle import PLUGIN_NOT_AVAILABLE

    _core_known()
    await h.found_departments()
    admin = await _administrator(h, "contract")
    routes = _Routes(h)
    await _switched(h, admin, on=True, n=3)
    suffix = h.run.lower()
    can = _manifest(h)
    cannot = _manifest(h, requires=[{"value": NOT_HELD}], plugin_id=f"acceptance-{suffix}-no")
    handed = _manifest(h, accepts=["RedactionTrace"], plugin_id=f"acceptance-{suffix}-raw")
    if not await refused(routes.install(admin, handed)):
        raise CheckFailedError(AN_UNREDACTED_TYPE_WAS_ACCEPTED)
    await _recorded(routes, admin, can)
    await _recorded(routes, admin, cannot)

    ran = await routes.plan(admin, str(can["plugin_id"]))
    if not ran.would_run or not ran.reach_is_the_callers:
        raise CheckFailedError(THE_REACH_WAS_NOT_THE_CALLERS)
    stopped = await routes.plan(admin, str(cannot["plugin_id"]))
    if stopped.would_run or stopped.reach_is_the_callers:
        raise CheckFailedError(A_PLUGIN_WAS_PLANNED_FOR_A_STRANGER)
    if stopped.refusal != PLUGIN_NOT_AVAILABLE or NOT_HELD in stopped.model_dump_json():
        raise CheckFailedError(THE_REFUSAL_SAID_MORE_THAN_ONE_THING)
