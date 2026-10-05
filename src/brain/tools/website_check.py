"""Is a website working: asked over HTTP first, and in a browser only when the page must be seen.

The owner's example of an agent with hands is somebody asking whether a client's website is
working (ARC-B-027, OWN-104, OWN-105 in the requirements register). Most of that question is
answered without a browser: a status, where the address sends a visitor, how long its
certificate has left and how long it took to answer. A browser run is a gVisor container, an
egress proxy and a slot in a global session budget (`brain.browsing`), and spending one to learn a
status code spends the scarcest thing in the product on the cheapest question it is asked.

**Every address this tool contacts passes `brain.tools.fetch.assert_fetchable`, the redirects
included.** It is the rule the skill importer, the REST connector, link uploads and webhooks
already share: https only, no credentials in the address, every resolved address checked and
none inside the network, and the transport handed the address that was checked rather than the
name. Imported and not restated. A website check is the same request as a skill import, made by a
model instead of a person, so it gets the same refusals and none of them is loosened here. The
cost is plain http: a site served only over it is refused rather than checked, and a redirect
down to it is reported as a redirect not followed.

**Rejected: calling `fetch` itself.** Its `Fetcher` answers one hop with either a body or the
next address, which is the right shape for importing bytes and has nowhere to put a status, a
certificate or a time, and those three are this tool's whole answer. Widening `Fetcher` would
change a protocol four other modules are written against, for one caller. So the loop is here and it
is short, and the part of it that is ever wrong, the check on every hop and the bound on how many
hops (`MAX_REDIRECTS`), is fetch's.

**The address must be inside the run's reach, and so must every redirect.** `entitlement` is the
run reach the gate already computed, `E(caller) ∩ agent_ceiling`, and this module asks it one
question through `scope_for`: whether `read:website_check` is held in a scope that admits this
host. Nothing here intersects anything, for the reason `brain.browsing.envelope` gives and
`tests/invariants/test_single_implementation.py` enforces. The host is asked about before it is
resolved, because a lookup is itself a request made on the agent's behalf. See
`A_REDIRECT_DOES_NOT_WIDEN_THE_REACH`. The record carries the host in the field a grant narrows
on, so the grant that let the call through is the one the redactor reads on the way out.

A grant narrows on the host with `eq` or `in`. `prefix` on a host admits look-alikes, since
`example.com` is a prefix of `example.com.evil.test`; it is not refused here, because what a scope
may say is `brain.core.scope`'s grammar and a second opinion about it would be a second grammar.

**A redirect not followed says so and does not say why.** See
`A_REDIRECT_NOT_FOLLOWED_DOES_NOT_SAY_WHY`.

**The browser is the last resort, and it is handed only what cannot write.** It opens only when
the request asks for the rendered page, only after HTTP reached one, only onto a surface a person
declared on that origin (`brain.browsing.targets`), only when that surface reads and admits no
write verb, and only when the run's reach holds the browser's own grant for that target. See
`THE_BROWSER_IS_THE_LAST_RESORT` and `THE_BROWSER_KEEPS_ITS_OWN_GRANT`. A site nobody declared
cannot be rendered, which is the browsing package's rule about maps a page wrote and not a
decision made here.

Not built here, and said: the transport. `Prober` is the seam, as `Fetcher` is fetch's, because a
module that owned a socket could not be tested on the redirect chain, which is the part that is
ever wrong. `brain.ops.webhook_delivery` holds the pieces one is made from: `SystemResolver`, and
a connection opened to the checked address that speaks TLS and HTTP as the name, and
`brain.ops.website_probe.HttpsProber` is the prober built from them. The application hands it to
`brain.tools.startup.build_registry`, which registers the check; a caller with no prober registers
none, for the reason that module gives about a row tool with no source. The other side
of `ReadOnlyBrowser` is the worker half `brain.browsing.launcher` says is not built either. No
field policy for `website_check` ships, as none ships for `skill_script` or `browser_surface`,
so default-deny withholds its fields until an administrator classifies them.

Task ids: M12.4.4
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Protocol
from urllib.parse import urljoin, urlsplit

import structlog
from pydantic import BaseModel, ConfigDict, Field

from brain.browsing.planning import Goal, Plan, PlanRequest, plan
from brain.browsing.sessions import BROWSE_SURFACE, TARGET_FIELD, SurfaceReading
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.channels.widget import normalise_origin
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Denied
from brain.tools.fetch import (
    MAX_REDIRECTS,
    Fetchable,
    Resolver,
    UnsafeAddressError,
    assert_fetchable,
)
from brain.tools.registry import RegisteredTool, ResultContract, ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ names and numbers

#: The system the call goes to, and the first segment of the tool's name.
WEBSITE_SOURCE: Final = "website"

#: The object this tool returns, and the entity a field policy for it is written about.
WEBSITE_CHECK_OBJECT: Final = "website_check"

#: The tool's name, in the `source.verb_noun` grammar `brain.tools.registry` enforces.
WEBSITE_CHECK_TOOL: Final = f"{WEBSITE_SOURCE}.check_site"

#: What a run must hold, in a scope that admits the host, for an address to be checked.
WEBSITE_CHECK_CAPABILITY: Final = Capability(value=f"read:{WEBSITE_CHECK_OBJECT}")

#: The field a grant narrows on, and the field the record carries the host in. One name for
#: both, so the scope that admitted the call is the scope the redactor evaluates on the record.
HOST_FIELD: Final = "website_host"

#: How long one hop may take, connect to status line. Ten seconds is what
#: `brain.ops.webhook_delivery` gives a receiver, and a site slower than that is the finding.
PROBE_TIMEOUT_SECONDS: Final = 10.0

#: The longest address a model may pass. Long enough for any real URL; an address longer
#: than this is content rather than a place.
MAX_ADDRESS_CHARS: Final = 2048

#: The statuses whose `Location` is followed. 300, 304 and 305 are not redirects a browser
#: follows on its own, so a site answering with one has answered.
REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})

#: What the read-only browser is asked to do. Fixed, because a goal is the only free text that
#: reaches a planner (`brain.browsing.planning.Goal`) and nothing here was typed by a person.
RENDERED_CHECK_GOAL: Final = (
    "Read the declared fields of this website's page as a browser renders it, for a check "
    "of whether the website is working"
)

TOOL_DESCRIPTION: Final = (
    "Check whether a website is working: its HTTP status, where it redirects, how many days "
    "its certificate has left and how long it took to answer. Opens the read-only browser "
    "only when asked to inspect the rendered page."
)

# ------------------------------------------------------------------ written-down reasons

#: Why a redirect is asked about exactly as the address was.
A_REDIRECT_DOES_NOT_WIDEN_THE_REACH: Final = (
    "The address an agent may check is decided by the run's reach, and a redirect is an "
    "address chosen by the site rather than by anybody who holds a grant. Followed without "
    "asking, it would let any site inside the reach send the check anywhere, including a "
    "place the reach was written to keep it out of. So every hop is asked the same two "
    "questions as the first, the reach and then the fetch rules, and a hop that fails either "
    "is reported and never contacted, not even by a lookup."
)

#: Why the record does not say which of the two refused a redirect.
A_REDIRECT_NOT_FOLLOWED_DOES_NOT_SAY_WHY: Final = (
    "A redirect can be refused because its host is outside the run's reach or because the "
    "fetch rules refuse its address, and the second includes a name that resolves inside the "
    "network. Saying which would tell whoever reads the answer that a name they chose resolves "
    "to something internal, one bit per question, which is a map of the network drawn by "
    "asking. So both read as one outcome, the address the site gave is shown because the site "
    "gave it, and the reason goes to the administrator's log."
)

#: Why the browser is the last thing this tool reaches for.
THE_BROWSER_IS_THE_LAST_RESORT: Final = (
    "A status, a redirect, a certificate and a time are answered over HTTP, and a browser run "
    "costs a sandboxed container and a slot in the global session budget. So the browser opens "
    "only when the request asks for the rendered page and only after HTTP reached a page to "
    "render: a site that did not answer, redirected somewhere this check does not go or looped "
    "has nothing a browser could add except a second failure."
)

#: Why the website check is not a way around the browser's own requirement.
THE_BROWSER_KEEPS_ITS_OWN_GRANT: Final = (
    "browser.read_surface requires read:browser_surface in a scope admitting its target, and "
    "the catalogue shows it only to a run holding that. Handing a surface to the browser from "
    "inside this tool skips the catalogue, so the same question is asked here: a run that "
    "could not have called the browser itself does not reach it through a website check. A "
    "surface that admits any write verb is never handed over, because this tool declares no "
    "side effect and a browser that can click is a browser the page can make post."
)


# ------------------------------------------------------------------ the request


class WebsiteCheckRequest(BaseModel):
    """The whole of what a model may say: an address, and whether the page must be seen.

    `inspect_rendered_page` is false unless the question is about what a visitor sees drawn:
    text a script builds, a section that renders or does not. Whether a site is up is answered
    without it. There is no field naming a browser target or a surface, so a model cannot point
    the browser anywhere a person did not declare.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str = Field(min_length=1, max_length=MAX_ADDRESS_CHARS)
    inspect_rendered_page: bool = False


