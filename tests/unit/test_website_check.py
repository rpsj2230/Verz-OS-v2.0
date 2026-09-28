"""Whether a website is working, over HTTP first and in the read-only browser only when asked.

Nothing here contacts a network. The resolver and the prober are scripted, because the cases
that matter are a redirect to an address the first check never saw, a redirect out of the
agent's reach and a certificate that has already expired, and none of them is reachable on
demand against a real site.

`NOW` is 2999 and every certificate date is relative to it, for the reason CLAUDE.md gives about
fixtures with dates in them: nothing tested here is about the present except the one test that
passes no instant, and that one is relative to the clock it reads.

Task ids: M12.4.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from brain.browsing.planning import Plan
from brain.browsing.sessions import READ_SURFACE, SurfaceReading
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb, is_write
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode, SideEffect, TypedResult
from brain.core.errors import Absent, Denied
from brain.core.scope import Clause, Op, Scope
from brain.tools.fetch import MAX_REDIRECTS, Fetchable
from brain.tools.registry import EffectClass, ResultContract, ToolRegistry
from brain.tools.run_skill import assert_single_execution_path
from brain.tools.website_check import (
    HOST_FIELD,
    WEBSITE_CHECK_TOOL,
    BrowserUse,
    ChainEnd,
    ProbeAnswer,
    ProbeError,
    ProbeFailure,
    WebsiteCheck,
    WebsiteCheckRequest,
    WebsiteCheckTool,
    register_website_check,
)

NOW = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
PUBLIC = "93.184.216.34"
ORIGIN = "https://example.com"


# ------------------------------------------------------------------ fixtures


class Resolver:
    """Whatever the test says a name resolves to; unknown names resolve to one public address."""

    def __init__(self, answers: dict[str, Sequence[str]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[str] = []

    def resolve(self, host: str) -> Sequence[str]:
        self.calls.append(host)
        return self.answers.get(host, [PUBLIC])


def ok(days: int = 90, seconds: float = 0.25) -> ProbeAnswer:
    return ProbeAnswer(
        elapsed_seconds=seconds, status=200, certificate_not_after=NOW + timedelta(days=days)
    )


def moved(location: str, status: int = 301, days: int = 90) -> ProbeAnswer:
    return ProbeAnswer(
        elapsed_seconds=0.1,
        status=status,
        location=location,
        certificate_not_after=NOW + timedelta(days=days),
    )


class Prober:
    """A scripted chain: each address answers as the script says, or with a plain 200."""

    def __init__(self, script: dict[str, ProbeAnswer] | None = None) -> None:
        self.script = script or {}
        self.probed: list[Fetchable] = []

    async def probe(self, target: Fetchable, *, timeout_seconds: float) -> ProbeAnswer:
        assert timeout_seconds > 0
        self.probed.append(target)
        return self.script.get(target.url, ok())


class Browser:
    """A read-only browser that records what it was handed and reads one declared field."""

    def __init__(self) -> None:
        self.handed: list[tuple[Plan, Target, EntitlementSet]] = []

    async def read(
        self, plan: Plan, target: Target, *, entitlement: EntitlementSet, now: datetime
    ) -> SurfaceReading:
        del now
        self.handed.append((plan, target, entitlement))
        return SurfaceReading(
            entity="browser_surface",
            id="reading-1",
            surface=plan.request.surfaces[0],
            origin=ORIGIN,
            values=(("title", "Example Domain"),),
        )


def reach(
    *hosts: str, company_wide: bool = False, browser_target: str | None = None
) -> EntitlementSet:
    """A run reach holding the website grant for these hosts, and the browser's if named.

    The scope is written with the literal field name rather than `HOST_FIELD`, so a change to
    the constant is a change a grant written by an administrator would not follow.
    """
    scope = (
        Scope.unrestricted()
        if company_wide
        else Scope(clauses=(Clause(field="website_host", op=Op.IN, value=tuple(hosts)),))
    )
    grants = [Grant(capability=Capability(value="read:website_check"), scope=scope)]
    if browser_target is not None:
        grants.append(
            Grant(
                capability=Capability(value="read:browser_surface"),
                scope=Scope(
                    clauses=(Clause(field="browser_target", op=Op.EQ, value=browser_target),)
                ),
            )
        )
    return EntitlementSet(principal_id="p-asker", grants=tuple(grants))


def site(*verbs: Verb) -> TargetRegistry:
    """One declared target on the checked origin, with one surface admitting these verbs."""
    return TargetRegistry(
        targets=(
            Target(
                name="site",
                origins=frozenset({ORIGIN}),
                surfaces=(
                    Surface(
                        name="home",
                        origin=ORIGIN,
                        path="/",
                        verbs=frozenset(verbs or (Verb.OPEN, Verb.READ)),
                        capability=Capability(value="read:browser_surface"),
                        reads=("title",),
                    ),
                ),
            ),
        )
    )


def check(
    address: str,
    *,
    entitlement: EntitlementSet,
    prober: Prober | None = None,
    resolver: Resolver | None = None,
    browser: Browser | None = None,
    targets: TargetRegistry | None = None,
    rendered: bool = False,
    now: datetime | None = NOW,
) -> WebsiteCheck:
    """Call the registered handler exactly as a dispatcher does, and return its one record."""
    tool = WebsiteCheckTool(
        resolver=resolver or Resolver(),
        prober=prober or Prober(),
        targets=targets or TargetRegistry(),
        browser=browser,
    )
    registry = ToolRegistry()
    register_website_check(registry, tool)
    handler = registry.get(WEBSITE_CHECK_TOOL).handler

    async def go() -> object:
        answered = handler(
            WebsiteCheckRequest(address=address, inspect_rendered_page=rendered),
            entitlement=entitlement,
            now=now,
        )
        assert asyncio.iscoroutine(answered)
        return await answered

    result = asyncio.run(go())
    assert isinstance(result, TypedResult)
    (record,) = result.records
    assert isinstance(record, WebsiteCheck)
    return record


# ------------------------------------------------------------------ the HTTP check


def test_a_website_inside_the_reach_reports_its_status_certificate_and_response_time() -> None:
    """The positive case every refusal below is measured against: a checker that refused
    everything would satisfy all of them. Delete this and a tool that never answers passes.

    Also pins that the prober is handed the address the fetch rules checked, not the name,
    which is what closes DNS rebinding for this tool."""
    prober = Prober({"https://example.com": ok(days=90, seconds=0.25)})

    record = check("https://example.com", entitlement=reach("example.com"), prober=prober)

    assert record.outcome is ChainEnd.ANSWERED
    assert record.status == 200
    assert record.certificate_expires_in_days == 90
    assert record.certificate_host == "example.com"
    assert record.response_seconds == pytest.approx(0.25)
    assert record.redirects == ()
    assert record.browser is BrowserUse.NOT_ASKED
    assert [(one.host, one.address) for one in prober.probed] == [("example.com", PUBLIC)]


def test_a_bare_host_is_checked_over_https() -> None:
    """A model asked about a website usually names a domain, not a URL. Delete this and a
    bare host goes to the fetch rules without a scheme and is refused as not https, so the
    commonest way of asking fails for a reason the person cannot see."""
    prober = Prober()

    record = check("example.com", entitlement=reach("example.com"), prober=prober)

    assert record.address == "https://example.com"
    assert [one.url for one in prober.probed] == ["https://example.com"]


def test_an_address_outside_the_reach_is_refused_before_it_is_resolved() -> None:
    """The leaf's "within its ceiling". Delete this and an agent whose reach names one client's
    site can check any site at all, and the lookup alone tells whoever chose the name that this
    server asked about it.

    The refusal carries the sentence every refusal carries, so a person cannot tell it from an
    address that is simply not there."""
    resolver = Resolver()
    prober = Prober()

    with pytest.raises(Denied) as refused:
        check(
            "https://example.org",
            entitlement=reach("example.com"),
            resolver=resolver,
            prober=prober,
        )

    assert refused.value.public_message == Absent().public_message
    assert resolver.calls == []
    assert prober.probed == []


def test_a_run_holding_no_website_grant_is_refused() -> None:
    """The other half of the reach: no grant at all, rather than a grant for another host.
    Delete this and `scope_for` answering None could be read as unrestricted, which is the
    typo-becomes-an-open-door failure `brain.tools.registry.capability_for` describes."""
    prober = Prober()

    with pytest.raises(Denied):
        check(
            "https://example.com",
            entitlement=EntitlementSet(principal_id="p-asker"),
            prober=prober,
        )

    assert prober.probed == []


def test_an_address_inside_the_network_is_refused_even_with_a_company_wide_grant() -> None:
    """The fetch rules apply whatever the grant says. Delete this and an administrator who
    grants the check company-wide has also granted the cloud metadata endpoint."""
    prober = Prober()

    with pytest.raises(Denied):
        check("https://169.254.169.254/", entitlement=reach(company_wide=True), prober=prober)

    assert prober.probed == []


def test_the_redirect_chain_is_reported_hop_by_hop() -> None:
    """Where the address sends a visitor is half of whether it is working. Delete this and a
    chain that reports only its end hides a 302 where a 301 belongs, and a relative `Location`
    resolved against the wrong base."""
    prober = Prober(
        {
            "https://example.com": moved("https://www.example.com/", status=301),
            "https://www.example.com/": moved("/home", status=302),
        }
    )

    record = check(
        "https://example.com",
        entitlement=reach("example.com", "www.example.com"),
        prober=prober,
    )

    assert record.outcome is ChainEnd.ANSWERED
    assert record.redirects == ("https://www.example.com/", "https://www.example.com/home")
    assert record.redirect_statuses == (301, 302)
    assert record.final_address == "https://www.example.com/home"
    assert record.status == 200
    assert record.total_seconds == pytest.approx(0.1 + 0.1 + 0.25)


def test_a_redirect_outside_the_reach_is_not_followed_or_looked_up() -> None:
    """See `A_REDIRECT_DOES_NOT_WIDEN_THE_REACH`. Delete this and any site inside the reach can
    send the check to any site outside it, which makes the reach a suggestion."""
    resolver = Resolver()
    prober = Prober({"https://example.com": moved("https://example.org/")})

    record = check(
        "https://example.com", entitlement=reach("example.com"), prober=prober, resolver=resolver
    )

    assert record.outcome is ChainEnd.REDIRECT_NOT_FOLLOWED
    assert record.redirects == ("https://example.org/",)
    assert record.final_address == "https://example.com"
    assert [one.host for one in prober.probed] == ["example.com"]
    assert "example.org" not in resolver.calls


@pytest.mark.parametrize(
    ("location", "answers"),
    [
        ("https://169.254.169.254/latest/meta-data/", {}),
        ("https://internal.example.com/", {"internal.example.com": ["10.1.2.3"]}),
        ("http://example.com/", {}),
    ],
    ids=["metadata endpoint", "name resolving inside", "plain http"],
)
def test_a_redirect_the_fetch_rules_refuse_is_not_contacted(
    location: str, answers: dict[str, Sequence[str]]
) -> None:
    """A permitted public address answering `302 Location: https://169.254.169.254/` is the
    standard way past a check made on the first address only. Delete this and the check
    becomes the server's way of asking its own network for instance credentials."""
    prober = Prober({"https://example.com": moved(location, status=302)})

    record = check(
        "https://example.com",
        entitlement=reach(company_wide=True),
        prober=prober,
        resolver=Resolver(answers),
    )

    assert record.outcome is ChainEnd.REDIRECT_NOT_FOLLOWED
    assert record.redirects == (location,)
    assert [one.url for one in prober.probed] == ["https://example.com"]


