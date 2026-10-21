"""Install acceptance check: an administrator declares a website, signs what lets a browser do more
on it, and takes it back, through the console's routes, and the compiler and the skill rule read it.

**One check, because the leaves are one story.** A website is declared (M19.2.4), an exception is
signed for one of its pages so a write there is compiled to run without waiting for a person
(M19.7.3), an exemption is signed so a skill may drive a website that has an API (M19.6.7), each is
listed with who signed it and when it lapses, each is in the ledger as a leash change, and each
stops being read the instant it is revoked or lapses (M19.9.7). Running them apart would show each
route answering and not that anything reads what they keep.

**It goes through the routes and then asks the readers.** The administrator holds the authority over
browsers and the second-factor sign-in the gate demands of an administrator, and every write is the
route's own function, so the authority, the switch and the codec are the ones a person meets. What
is then asked is what the driver and the assignment ask: `driver.prepare_run` compiles a write
step to an envelope that waits for a person unless a live exception names its page, and
`skill_library.browser_refusals` refuses a browser skill for a website with an API tool unless a
live exemption names it. A permission is shown absent three ways: revoked, lapsed at an instant
later than its end, and never signed.

**Nothing here opens a browser,** and the check does not read the `browser_runs` switch: it
asks for the records a run will read. Everything it writes is in the check's transaction and rolled
back with it.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any, Final

from sqlalchemy import text

from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the browser modules' (2301 to 2303).
CHECK_ORDER: Final = 2304

A, _B = RESERVED_DEPARTMENTS

#: The authorities and capabilities the check's administrator holds, restated rather than imported,
#: so a change to a route's authority fails the check instead of moving with it.
ADMINISTERS_BROWSERS: Final = "admin:browser"
SWITCHES_FEATURES: Final = "admin:feature"
BROWSES: Final = "read:browser_surface"
WRITES: Final = "write:browser_surface"

#: The origin the check's made-up website allows. `.invalid` is reserved and never resolves.
ORIGIN: Final = "https://acceptance-check.invalid"
#: The API tool the made-up website names, which a stand-in registry holds for the skill rule.
API_TOOL: Final = "acceptance.list_invoices"

A_PERSON_WITHOUT_THE_AUTHORITY_WAS_SHOWN_THE_SCREEN: Final = (
    "a person without the authority over browsers was shown what is declared"
)
A_WRITE_OPENED_A_PERMISSION_WITH_THE_SWITCH_OFF: Final = (
    "a website was declared or a permission signed while the switch was off"
)
A_BAD_DOCUMENT_WAS_DECLARED: Final = "a declaration carrying a key the codec does not take was kept"
A_WEBSITE_WAS_NOT_DECLARED: Final = "a declaration the codec should accept was not kept and listed"
A_DECLARATION_WAS_NOT_STORED: Final = "a declared website was not in the install's table"
A_WRITE_WAITED_FOR_NOBODY_BEFORE_A_SIGNATURE: Final = (
    "a write on a page nobody signed an exception for was compiled to run without a person"
)
AN_EXCEPTION_WAS_NOT_SIGNED: Final = "an exception for a declared write page was not signed"
AN_EXCEPTION_WAS_NOT_LISTED: Final = "a signed exception was not listed with who signed it"
AN_EXCEPTION_WAS_NOT_READ: Final = (
    "a write on a page with a signed exception still waited for a person"
)
AN_EXCEPTION_OUTLIVED_ITS_END: Final = (
    "a write compiled after its exception had lapsed still ran without a person"
)
A_READ_PAGE_TOOK_AN_EXCEPTION: Final = "an exception was signed for a page that does not write"
AN_EXCEPTION_OUTLIVED_ITS_REVOCATION: Final = (
    "a write compiled after its exception was revoked still ran without a person"
)
A_REVOKED_GRANT_WAS_LISTED: Final = "a revoked permission was still listed"
A_BROWSER_SKILL_WAS_ASSIGNABLE_OVER_AN_API: Final = (
    "a browser skill was allowed for a website that has an API tool and no exemption"
)
AN_EXEMPTION_WAS_NOT_READ: Final = "a browser skill with a live exemption was still refused"
AN_EXEMPTION_OUTLIVED_ITS_REVOCATION: Final = (
    "a browser skill was still allowed after its exemption was revoked"
)
A_PERMISSION_LEFT_NO_ENTRY: Final = (
    "signing or revoking a browser permission did not leave a leash change in the ledger"
)
A_RETIRED_WEBSITE_WAS_LISTED: Final = "a retired website was still declared"


async def _administrator(h: Harness) -> str:
    """A reserved principal holding the authority over browsers and the feature one, and both
    browser capabilities, each over everything."""
    made = h.principal(A, "browsers")
    await h.person(
        made,
        department=A,
        grants=(
            (ADMINISTERS_BROWSERS, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
            (BROWSES, Scope.unrestricted()),
            (WRITES, Scope.unrestricted()),
        ),
    )
    return made


def _document(h: Harness) -> dict[str, Any]:
    """The made-up website: a page that reads, a page that files, and an API tool for its work."""
    return {
        "name": f"acceptance_{h.run}_books".lower(),
        "origins": [ORIGIN],
        "api_tools": [API_TOOL],
        "surfaces": [
            {
                "name": "invoices",
                "origin": ORIGIN,
                "path": "/invoices",
                "verbs": ["open", "read"],
                "reads": ["number"],
            },
            {
                "name": "filing",
                "origin": ORIGIN,
                "path": "/filing",
                "verbs": ["open", "submit"],
                "controls": [{"verb": "submit", "role": "button", "label": "File"}],
            },
        ],
    }


class _Routes:
    """The browser routes, each asked as one reserved person with the second factor."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.console = console_for(h)

    async def page(self, who: str) -> Any:
        from brain.browser_routes import browser_page

        return await browser_page(self.console.request(), await asking_as(self.h, who, strong=True))

    async def declare(self, who: str, document: dict[str, Any]) -> Any:
        from brain.browser_routes import DeclarationAsked, declare_target

        return await declare_target(
            self.console.request("POST"),
            DeclarationAsked(declaration=document),
            await asking_as(self.h, who, strong=True),
        )

    async def retire(self, who: str, name: str) -> None:
        from brain.browser_routes import retire_target

        await retire_target(
            self.console.request("POST"), name, await asking_as(self.h, who, strong=True)
        )

    async def sign_exception(self, who: str, target: str, surface: str, days: int) -> Any:
        from brain.browser_routes import ExceptionAsked, sign_exception

        return await sign_exception(
            self.console.request("POST"),
            ExceptionAsked(
                target=target,
                surface=surface,
                days=days,
                reason="the nightly filing runs unattended for the check",
            ),
            await asking_as(self.h, who, strong=True),
        )

    async def sign_exemption(self, who: str, target: str, skill: str, days: int) -> Any:
        from brain.browser_routes import ExemptionAsked, sign_exemption

        return await sign_exemption(
            self.console.request("POST"),
            ExemptionAsked(
                target=target,
                skill=skill,
                days=days,
                reason="the connector has no filing page for the check",
            ),
            await asking_as(self.h, who, strong=True),
        )

    async def revoke(self, who: str, seq: int) -> None:
        from brain.browser_routes import revoke_grant

        await revoke_grant(
            self.console.request("POST"), seq, await asking_as(self.h, who, strong=True)
        )


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    """The declarations switch, through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features_declared.browser_declarations import BROWSER_DECLARATIONS

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            BROWSER_DECLARATIONS.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


async def _write_waits(
    h: Harness, administrator: str, document: dict[str, Any], *, days_later: int, n: str
) -> bool:
    """Whether a plan to file on the made-up website is compiled to wait for a person, at an
    instant `days_later` days on. Compiled by the driver's own `prepare_run`, which reads the
    exceptions in force at that instant and nowhere else."""
    from brain.browsing.declared import declared_from
    from brain.browsing.driver import prepare_run
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.targets import TargetRegistry
    from brain.gate.injection import AutonomyTier
    from brain.gate.suspension_store import StoredSuspensions

    target = declared_from(document).target
    asking = await h.reach(administrator)
    async with StoredSuspensions(h.sessions).holding(asking, h.now) as rows:
        envelope = await prepare_run(
            rows.session,
            plan(
                PlanRequest(
                    goal=Goal(text="File the check's return", asked_by=administrator),
                    target=target.name,
                    surfaces=("filing",),
                ),
                TargetRegistry(targets=(target,)),
            ),
            target,
            run_id=f"acceptance_{h.run}_{n}",
            agent_id=f"acceptance_{h.run}_agent",
            reach=asking,
            ceiling=AutonomyTier.AUTONOMOUS,
            trace_id=h.trace_id,
            now=h.now + timedelta(days=days_later),
        )
    return bool(envelope.awaits_approval())


async def _skill_refused(h: Harness, name: str, *, days_later: int) -> bool:
    """Whether a browser skill is refused for the made-up website at an instant `days_later` on."""
    from brain.browsing import declared
    from brain.browsing.sessions import READ_SURFACE
    from brain.console.skill_library import BrowserNeeds, browser_refusals
    from brain.tools.registry import ToolRegistry
    from brain.tools.skills import Skill

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name=API_TOOL,
            description="Lists the made-up website's invoices",
            entity="ticket",
            required_capability="read:ticket.status",
            identity_mode=IdentityMode.DELEGATED,
            side_effect=SideEffect.NONE,
        ),
        _handler,
    )
    at = h.now + timedelta(days=days_later)
    async with h.sessions() as session:
        needs = BrowserNeeds(
            targets=await declared.registry_of(session),
            tools=registry,
            exemptions=await declared.live_exemptions(session, at),
        )
    skill = Skill(
        name=name,
        description="Reads the made-up website's invoices in a browser",
        tools=(READ_SURFACE.name,),
    )
    return bool(browser_refusals(skill, Scope.unrestricted(), needs, at))


class _InvoiceRow(Entity):
    """What the made-up API tool would return. It is never called."""


def _handler() -> TypedResult[_InvoiceRow]:
    """A registry only has to hold the tool for the skill rule to find it."""
    return TypedResult[_InvoiceRow]()


async def _ledger_entries(h: Harness, target: str) -> list[tuple[str, str]]:
    rows = await h.execute(
        text(
            "SELECT action, actor_id FROM obs.audit_entry WHERE subject = :subject ORDER BY seq"
        ).bindparams(subject=f"connector:browser.{target}")
    )
    return [(str(one[0]), str(one[1])) for one in rows.all()]


@check(
    leaves=("M19.2.4", "M19.6.7", "M19.7.3", "M19.9.7"),
    sentence=(
        "An administrator of browsers declares a website and signs an exception for a page and an "
        "exemption for a skill through the console's routes; the driver compiles a write on that "
        "page to run without a person, and a browser skill is allowed over an API tool, only "
        "while the permission is in force, and each signature is a leash change in the ledger."
    ),
)
async def a_website_is_declared_and_permissions_signed_for_it_are_read(h: Harness) -> None:
    await h.found_departments()
    admin, other = await _administrator(h), h.principal(A, "other")
    await h.person(other, department=A)
    routes = _Routes(h)
    if not await refused(routes.page(other)):
        raise CheckFailedError(A_PERSON_WITHOUT_THE_AUTHORITY_WAS_SHOWN_THE_SCREEN)

    document = _document(h)
    name = str(document["name"])
    await _switched(h, admin, on=False, n=1)
    opening: tuple[Callable[[], Coroutine[Any, Any, Any]], ...] = (
        lambda: routes.declare(admin, document),
        lambda: routes.sign_exception(admin, name, "filing", 5),
        lambda: routes.sign_exemption(admin, name, "acceptance-skill", 5),
    )
    for write in opening:
        if not await refused(write()):
            raise CheckFailedError(A_WRITE_OPENED_A_PERMISSION_WITH_THE_SWITCH_OFF)
    await _switched(h, admin, on=True, n=2)

    if not await refused(routes.declare(admin, {**document, "selector": "#go"})):
        raise CheckFailedError(A_BAD_DOCUMENT_WAS_DECLARED)
    made = await routes.declare(admin, document)
    if made.name != name or [one.name for one in made.surfaces] != ["invoices", "filing"]:
        raise CheckFailedError(A_WEBSITE_WAS_NOT_DECLARED)
    stored = (
        await h.execute(
            text(
                "SELECT count(*) FROM agent.browser_target WHERE name = :name AND NOT retired"
            ).bindparams(name=name)
        )
    ).scalar_one()
    if stored != 1 or not any(one.name == name for one in (await routes.page(admin)).targets):
        raise CheckFailedError(A_DECLARATION_WAS_NOT_STORED)

    # Before any signature a write waits for a person, and a skill is refused over the API tool.
    if not await _write_waits(h, admin, document, days_later=0, n="before"):
        raise CheckFailedError(A_WRITE_WAITED_FOR_NOBODY_BEFORE_A_SIGNATURE)
    if not await _skill_refused(h, "acceptance-skill", days_later=0):
        raise CheckFailedError(A_BROWSER_SKILL_WAS_ASSIGNABLE_OVER_AN_API)

    if not await refused(routes.sign_exception(admin, name, "invoices", 5)):
        raise CheckFailedError(A_READ_PAGE_TOOK_AN_EXCEPTION)
    exception = await routes.sign_exception(admin, name, "filing", 5)
    exemption = await routes.sign_exemption(admin, name, "acceptance-skill", 5)
    if exception.kind != "exception" or exception.signed_by != admin:
        raise CheckFailedError(AN_EXCEPTION_WAS_NOT_SIGNED)
    listed = {one.seq: one for one in (await routes.page(admin)).grants}
    if (
        listed.get(exception.seq) is None
        or listed[exception.seq].expires_at != exception.expires_at
    ):
        raise CheckFailedError(AN_EXCEPTION_WAS_NOT_LISTED)

    if await _write_waits(h, admin, document, days_later=1, n="during"):
        raise CheckFailedError(AN_EXCEPTION_WAS_NOT_READ)
    if not await _write_waits(h, admin, document, days_later=6, n="after"):
        raise CheckFailedError(AN_EXCEPTION_OUTLIVED_ITS_END)
    if await _skill_refused(h, "acceptance-skill", days_later=1):
        raise CheckFailedError(AN_EXEMPTION_WAS_NOT_READ)
    if not await _skill_refused(h, "another-skill", days_later=1):
        raise CheckFailedError(A_BROWSER_SKILL_WAS_ASSIGNABLE_OVER_AN_API)

    await routes.revoke(admin, exception.seq)
    await routes.revoke(admin, exemption.seq)
    still = {one.seq for one in (await routes.page(admin)).grants}
    if still & {exception.seq, exemption.seq}:
        raise CheckFailedError(A_REVOKED_GRANT_WAS_LISTED)
    if not await _write_waits(h, admin, document, days_later=1, n="revoked"):
        raise CheckFailedError(AN_EXCEPTION_OUTLIVED_ITS_REVOCATION)
    if not await _skill_refused(h, "acceptance-skill", days_later=1):
        raise CheckFailedError(AN_EXEMPTION_OUTLIVED_ITS_REVOCATION)

    entries = await _ledger_entries(h, name)
    if entries != [("leash_change", admin)] * 4:
        raise CheckFailedError(A_PERMISSION_LEFT_NO_ENTRY)

    await routes.retire(admin, name)
    if any(one.name == name for one in (await routes.page(admin)).targets):
        raise CheckFailedError(A_RETIRED_WEBSITE_WAS_LISTED)
