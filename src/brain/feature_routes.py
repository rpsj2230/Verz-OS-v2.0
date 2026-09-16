"""The Features screen over HTTP: which new features this install has switched on, and the switch.

`brain.ops.features` declares what can be switched on and which functions read each switch, and
`ops.setting` keeps the install's answer. Until this module the only way to turn a feature on was
a statement at a database prompt, which is the shell `docs/admin-console.md` says a routine
change must not need.

**One authority for both the read and the write, held over everything.** `admin:feature` is
asked through `brain.console.govern._in_reach` at `brain.console.govern.NOWHERE`, which only an
unrestricted grant admits, before the database is reached. A feature is switched for the whole
install, so there is no department's version of a switch, and a list of what is switched on is
read by nobody but somebody deciding whether to switch something: the Stop screen's `admin:halt`
is the precedent for a screen whose read is its authority. A second, `read:` capability for the
list would be a screen whose only readers cannot use it, and the first administrator, who holds
every `admin:` capability and no `read:` one, could not open it.

**A caller without the authority is refused identically on an install with a database and one
without**, which is `brain.routing_routes`' ordering argument, and the refusal names the screen
and never the capability. A caller with the authority who names a feature this product does not
declare is told so by name, because the list of features is product text identical on every
install and naming it discloses nothing about this one.

**What the screen cannot switch is said on the answer, as fields.** Components are the install
profile's containers, and plugins have no loader; see `brain.ops.features` for both. Each is a
boolean on the response rather than a sentence in the console, on
`brain.operate_routes.LiveRunsView`'s argument: the day either stops being true, it goes false in
the commit that makes it so.

**Not claimed: M27.8.10.** The leaf is feature and module enablement, and modules cannot be
enabled from here, for the reason above. A leaf closed over a screen that switches half of what
it names would be the tracker counting the half.

Task ids: none
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.features import (
    FEATURES,
    Feature,
    FeatureError,
    feature,
    switch,
    switch_states,
    switched_on_in,
)
from brain.ops.setting_store import SettingState
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: Reads the Features screen and switches a feature. Held over everything or not at all.
FEATURE_AUTHORITY: Final = Capability(value="admin:feature")

#: The screen's name in a refusal. The console's own menu word, identical on every install.
FEATURES_SCREEN: Final = "features"


def may_switch(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read the Features screen and turn a switch: the authority, over
    everything."""
    return _in_reach(reach, FEATURE_AUTHORITY, NOWHERE, now)


class FeatureView(BaseModel):
    """One feature, whether it is on, and who last changed it. Never a description anybody typed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    title: str
    what: str
    while_off: str
    on: bool
    #: Every function that reads the switch, as `module:function`, so a person can see it reaches
    #: something. Product text.
    read_by: list[str]
    #: Who last turned it, and when, or both null for a switch nobody has touched.
    changed_by: str | None
    changed_at: datetime | None


class FeaturesPage(BaseModel):
    """Every feature this product can switch on, and what this screen cannot switch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    features: list[FeatureView]
    #: Optional components are containers chosen by the install profile on the server.
    components_are_chosen_by_the_profile: bool = True
    #: Plugins have a lifecycle and nothing loads one, so no plugin switch is offered.
    plugins_have_no_loader: bool = True
    #: A switch keeps its last change and nothing before it, and writes no ledger entry. See
    #: `brain.ops.setting_store.A_SWITCH_RECORDS_ITS_LAST_CHANGE_AND_NOTHING_BEFORE_IT`.
    only_the_last_change_is_kept: bool = True


class SwitchAsked(BaseModel):
    """Turn one feature on or off. Required, so what is sent is what the screen displayed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool


def feature_view(one: Feature, state: SettingState | None, *, on: bool) -> FeatureView:
    """One feature as the screen draws it."""
    return FeatureView(
        name=one.name,
        title=one.title,
        what=one.what,
        while_off=one.while_off,
        on=on,
        read_by=list(one.read_by),
        changed_by=state.updated_by if state is not None else None,
        changed_at=state.updated_at if state is not None else None,
    )


def features_page(states: dict[str, SettingState]) -> FeaturesPage:
    """Every declared feature in declaration order, whether or not a row exists for it.

    `on` is `brain.ops.features.switched_on_in`'s answer over the same rows, rather than read off
    the row here, so the screen and the readers cannot disagree about what a row means.
    """
    on = switched_on_in(states)
    return FeaturesPage(
        features=[feature_view(one, states.get(one.name), on=one.name in on) for one in FEATURES]
    )


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {FEATURES_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what to fix."""
    message = f"that feature was not switched: {reason}"
    return Absent(message, public_message=message)


router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get("/install/features", response_model=FeaturesPage, responses=COMMON_RESPONSES)
async def features(request: Request, asked: Asked) -> FeaturesPage:
    """Every feature and whether it is on, for a caller who may switch them."""
    if not may_switch(asked.reach, asked.now):
        log.info("features screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        states = await switch_states(session)
    return features_page(states)


@router.post("/install/features/{name}", response_model=FeatureView, responses=COMMON_RESPONSES)
async def switch_feature(
    request: Request, name: str, body: SwitchAsked, asked: Asked
) -> FeatureView:
    """Turn one feature on or off, and answer with what the database now holds.

    The authority first, then the name, then the write, and the order is the property: a caller
    without the authority learns nothing about which names exist, and a caller with it is told
    the name is not a feature before anything is written.
    """
    if not may_switch(asked.reach, asked.now):
        log.info("feature switch refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        one = feature(name)
    except FeatureError:
        raise _refused_because(f"{name!r} is not a feature this product declares") from None

    async with _require_sessions(request)() as session:
        await switch(session, one, on=body.on, by=asked.caller.principal.id)
        states = await switch_states(session)
        await session.commit()
    log.info("feature switched", feature=one.name, on=body.on, principal=asked.caller.principal.id)
    return features_page(states).features[FEATURES.index(one)]