# ------------------------------------------------------------------ one hop


class ProbeError(Exception):
    """A prober reported something that cannot have happened, so none of it is believed."""


class ProbeFailure(enum.StrEnum):
    """Why a hop gave no status. Closed, and each is a different thing for a person to fix."""

    #: Refused, reset or unroutable.
    CONNECTION = "connection"
    #: The handshake failed: an expired, mismatched or untrusted certificate among others.
    TLS = "tls"
    #: No status line inside `PROBE_TIMEOUT_SECONDS`.
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ProbeAnswer:
    """What one hop came back with, as the transport measured it.

    A status or a failure, exactly one. `certificate_not_after` may be set beside a TLS failure,
    because a transport that could read the certificate it was shown should report it: an
    expired certificate is the commonest reason a handshake fails and the days are the answer.
    """

    elapsed_seconds: float
    status: int | None = None
    location: str = ""
    certificate_not_after: datetime | None = None
    failure: ProbeFailure | None = None

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            msg = (
                f"a hop took {self.elapsed_seconds} seconds; a negative time is a broken clock "
                "or a broken prober, and neither is a response time"
            )
            raise ProbeError(msg)
        if (self.status is None) == (self.failure is None):
            msg = (
                "a hop answers with a status or fails, exactly one of the two; this one reported "
                f"status {self.status} and failure {self.failure}"
            )
            raise ProbeError(msg)