def test_a_redirect_not_followed_reads_the_same_whatever_the_reason() -> None:
    """See `A_REDIRECT_NOT_FOLLOWED_DOES_NOT_SAY_WHY`. Delete this and a field saying which
    rule refused can be added, and then a name resolving inside the network is told apart from
    a name outside the reach, one question at a time."""
    outside = check(
        "https://example.com",
        entitlement=reach("example.com", "inside.example.com"),
        prober=Prober({"https://example.com": moved("https://example.org/")}),
    )
    inside = check(
        "https://example.com",
        entitlement=reach("example.com", "inside.example.com"),
        prober=Prober({"https://example.com": moved("https://inside.example.com/")}),
        resolver=Resolver({"inside.example.com": ["10.0.0.7"]}),
    )

    assert outside.model_dump(exclude={"redirects"}) == inside.model_dump(exclude={"redirects"})


def test_a_redirect_loop_ends_at_the_bound_the_fetch_rules_set() -> None:
    """A redirect loop is a request that never returns, and it holds whatever called it. Delete
    this and the loop's bound can drift from `brain.tools.fetch.MAX_REDIRECTS`, which is the
    bound every other fetch in the product keeps."""
    prober = Prober(
        {
            "https://example.com/a": moved("https://example.com/b"),
            "https://example.com/b": moved("https://example.com/a"),
        }
    )

    record = check("https://example.com/a", entitlement=reach("example.com"), prober=prober)

    assert record.outcome is ChainEnd.TOO_MANY_REDIRECTS
    assert len(prober.probed) == MAX_REDIRECTS + 1


