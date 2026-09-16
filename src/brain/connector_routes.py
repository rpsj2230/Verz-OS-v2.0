"""The connectors screen over HTTP: which sources are installed, and what each may read.

`brain.console.connector_trust` decides what a reader may be told about a connector and renders
nothing. This is the half that makes it openable, and it adds no second opinion about any of it:
every field below is a projection of a value that module produced.

**A router of its own, and the reason is the act rather than the noun.** `brain.install_routes`
answers about the deployment, where there is no name to guess and no row belonging to anybody.
This answers about which outside systems this company reads, where a name is exactly the thing a
refusal must not confirm: `brain.connectors.federation.NAMING_A_SOURCE_IS_A_DISCLOSURE` is the
rule, and `brain.console.operate.reachable_connectors` is where it is applied. It is also the
one console surface whose subject is an act nobody can perform from here, and the sentence
saying so is served beside the list rather than written into a page, so it is one statement
rather than two that can drift apart.

**The capability is read out of the screen registry and is not declared again**, for the reason
`brain.install_routes.A_SECOND_SPELLING_OF_A_CAPABILITY_IS_THE_ONE_THAT_GOES_STALE` gives.
`brain.console.screens` already registers `connectors` against `read:connector`, and
`Screen.__post_init__` refuses a screen wired to a read that audits itself under another key.

**The capability is checked before the registry is consulted.** Copied from
`brain.install_routes` deliberately: a caller holding no grant is refused identically on an
install with twelve connectors and on one with none, so nobody can learn whether this company
reads anything at all by reaching the port.

**Two different facts about the reader are answered here and only one of them is a permission
check.** Whether the screen opens is `brain.console.reads.permitted`, which is the tool's
capability and the console plane together. Whether the reader holds the authority to install a
connector is `brain.connectors.registry.may_install`, and it is a fact about the reader's own
grant, answered because the screen has to tell somebody who could install a source what has to
happen for one to be installed and somebody who could not that it is not theirs to do. It is
never used to decide what the list contains: the list is narrowed by reach, and a reader holding
`admin:connector` and no reach sees nothing.

**No credential in, none out, and none in a log.** There is no body on this route and no write
verb on this router. `brain.console.connector_trust.CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY`
is the sentence served in place of a control: nothing in this repository writes a value into the
vault at runtime, so a form collecting a credential would have nowhere to send it, and a control
drawn and then refused reads as a permission problem with the person using it. The one thing
this route logs is the surface name on a refusal, which is `_not_answerable`'s own rule.

**A process with no registry answers a sentence and never an empty list**, which is
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` applied where it matters most: an
empty list of connectors reads as an install that reads nothing, which is the reassuring answer
to "what does this system have access to". Nothing in this repository constructs a
`ConnectorRegistry`, so this answers the sentence on every install today, and the day something
attaches one the list appears with no line here changing.

Rejected: building the registry here out of the manifest builders in `brain.connectors`. Each of
those takes the folder ids, hosts and vault paths of one company's install, so a module calling
them would be this repository holding a client's configuration, and `brain.ops.independence` is
the sweep that refuses it. The registry is a runtime record of what somebody installed and it
has to arrive from wherever that happened.

Rejected: a POST that registers a manifest. `brain.connectors.registry.register` already takes
an installer's entitlement and refuses without `admin:connector`, so the guard exists; what does
not exist is the vault write that has to happen first. A route that registered a manifest
pointing at a vault path holding nothing would produce a connector that is installed, enabled
and fails on its first call, which is the state this screen is meant to let somebody avoid.

Scope: one read-only route. Nothing here writes, and it opens no session.

Task ids: M42.6.5
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.connectors.contract import ConnectorHealth
from brain.connectors.registry import RegisteredConnector, may_install
from brain.console.connector_trust import (
    CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY,
    COPY_POLICY,
    NOTHING_HERE_COUNTS_TODAYS_CALLS,
    NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY,
    TrustRow,
    trust_rows,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent

log = structlog.get_logger()


# ------------------------------------------------------------------ the capability

#: Every source this install reads, and what each was connected to.
CONNECTORS_READ: Final[Capability] = screen("connectors").read.requires


# ------------------------------------------------------- what is not on this process


class InstalledConnectors(Protocol):
    """Every connector this install registered, and what the last probe of each found.

    Both together, in the shape `brain.install_routes.ThrottleSource` uses and for its reason: a
    caller holding one would have to invent the other, and a screen carrying a lifecycle state
    with no health beside it is the screen that sends an operator to chase the wrong thing.

    A protocol read off `app.state` rather than a parameter, because there is nothing to pass.
    Nothing in this repository constructs a `brain.connectors.registry.ConnectorRegistry`, so
    there is no value `brain.app` could attach today, and the absence is answered as a sentence
    rather than as an empty list.
    """

    def __call__(self) -> tuple[Sequence[RegisteredConnector], dict[str, ConnectorHealth]]: ...


def installed_connectors_of(request: Request) -> InstalledConnectors | None:
    """The registry reader this process was built with, or None.

    `getattr` and a `callable` check rather than an `isinstance` against the protocol, in the
    shape `brain.install_routes.backup_objects_of` uses and with its argument: a runtime
    checkable protocol whose only member is `__call__` admits every function in the process, so
    the check would read as structural and be a callable check with more words. The attribute's
    name is what discriminates and this comment is the proof the structural match was not made.
    """
    found = getattr(request.app.state, "installed_connectors", None)
    return cast(InstalledConnectors, found) if callable(found) else None


# ------------------------------------------------------------------------ the shapes


class TrustView(BaseModel):
    """One connector, with what it is trusted to read said in words.

    `brain.console.connector_trust.TrustRow`, copied field by field rather than from `__dict__`,
    for the reason `brain.install_routes.fact_view` gives: a field added to `TrustRow` would
    otherwise arrive in a response because a copy loop was generous, and the fields this screen
    has refused are exactly the ones somebody would add.

    No field for a credential, a vault path, a host or an endpoint. See
    `brain.console.connector_trust.A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    wiring: str
    credential: str
    budget: str
    projected_fields: int
    checked_at: str | None
    health: str
    lifecycle: str
    serving: bool
    version: str
    reaches: str
    access: str
    permission_sync: str


class ConnectorsView(BaseModel):
    """The connectors this reader may be told exist, or why there is no list.

    Exactly one of a list and a sentence, refused in the model rather than left to whatever
    draws it, which is `brain.install_routes.LimitsView`'s construction and its reason: an empty
    list of connectors and an absent one draw the same nothing, and one of them means this
    install reads no outside system while the other means nothing here looked.

    `connecting` is on every response including the unread one, because it is a statement about
    what this build can do rather than about what this install has, and a reader who cannot see
    a list is exactly the reader who needs to know what connecting involves.

    No count and no total, on either half.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    connectors: list[TrustView] | None = None
    #: Why there is no list. Required when there is none, empty when there is one.
    unread: str = ""
    #: What has to happen for a source to be connected, and where.
    connecting: str
    #: What is copied out of any source and what never is. The same on every install and for
    #: every reader, because it is the platform's rule rather than this company's configuration.
    copy_policy: list[CopyLineView]
    #: Why the budget column states a ceiling and draws no bar of today's use.
    budget_unread: str
    #: Whether this reader holds the authority to install one. Their own grant and nobody's
    #: else, and it narrows nothing on this response.
    may_connect: bool

    @model_validator(mode="after")
    def _exactly_one(self) -> ConnectorsView:
        if self.connectors is not None and self.unread:
            msg = (
                "a connector list is set and a reason for having none is set beside it, so a "
                "reader cannot tell an install that reads nothing from one nothing looked at"
            )
            raise ValueError(msg)
        if self.connectors is None and not self.unread:
            msg = (
                "no connector list and nothing saying why, which renders as an install that "
                f"reads no outside system. {NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY}"
            )
            raise ValueError(msg)
        return self


def trust_view(one: TrustRow) -> TrustView:
    """One row, copied field by field. See `TrustView` for why it is written out."""
    return TrustView(
        name=one.name,
        wiring=one.wiring,
        credential=one.credential,
        budget=one.budget,
        projected_fields=one.projected_fields,
        checked_at=None if one.checked_at is None else one.checked_at.isoformat(),
        health=one.health,
        lifecycle=one.lifecycle,
        serving=one.serving,
        version=one.version,
        reaches=one.reaches,
        access=one.access,
        permission_sync=one.permission_sync,
    )


class CopyLineView(BaseModel):
    """One line of what this system copies out of a source and what it never does.

    `brain.console.connector_trust.CopyLine`, field by field. Served rather than written into a
    page, because it is the answer to the question a client's own auditor asks and it must be
    one document: a console holding its own copy of it is a second policy, edited by whoever is
    next in the browser.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    what: str
    verdict: str
    why: str


# ---------------------------------------------------------------------- the refusals


def _not_answerable(surface: str) -> Absent:
    """The one refusal this router makes.

    `surface` reaches a log and never a response, which is `brain.install_routes._not_answerable`
    rule: `brain.app.handle_brain_error` sends `Absent.public_message`, and a body naming the
    screen would tell a caller which capability they are short of. Nothing about a connector
    reaches either, which matters more here than on any other console surface: a refusal that
    named one would be the disclosure the whole list is filtered to prevent.
    """
    log.info("connector surface not answerable", surface=surface)
    return Absent("this part of the console is not answerable for this caller")


def _permitted(reach: EntitlementSet, now: datetime) -> None:
    """Refuse unless this caller may open this screen, before the registry is consulted.

    `brain.console.reads.permitted` rather than a `holds` call on the capability, because a
    console read asks for the plane as well; see
    `brain.install_routes.A_SCREENS_CAPABILITY_IS_HALF_OF_WHAT_IT_ASKS_FOR`.
    """
    if not permitted(screen("connectors").read, reach, now):
        raise _not_answerable("connectors")


# ----------------------------------------------------------------------- the route

router = APIRouter(prefix=API_PREFIX, tags=["connectors"])


@router.get("/connectors", response_model=ConnectorsView, responses=COMMON_RESPONSES)
async def connectors(request: Request, asked: Asked) -> ConnectorsView:
    """Which sources this install reads, and what each one is trusted to read (M42.6.5).

    The capability first and the registry second, for the reason the module docstring gives.

    `may_connect` is answered for every caller who gets this far, including one who will be
    shown the unread sentence, because it is a fact about their own grant and it decides which
    of two things the screen tells them to do. It narrows nothing: a reader holding
    `admin:connector` and no reach over any source is shown an empty list of connectors and the
    same sentence about what connecting involves.

    There is no connect control and no credential field. See
    `brain.console.connector_trust.CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY`, which is served
    as the `connecting` field so the sentence is stated once rather than once here and once in a
    page.
    """
    _permitted(asked.reach, asked.now)
    may_connect = may_install(asked.reach, asked.now)
    policy = [CopyLineView(what=one.what, verdict=one.verdict, why=one.why) for one in COPY_POLICY]
    source = installed_connectors_of(request)
    if source is None:
        return ConnectorsView(
            unread=NOTHING_HERE_HOLDS_A_CONNECTOR_REGISTRY,
            connecting=CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY,
            copy_policy=policy,
            budget_unread=NOTHING_HERE_COUNTS_TODAYS_CALLS,
            may_connect=may_connect,
        )
    registry, checked = source()
    rows = trust_rows(registry, asked.reach, now=asked.now, checked=checked)
    return ConnectorsView(
        connectors=[trust_view(one) for one in rows],
        connecting=CONNECTING_IS_NOT_DONE_FROM_A_BROWSER_TODAY,
        copy_policy=policy,
        budget_unread=NOTHING_HERE_COUNTS_TODAYS_CALLS,
        may_connect=may_connect,
    )