class Prober(Protocol):
    """One hop to an address that passed the fetch rules. Never follows a redirect.

    Handed the `Fetchable` and never a URL on its own, so the address it connects to is the one
    that was checked. It must send the name in the Host header and in SNI, verify the
    certificate against the name, and report the redirect rather than follow it, because a
    client that follows redirects applies the rules to the first address only.
    """

    async def probe(self, target: Fetchable, *, timeout_seconds: float) -> ProbeAnswer: ...


class ReadOnlyBrowser(Protocol):
    """The read-only browser as this tool reaches it: one declared surface, read and returned.

    Handed a `Plan` that `brain.browsing.planning.plan` expanded from a declared surface with no
    write verb, the target that declares it, and the run's reach, which the other side compiles
    an envelope against with `brain.browsing.envelope.compile_envelope`.
    """

    async def read(
        self, plan: Plan, target: Target, *, entitlement: EntitlementSet, now: datetime
    ) -> SurfaceReading: ...


# ------------------------------------------------------------------ what comes back


class ChainEnd(enum.StrEnum):
    """How the chain from the address ended. Closed, and there is no member for unknown."""

    #: An address answered with something other than a redirect.
    ANSWERED = "answered"
    #: An address gave no status. `failure` says which kind.
    UNREACHABLE = "unreachable"
    #: A redirect pointed somewhere this check does not contact. See
    #: `A_REDIRECT_NOT_FOLLOWED_DOES_NOT_SAY_WHY`.
    REDIRECT_NOT_FOLLOWED = "redirect_not_followed"
    #: More redirects than `brain.tools.fetch.MAX_REDIRECTS`, which is a loop or a redirector.
    TOO_MANY_REDIRECTS = "too_many_redirects"


class BrowserUse(enum.StrEnum):
    """What happened to the rendered-page check."""

    #: The request did not ask for the rendered page, so the browser was not opened.
    NOT_ASKED = "not_asked"
    #: HTTP reached no page, so there was nothing to render.
    NO_PAGE = "no_page"
    #: No read-only browser for this page and this run: none running, no declared surface on
    #: that origin that reads and cannot write, or no grant for the browser on its target. One
    #: word for all three, for the reason `brain.tools.run_skill.SKILL_NOT_AVAILABLE` gives.
    NOT_AVAILABLE = "not_available"
    #: The browser read the declared surface and `rendered_values` is what it read.
    OPENED = "opened"