def test_a_site_that_cannot_be_reached_is_reported_rather_than_raised() -> None:
    """A site that is down is the answer to "is it working", not an error in the tool. Delete
    this and a refused connection surfaces as an exception, and the person hears that the
    system failed rather than that their client's site did."""
    prober = Prober(
        {"https://example.com": ProbeAnswer(elapsed_seconds=3.0, failure=ProbeFailure.CONNECTION)}
    )

    record = check("https://example.com", entitlement=reach("example.com"), prober=prober)

    assert record.outcome is ChainEnd.UNREACHABLE
    assert record.failure is ProbeFailure.CONNECTION
    assert record.status is None
    assert record.response_seconds is None
    assert record.total_seconds == pytest.approx(3.0)


def test_the_soonest_certificate_on_the_chain_is_the_one_reported() -> None:
    """A visitor who types the bare domain meets its certificate before the one at the end of
    the redirect. Delete this and a chain whose apex certificate expires in five days reports
    the eighty left at the end, and the site breaks for most visitors on a date nobody saw."""
    prober = Prober(
        {
            "https://example.com": moved("https://www.example.com/", days=5),
            "https://www.example.com/": ok(days=80),
        }
    )

    record = check(
        "https://example.com",
        entitlement=reach("example.com", "www.example.com"),
        prober=prober,
    )

    assert record.certificate_expires_in_days == 5
    assert record.certificate_host == "example.com"


