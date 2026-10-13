"""The plugin registry over HTTP: the extension points, the plugins on this install, and the
transitions between their states.

`brain.plugins` decides every question about a plugin and holds no connection, and
`brain.ops.plugin_registry` keeps what it decides in the two tables migration 0032 made. Until this
module nothing called either, so a plugin could not be put on an install by anybody short of a
database prompt, and the Features screen said so in a sentence (`plugins_have_no_loader`). This is
the door and nothing behind it: **a plugin recorded here is not loaded, and no code of its runs.**

**The point of the first slice is the lifecycle, not the loader.** The register says code from
outside never runs in this process (`brain.plugins.points.
CODE_IN_THIS_PROCESS_IS_INSIDE_EVERY_GUARD_AT_ONCE`), so a plugin point that takes code runs in a
sidecar or a sandbox, and neither runner exists yet. Rejected: a loader that imports a plugin's
module on `enable`, which is the shortest path to a plugin and puts outside code inside every guard
the repository has. What this slice can honestly do is take a manifest, refuse it by the rules the
package already holds, record it, and move it between states, so the day a runner exists there is a
registry for it to read.

**One authority for the read and the write, held over everything**, `admin:plugin`, for the reason
`brain.feature_routes` gives about `admin:feature`: a plugin is on the whole install, so there is no
department's version of one. A caller without it is answered identically with a database and
without one, and the refusal names the screen and never the capability.

**The switch gates the door and never traps what it opened.** Installing, enabling, upgrading and
rolling back are behind `PLUGIN_REGISTRY`, which ships off. Disabling and removing never are, so a
plugin enabled while the switch was on can always be turned off with it off. See
`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

**A manifest is refused where its words still exist.** `manifest_from` refuses a key that expresses
reach before the model sees the document, `lifecycle.install` refuses a core outside the declared
range, and `contract.assert_cannot_see_unredacted` refuses a manifest that would be handed a value
the gate has not walked. The last is asked at install as well as before a run, because a plugin
that could never be run is a row nobody can explain. A point the register does not give to a plugin
is refused in the register's own words (`contract.would_be_refused`).

**`POST /install/plugins/{plugin_id}/plan` is `contract.plan_run` asked of the caller.** It says
whether a plugin would be given the caller's reach, and the answer is a boolean and a hash: the
reach a plugin is handed is the caller's own and unchanged, which is the whole of "cannot widen
entitlements", and the refusal is `PLUGIN_NOT_AVAILABLE` for every reason so the caller cannot
enumerate the register or their own reach by difference.

**Not claimed:** M29.2.4 (a drain on upgrade needs runs to drain) and M29.2.5 (a host to enforce a
tier). Nothing here runs a plugin, so there is nothing in flight and nothing to isolate, and a
route that said otherwise would be the tracker counting the half.

Task ids: M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12, M29.2.1, M29.2.2, M29.2.3, M29.2.6
"""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops import plugin_registry
from brain.ops.features import PLUGIN_REGISTRY, is_on
from brain.plugins.contract import (
    PluginContractError,
    assert_cannot_see_unredacted,
    plan_run,
    would_be_refused,
)
from brain.plugins.lifecycle import (
    PLUGIN_ADMIN,
    PLUGIN_NOT_AVAILABLE,
    Installed,
    LifecycleError,
    disable,
    enable,
    install,
    rollback,
    upgrade,
)
from brain.plugins.manifest import ManifestError, PluginManifest, manifest_from
from brain.plugins.points import POINTS, Answer, ExtensionPoint, point_named
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The screen's name in a refusal. The console's own menu word, identical on every install.
PLUGINS_SCREEN: Final = "plugins"

#: The package whose version a manifest's compatibility range is judged against.
CORE_PACKAGE: Final = "verz-brain"