class WebsiteCheck(Entity):
    """One check of one address, tagged so the redactor can walk it.

    `redirects` and `redirect_statuses` run in step: the address each redirect sent the check
    to, and the status that sent it. When `outcome` is `REDIRECT_NOT_FOLLOWED` the last address
    in `redirects` is the one not contacted, and `final_address` is the last one that was.

    `certificate_expires_in_days` is the soonest on the chain, and `certificate_host` names whose
    it is: a visitor who types the bare domain meets its certificate before the one at the end.
    Negative when it has already expired.
    """

    website_host: str
    address: str
    outcome: ChainEnd
    status: int | None = None
    failure: ProbeFailure | None = None
    redirects: tuple[str, ...] = ()
    redirect_statuses: tuple[int, ...] = ()
    final_address: str
    certificate_expires_in_days: int | None = None
    certificate_host: str = ""
    #: The last address contacted, from connect to status line. None when it gave no status.
    response_seconds: float | None = None
    #: Every hop contacted, added up: what a visitor waits before the page starts.
    total_seconds: float = 0.0
    browser: BrowserUse = BrowserUse.NOT_ASKED
    rendered_values: tuple[tuple[str, str], ...] = ()


# ------------------------------------------------------------------ the reach


def within_reach(entitlement: EntitlementSet, host: str, now: datetime) -> bool:
    """Whether the run holds `read:website_check` in a scope that admits this host."""
    scope = entitlement.scope_for(WEBSITE_CHECK_CAPABILITY, now)
    return scope is not None and scope.matches({HOST_FIELD: host})


def browser_in_reach(entitlement: EntitlementSet, target: Target, now: datetime) -> bool:
    """Whether the run holds the browser's own grant for this target. See
    `THE_BROWSER_KEEPS_ITS_OWN_GRANT`."""
    scope = entitlement.scope_for(BROWSE_SURFACE, now)
    return scope is not None and scope.matches({TARGET_FIELD: target.name})


# ------------------------------------------------------------------ the chain


def address_of(text: str) -> str:
    """The address to check: as given, or https in front of a bare host."""
    stripped = text.strip()
    return stripped if "://" in stripped else f"https://{stripped}"


def _host_of(url: str) -> str | None:
    """The host an address names, or None for one that does not parse."""
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return None


def _joined(base: str, location: str) -> str:
    """Where a `Location` points, from the address that gave it; as given if it does not parse."""
    try:
        return urljoin(base, location)
    except ValueError:
        return location


async def admitted(
    url: str, *, entitlement: EntitlementSet, now: datetime, resolver: Resolver
) -> Fetchable | None:
    """The checked address for one hop, or None when this check may not contact it.

    The reach first and the fetch rules second, so a host outside the reach is never looked up.
    The fetch rules run in a thread because a resolver blocks and this is called on the event
    loop. The reason for a None goes to the log and nowhere else; see
    `A_REDIRECT_NOT_FOLLOWED_DOES_NOT_SAY_WHY`.
    """
    host = _host_of(url)
    if host is None:
        log.info("website_check.not_contacted", reason="unparseable")
        return None
    if not within_reach(entitlement, host, now):
        log.info("website_check.not_contacted", reason="outside_reach", host=host)
        return None
    try:
        return await asyncio.to_thread(assert_fetchable, url, resolver)
    except (UnsafeAddressError, ValueError) as exc:
        log.info("website_check.not_contacted", reason="fetch_rules", error=str(exc))
        return None


@dataclass(frozen=True)
class Hop:
    """One address contacted, and what it answered."""

    url: str
    host: str
    answer: ProbeAnswer


@dataclass(frozen=True)
class Chain:
    """Every hop contacted, in order, the redirects that led between them, and how it ended."""

    end: ChainEnd
    hops: tuple[Hop, ...]
    redirects: tuple[str, ...] = ()
    redirect_statuses: tuple[int, ...] = ()

    @property
    def last(self) -> Hop:
        return self.hops[-1]