def test_an_expired_certificate_reports_the_days_since_as_negative() -> None:
    """An expired certificate is the commonest reason a handshake fails. Delete this and the
    days are dropped whenever the handshake did, which is exactly when they are the answer."""
    expired = ProbeAnswer(
        elapsed_seconds=0.2,
        failure=ProbeFailure.TLS,
        certificate_not_after=NOW - timedelta(days=2),
    )

    record = check(
        "https://example.com",
        entitlement=reach("example.com"),
        prober=Prober({"https://example.com": expired}),
    )

    assert record.outcome is ChainEnd.UNREACHABLE
    assert record.failure is ProbeFailure.TLS
    assert record.certificate_expires_in_days == -2


def test_without_an_instant_the_certificate_is_judged_at_the_clock() -> None:
    """The automation route passes the instant it has, which may be none. Delete this and a
    call with no instant raises on the subtraction, or judges the certificate at some other
    moment, and the days a person reads are wrong in the direction that looks safe."""
    soon = ProbeAnswer(
        elapsed_seconds=0.1,
        status=200,
        certificate_not_after=datetime.now(UTC) + timedelta(days=10, hours=1),
    )

    record = check(
        "https://example.com",
        entitlement=reach("example.com"),
        prober=Prober({"https://example.com": soon}),
        now=None,
    )

    assert record.certificate_expires_in_days == 10


def test_a_prober_reporting_the_impossible_is_not_believed() -> None:
    """The transport is the part under load and the part that gets replaced. Delete this and a
    negative time becomes a response time, and an answer with both a status and a failure is
    read as whichever the loop happens to look at first."""
    with pytest.raises(ProbeError, match="negative"):
        ProbeAnswer(elapsed_seconds=-0.1, status=200)
    with pytest.raises(ProbeError, match="exactly one"):
        ProbeAnswer(elapsed_seconds=0.1, status=200, failure=ProbeFailure.TLS)
    with pytest.raises(ProbeError, match="exactly one"):
        ProbeAnswer(elapsed_seconds=0.1)


def test_the_record_carries_the_host_in_the_field_a_grant_narrows_on() -> None:
    """One grant governs both the call and what the redactor lets through, because the record
    carries the host under the name the scope tests. Delete this and the two names can drift,
    and a grant that admitted the call then withholds every record it produced."""
    record = check("https://example.com", entitlement=reach("example.com"))

    assert HOST_FIELD in WebsiteCheck.model_fields
    scope = reach("example.com").scope_for(Capability(value="read:website_check"), NOW)
    assert scope is not None
    assert scope.matches(record.model_dump(mode="json"))


# ------------------------------------------------------------------ the read-only browser


def test_a_check_not_asking_for_the_rendered_page_never_opens_the_browser() -> None:
    """The leaf's "only when a rendered page must be inspected". Delete this and every check
    can spend a sandboxed browser session to learn a status code, which is the scarcest thing
    in the product spent on the cheapest question."""
    browser = Browser()

    record = check(
        "https://example.com",
        entitlement=reach("example.com", browser_target="site"),
        browser=browser,
        targets=site(),
        rendered=False,
    )

    assert record.browser is BrowserUse.NOT_ASKED
    assert browser.handed == []