#: Why a plugin routes' answer says nothing runs, as a field on every answer and not a sentence.
NOTHING_RUNS_A_PLUGIN_YET: Final = (
    "A plugin recorded here is not loaded: the points that take code run it in a sidecar or a "
    "sandbox, and neither runner exists. The record is what a runner will read."
)


def may_administer(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read the plugin registry and change it: the authority, over
    everything."""
    return _in_reach(reach, PLUGIN_ADMIN, NOWHERE, now)


def core_version() -> str | None:
    """The version of this product a manifest's range is judged against, or None when the
    package metadata is absent (a source tree that was never installed)."""
    try:
        return installed_version(CORE_PACKAGE)
    except PackageNotFoundError:
        return None


class PointView(BaseModel):
    """One extension point, as the register states it. Product text, identical on every install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    leaf: str
    #: `plugin`, `flag`, `configuration` or `undecided`.
    answer: str
    #: Where a plugin at it would run, or null for a point that takes none.
    tier: str | None
    direction: str | None
    carries: str | None
    #: The `module:Symbol` a plugin implements, or empty for a point with none.
    contract: str
    why: str


class ConfigView(BaseModel):
    """One value a plugin needs set on the install. A name and its meaning, never a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    meaning: str
    required: bool


class PluginView(BaseModel):
    """One plugin on this install, its state and the versions it has run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: str
    version: str
    point: str
    #: `installed`, `enabled` or `disabled`. Never `absent`: an absent plugin is not listed.
    state: str
    since: datetime
    history: list[str]
    #: Capabilities the plugin needs its caller to hold. A question, never a grant.
    requires: list[str]
    config: list[ConfigView]
    core_min: str
    core_max: str


class PluginsPage(BaseModel):
    """The register and the install's plugins, and the facts this screen cannot change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    points: list[PointView]
    plugins: list[PluginView]
    #: Whether the registry's writes are switched on. Disabling and removing are always offered.
    registry_is_on: bool
    #: True while no runner exists. A field, so the sentence leaves the page in the commit that
    #: makes it false.
    no_plugin_is_loaded: bool = True
    #: The release this install is, which a manifest's range is judged against, or null.
    core_version: str | None


class ManifestAsked(BaseModel):
    """A manifest to record. Raw, because the parser's refusals are the ones that name a reach key
    where it still exists; a typed body would have dropped it first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: dict[str, Any]


class RollbackAsked(BaseModel):
    """The version to return to. A version this install has run, which the registry holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class PlanAsked(BaseModel):
    """Whether a plugin would be handed the caller's reach, asked as the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PlanView(BaseModel):
    """What `contract.plan_run` said. A boolean, a hash and the one sentence for every refusal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    would_run: bool
    #: True when the reach a plugin would be handed hashes the same as the caller's own.
    reach_is_the_callers: bool
    #: The one refusal, or empty when the plugin would be given the reach.
    refusal: str


def point_view(one: ExtensionPoint) -> PointView:
    return PointView(
        name=one.name,
        leaf=one.leaf,
        answer=one.answer.value,
        tier=None if one.tier is None else one.tier.value,
        direction=None if one.direction is None else one.direction.value,
        carries=None if one.carries is None else one.carries.value,
        contract=one.contract,
        why=one.why,
    )


def plugin_view(record: Installed) -> PluginView:
    manifest = record.manifest
    return PluginView(
        plugin_id=manifest.plugin_id,
        version=manifest.version,
        point=manifest.point,
        state=record.state.value,
        since=record.since,
        history=list(record.history),
        requires=[one.value for one in manifest.requires],
        config=[
            ConfigView(name=key.name, meaning=key.meaning, required=key.required)
            for key in manifest.config
        ],
        core_min=manifest.core_min,
        core_max=manifest.core_max,
    )


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {PLUGINS_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what to fix."""
    message = f"that plugin was not changed: {reason}"
    return Absent(message, public_message=message)


def parsed(raw: dict[str, Any]) -> PluginManifest:
    """The manifest a body carries, or a refusal that names what is wrong with it.

    A validation error is summarised as where and what, never as the input it quotes: a manifest's
    own words are its author's and the refusal says them, and a value that is not a manifest's is
    not repeated.
    """
    try:
        return manifest_from(raw)
    except ManifestError as refused:
        raise _refused_because(str(refused)) from None
    except ValidationError as refused:
        found = "; ".join(
            f"{'.'.join(str(part) for part in one['loc']) or 'the manifest'}: {one['msg']}"
            for one in refused.errors(include_input=False)
        )
        raise _refused_because(f"the manifest does not read: {found}") from None


def _plugin_point_or_refusal(manifest: PluginManifest) -> None:
    """Refuse a manifest for a point the register does not give to a plugin, in its own words."""
    point = point_named(manifest.point)
    if point is None or point.answer is not Answer.PLUGIN:
        raise _refused_because(would_be_refused(manifest.point))


async def _switched_on(session: AsyncSession) -> None:
    """Refuse when the registry's writes are switched off. Asked of the switch, not of a copy."""
    if not await is_on(session, PLUGIN_REGISTRY):
        raise _refused_because(
            "the plugin registry is switched off for this install; switch it on from Features"
        )


router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get("/install/plugins", response_model=PluginsPage, responses=COMMON_RESPONSES)
async def plugins(request: Request, asked: Asked) -> PluginsPage:
    """Every extension point and every plugin on this install, for a caller who administers them."""
    if not may_administer(asked.reach, asked.now):
        log.info("plugins screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        held = await plugin_registry.records(session)
        registry_is_on = await is_on(session, PLUGIN_REGISTRY)
    return PluginsPage(
        points=[point_view(one) for one in POINTS],
        plugins=[plugin_view(held[name]) for name in sorted(held)],
        registry_is_on=registry_is_on,
        core_version=core_version(),
    )


@router.post(
    "/install/plugins",
    status_code=201,
    response_model=PluginView,
    responses=COMMON_RESPONSES,
)
async def install_plugin(request: Request, body: ManifestAsked, asked: Asked) -> PluginView:
    """Record a manifest as a plugin on this install, switched off.

    The authority first, then the switch, then the manifest, and the order is the property: a
    caller without the authority learns nothing, and one with it is told the switch is off before
    anything about the document it sent.
    """
    if not may_administer(asked.reach, asked.now):
        log.info("plugin install refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        manifest = parsed(body.manifest)
        _plugin_point_or_refusal(manifest)
        try:
            assert_cannot_see_unredacted(manifest)
        except PluginContractError as refused:
            raise _refused_because(str(refused)) from None
        core = core_version()
        if core is None:
            raise _refused_because("this install cannot say which core version it runs")
        if manifest.plugin_id in await plugin_registry.records(session):
            raise _refused_because(
                f"{manifest.plugin_id} is already on this install; upgrade it instead"
            )
        try:
            record = install(manifest, core_version=core, at=asked.now)
            await plugin_registry.save(session, record)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin installed", plugin=manifest.plugin_id, principal=asked.caller.principal.id)
    return plugin_view(record)


async def _held(session: AsyncSession, plugin_id: str) -> Installed:
    held = (await plugin_registry.records(session)).get(plugin_id)
    if held is None:
        raise _refused_because(f"{plugin_id} is not on this install")
    return held


@router.post(
    "/install/plugins/{plugin_id}/enable", response_model=PluginView, responses=COMMON_RESPONSES
)
async def enable_plugin(request: Request, plugin_id: str, asked: Asked) -> PluginView:
    """Switch an installed plugin on. A separate act from installing it, and behind the switch."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        held = await _held(session, plugin_id)
        try:
            moved = enable(held, at=asked.now)
            await plugin_registry.save(session, moved)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin enabled", plugin=plugin_id, principal=asked.caller.principal.id)
    return plugin_view(moved)


@router.post(
    "/install/plugins/{plugin_id}/disable", response_model=PluginView, responses=COMMON_RESPONSES
)
async def disable_plugin(request: Request, plugin_id: str, asked: Asked) -> PluginView:
    """Switch a plugin off, leaving it installed. Never behind the switch: the act that undoes a
    state is not gated by the act that opened it."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        held = await _held(session, plugin_id)
        try:
            moved = disable(held, at=asked.now)
            await plugin_registry.save(session, moved)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin disabled", plugin=plugin_id, principal=asked.caller.principal.id)
    return plugin_view(moved)


@router.post(
    "/install/plugins/{plugin_id}/upgrade", response_model=PluginView, responses=COMMON_RESPONSES
)
async def upgrade_plugin(
    request: Request, plugin_id: str, body: ManifestAsked, asked: Asked
) -> PluginView:
    """Move a plugin to a later version of itself. The state is not changed by an upgrade."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        held = await _held(session, plugin_id)
        arriving = parsed(body.manifest)
        _plugin_point_or_refusal(arriving)
        try:
            assert_cannot_see_unredacted(arriving)
        except PluginContractError as refused:
            raise _refused_because(str(refused)) from None
        core = core_version()
        if core is None:
            raise _refused_because("this install cannot say which core version it runs")
        try:
            moved = upgrade(held, arriving, core_version=core, at=asked.now)
            await plugin_registry.save(session, moved)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin upgraded", plugin=plugin_id, principal=asked.caller.principal.id)
    return plugin_view(moved)


@router.post(
    "/install/plugins/{plugin_id}/rollback", response_model=PluginView, responses=COMMON_RESPONSES
)
async def rollback_plugin(
    request: Request, plugin_id: str, body: RollbackAsked, asked: Asked
) -> PluginView:
    """Return a plugin to a version this install has run, as the document that ran."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        held = await _held(session, plugin_id)
        previous = await plugin_registry.manifest_for(session, plugin_id, body.version)
        if previous is None:
            raise _refused_because(
                f"{plugin_id} {body.version} has never run on this install, so there is "
                "nothing to return to"
            )
        try:
            moved = rollback(held, previous, at=asked.now)
            await plugin_registry.save(session, moved)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin rolled back", plugin=plugin_id, principal=asked.caller.principal.id)
    return plugin_view(moved)


@router.post("/install/plugins/{plugin_id}/remove", status_code=204, responses=COMMON_RESPONSES)
async def remove_plugin(request: Request, plugin_id: str, asked: Asked) -> None:
    """Take a disabled plugin off the install. Never behind the switch. The row is retired and the
    versions it ran are kept."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _held(session, plugin_id)
        try:
            await plugin_registry.remove(session, plugin_id, at=asked.now)
        except (LifecycleError, plugin_registry.RegistryError) as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
    log.info("plugin removed", plugin=plugin_id, principal=asked.caller.principal.id)


@router.post(
    "/install/plugins/{plugin_id}/plan", response_model=PlanView, responses=COMMON_RESPONSES
)
async def plan_plugin(request: Request, plugin_id: str, body: PlanAsked, asked: Asked) -> PlanView:
    """Whether this plugin would be given the caller's reach, and whether it would be unchanged.

    `contract.plan_run` as the caller, which is what a host would ask before every call. Every
    refusal is one sentence, so the answer cannot be used to map the register or the caller's own
    reach by difference.
    """
    del body
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        held = await _held(session, plugin_id)
    try:
        run = plan_run(held.manifest, caller=asked.reach, now=asked.now)
    except PluginContractError:
        return PlanView(would_run=False, reach_is_the_callers=False, refusal=PLUGIN_NOT_AVAILABLE)
    return PlanView(
        would_run=True,
        reach_is_the_callers=run.reach.ent_hash() == asked.reach.ent_hash(),
        refusal="",
    )