async def follow(
    address: str,
    *,
    entitlement: EntitlementSet,
    now: datetime,
    resolver: Resolver,
    prober: Prober,
) -> Chain:
    """Contact the address and every redirect this check may follow, one hop at a time.

    The address itself is refused with `Denied` rather than reported, because the caller chose
    it: its public sentence is the one every refusal carries, and the detail goes to the log.
    A redirect is chosen by the site, so one that may not be followed is reported instead.
    """
    first = await admitted(address, entitlement=entitlement, now=now, resolver=resolver)
    if first is None:
        msg = (
            f"website check of {address!r} refused: outside this run's reach or refused by the "
            "fetch rules"
        )
        raise Denied(msg)

    hops: list[Hop] = []
    redirects: list[str] = []
    statuses: list[int] = []

    def ended(end: ChainEnd) -> Chain:
        return Chain(
            end=end,
            hops=tuple(hops),
            redirects=tuple(redirects),
            redirect_statuses=tuple(statuses),
        )

    target = first
    while True:
        answer = await prober.probe(target, timeout_seconds=PROBE_TIMEOUT_SECONDS)
        hops.append(Hop(url=target.url, host=target.host, answer=answer))
        if answer.status is None:
            return ended(ChainEnd.UNREACHABLE)
        if answer.status not in REDIRECT_STATUSES or not answer.location:
            return ended(ChainEnd.ANSWERED)
        following = _joined(target.url, answer.location)
        redirects.append(following)
        statuses.append(answer.status)
        if len(redirects) > MAX_REDIRECTS:
            return ended(ChainEnd.TOO_MANY_REDIRECTS)
        allowed = await admitted(following, entitlement=entitlement, now=now, resolver=resolver)
        if allowed is None:
            return ended(ChainEnd.REDIRECT_NOT_FOLLOWED)
        target = allowed


def soonest_certificate(hops: Sequence[Hop], now: datetime) -> tuple[int | None, str]:
    """Whole days until the first certificate on the chain expires, and whose it is.

    `timedelta.days` floors, so an hour after expiry is minus one day and an hour before it is
    zero: a certificate with less than a day left reads as zero rather than as one.
    """
    dated = [
        (hop.answer.certificate_not_after, hop.host)
        for hop in hops
        if hop.answer.certificate_not_after is not None
    ]
    if not dated:
        return None, ""
    not_after, host = min(dated)
    return (not_after - now).days, host


def check_id(address: str, now: datetime) -> str:
    """A record id the redactor accepts: a URL is not one, so it is a digest of the check."""
    return hashlib.sha256(f"{address}\n{now.isoformat()}".encode()).hexdigest()[:32]


def record_of(
    address: str,
    chain: Chain,
    *,
    now: datetime,
    browser: BrowserUse = BrowserUse.NOT_ASKED,
    rendered: tuple[tuple[str, str], ...] = (),
) -> WebsiteCheck:
    """The chain as the record a caller is shown."""
    last = chain.last
    days, certificate_host = soonest_certificate(chain.hops, now)
    return WebsiteCheck(
        entity=WEBSITE_CHECK_OBJECT,
        id=check_id(address, now),
        website_host=_host_of(address) or "",
        address=address,
        outcome=chain.end,
        status=last.answer.status,
        failure=last.answer.failure,
        redirects=chain.redirects,
        redirect_statuses=chain.redirect_statuses,
        final_address=last.url,
        certificate_expires_in_days=days,
        certificate_host=certificate_host,
        response_seconds=(last.answer.elapsed_seconds if last.answer.status is not None else None),
        total_seconds=sum(hop.answer.elapsed_seconds for hop in chain.hops),
        browser=browser,
        rendered_values=rendered,
    )


# ------------------------------------------------------------------ the browser