def test_a_rendered_check_hands_the_browser_only_the_declared_read_only_surface() -> None:
    """The positive case for the browser. Delete this and the refusals below are satisfied by a
    tool that never opens it, and the owner's example, an agent that actually opens the site,
    is never met."""
    browser = Browser()
    entitlement = reach("example.com", browser_target="site")

    record = check(
        "https://example.com",
        entitlement=entitlement,
        browser=browser,
        targets=site(),
        rendered=True,
    )

    assert record.browser is BrowserUse.OPENED
    assert record.rendered_values == (("title", "Example Domain"),)
    ((plan, target, handed_reach),) = browser.handed
    assert target.name == "site"
    assert [(step.surface, step.verb) for step in plan.steps] == [
        ("home", Verb.OPEN),
        ("home", Verb.READ),
    ]
    assert not any(is_write(step.verb) for step in plan.steps)
    assert plan.request.goal.asked_by == "p-asker"
    assert handed_reach == entitlement


def test_the_browser_is_not_opened_when_http_reached_no_page() -> None:
    """See `THE_BROWSER_IS_THE_LAST_RESORT`. Delete this and a site that is down costs a
    browser session to fail a second time."""
    browser = Browser()
    down = ProbeAnswer(elapsed_seconds=10.0, failure=ProbeFailure.TIMEOUT)

    record = check(
        "https://example.com",
        entitlement=reach("example.com", browser_target="site"),
        prober=Prober({"https://example.com": down}),
        browser=browser,
        targets=site(),
        rendered=True,
    )

    assert record.browser is BrowserUse.NO_PAGE
    assert browser.handed == []


def test_a_surface_that_can_write_is_never_handed_to_the_browser() -> None:
    """This tool declares no side effect. Delete this and a declared surface that admits a click
    is handed to the browser by a tool the leash treats as a read, and the page decides what
    the click does."""
    browser = Browser()

    record = check(
        "https://example.com",
        entitlement=reach("example.com", browser_target="site"),
        browser=browser,
        targets=site(Verb.OPEN, Verb.READ, Verb.CLICK),
        rendered=True,
    )

    assert record.browser is BrowserUse.NOT_AVAILABLE
    assert browser.handed == []


@pytest.mark.parametrize("browser_target", [None, "another_site"], ids=["no grant", "other target"])
def test_the_browser_keeps_its_own_grant(browser_target: str | None) -> None:
    """See `THE_BROWSER_KEEPS_ITS_OWN_GRANT`. Delete this and a run that may check a website
    but may not use the browser reaches the browser anyway, by asking for the rendered page."""
    browser = Browser()

    record = check(
        "https://example.com",
        entitlement=reach("example.com", browser_target=browser_target),
        browser=browser,
        targets=site(),
        rendered=True,
    )

    assert record.browser is BrowserUse.NOT_AVAILABLE
    assert browser.handed == []


def test_an_install_with_no_browser_still_answers_the_http_check() -> None:
    """The HTTP check stands on its own. Delete this and asking for the rendered page on an
    install with no browser either raises or loses the status, the certificate and the time
    that were already measured."""
    record = check(
        "https://example.com",
        entitlement=reach("example.com", browser_target="site"),
        targets=site(),
        rendered=True,
    )

    assert record.browser is BrowserUse.NOT_AVAILABLE
    assert record.outcome is ChainEnd.ANSWERED
    assert record.status == 200


# ------------------------------------------------------------------ registration


def test_the_tool_registers_as_a_typed_read_that_runs_nothing() -> None:
    """The registry is the one door, and it refuses a malformed name, a write asking only to
    read, an untyped result and a duplicate description. Delete this and the tool can drift out
    of any of those unnoticed until startup, and a name reading as an executor would put it
    beside `skill.run_script` as a second way to run code."""
    tool = WebsiteCheckTool(resolver=Resolver(), prober=Prober())
    registry = ToolRegistry()

    registered = register_website_check(registry, tool)
    registry.freeze()

    assert registered.name == "website.check_site"
    assert registered.definition.description != READ_SURFACE.description
    assert registered.definition.side_effect is SideEffect.NONE
    assert registered.definition.identity_mode is IdentityMode.DELEGATED
    assert registered.effect is EffectClass.READ
    assert registered.capability == Capability(value="read:website_check")
    assert registered.result_contract is ResultContract.TYPED
    assert registered.object_name == "website_check"
    assert set(registered.definition.args_schema["properties"]) == {
        "address",
        "inspect_rendered_page",
    }
    assert_single_execution_path(registry)