def origin_of(url: str) -> str:
    """The normalised origin of an address, or empty when it has none."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return normalise_origin(f"{parts.scheme}://{parts.netloc}")


def read_only_surface(targets: TargetRegistry, origin: str) -> tuple[Target, Surface] | None:
    """The first declared surface on this origin that reads and admits no write verb.

    Matched on the surface's own origin, which `Target` already holds inside the target's
    allowlist, so an origin that did not normalise matches nothing: no surface declares the
    empty one. Targets are tried in name order so two installs with one configuration hand the
    browser the same surface.
    """
    for target in sorted(targets.targets, key=lambda one: one.name):
        for surface in target.surfaces:
            if surface.origin == origin and surface.admits(Verb.READ) and not surface.writes():
                return target, surface
    return None


# ------------------------------------------------------------------ the tool


@dataclass(frozen=True)
class WebsiteCheckTool:
    """The website check (M12.4.4), bound to its transport and, if it has one, its browser.

    `resolver` and `prober` are required and have no default, for the reason
    `brain.tools.run_skill.SkillScriptTool` gives about its runner. `browser` may be absent: the
    HTTP check stands on its own, and a rendered check on an install with no browser says the
    browser is not available rather than refusing the whole check.
    """

    resolver: Resolver
    prober: Prober
    targets: TargetRegistry = field(default_factory=TargetRegistry)
    browser: ReadOnlyBrowser | None = None

    def definition(self) -> ToolDefinition:
        """What the catalogue describes to a model.

        `SideEffect.NONE`, and it is load-bearing on two things this module holds to: every
        request it makes is a read, and the browser is never handed a surface that can write.
        `IdentityMode.DELEGATED` because no credential of either kind is spent, which is
        `SkillScriptTool.definition`'s argument; the browser's shared credential belongs to the
        browser's side of `ReadOnlyBrowser` and is not this tool's to declare.
        """
        return ToolDefinition(
            name=WEBSITE_CHECK_TOOL,
            description=TOOL_DESCRIPTION,
            entity=WEBSITE_CHECK_OBJECT,
            args_schema=WebsiteCheckRequest.model_json_schema(),
            required_capability=WEBSITE_CHECK_CAPABILITY.value,
            side_effect=SideEffect.NONE,
            identity_mode=IdentityMode.DELEGATED,
            source=WEBSITE_SOURCE,
        )

    async def rendered(
        self,
        request: WebsiteCheckRequest,
        chain: Chain,
        *,
        entitlement: EntitlementSet,
        now: datetime,
    ) -> tuple[BrowserUse, tuple[tuple[str, str], ...]]:
        """The rendered-page check, if it is asked for and may be made. See
        `THE_BROWSER_IS_THE_LAST_RESORT` and `THE_BROWSER_KEEPS_ITS_OWN_GRANT`."""
        if not request.inspect_rendered_page:
            return BrowserUse.NOT_ASKED, ()
        if chain.end is not ChainEnd.ANSWERED:
            return BrowserUse.NO_PAGE, ()
        found = read_only_surface(self.targets, origin_of(chain.last.url))
        if self.browser is None or found is None:
            return BrowserUse.NOT_AVAILABLE, ()
        target, surface = found
        if not browser_in_reach(entitlement, target, now):
            return BrowserUse.NOT_AVAILABLE, ()
        handed = plan(
            PlanRequest(
                goal=Goal(text=RENDERED_CHECK_GOAL, asked_by=entitlement.principal_id),
                target=target.name,
                surfaces=(surface.name,),
            ),
            self.targets,
        )
        reading = await self.browser.read(handed, target, entitlement=entitlement, now=now)
        return BrowserUse.OPENED, reading.values

    def handler(self) -> Callable[..., Awaitable[TypedResult[WebsiteCheck]]]:
        """The callable a registry registers, called as every dispatcher here calls a handler.

        A closure, for the reason `brain.knowledge.rows.RowTool.reader` gives: the signature a
        registry and a dispatcher inspect carries only what a model may pass, and `entitlement`
        is the run reach the gate computed, keyword-only and absent from `args_schema`.
        """

        async def check_website(
            request: WebsiteCheckRequest,
            *,
            entitlement: EntitlementSet,
            now: datetime | None = None,
        ) -> TypedResult[WebsiteCheck]:
            """HTTP first, the browser only if asked and possible, then one record.

            The clock is read here when the dispatcher passed no instant, and only here. A
            certificate's days left is a fact about the present, unlike a `fetched_at` that can
            be left empty, and `EntitlementSet.scope_for` falls back to the same clock.
            """
            at = now if now is not None else datetime.now(UTC)
            address = address_of(request.address)
            chain = await follow(
                address,
                entitlement=entitlement,
                now=at,
                resolver=self.resolver,
                prober=self.prober,
            )
            browser, values = await self.rendered(request, chain, entitlement=entitlement, now=at)
            record = record_of(address, chain, now=at, browser=browser, rendered=values)
            return TypedResult(records=(record,), source=WEBSITE_SOURCE, fetched_at=at.isoformat())

        return check_website


def register_website_check(registry: ToolRegistry, tool: WebsiteCheckTool) -> RegisteredTool:
    """Register the check through the one door every tool uses, with its contract declared.

    `ResultContract.TYPED` is stated rather than left to the default, as
    `brain.tools.startup.build_registry` states it for a row tool: a handler changed to return a
    dictionary then fails at registration instead of at the first redaction.
    """
    return registry.register(
        tool.definition(), tool.handler(), result_contract=ResultContract.TYPED
    )
