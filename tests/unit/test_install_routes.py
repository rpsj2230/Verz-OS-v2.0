"""The five install screens over HTTP: who may open each, and what each says when it cannot look.

Driven through the real application, with the token machinery, the identity directory and the
key source imported from `tests/unit/test_api_routes.py` rather than rebuilt. What is under test
here is five capabilities and not an identity: the same six people sign in the same way and only
what they hold over the deployment differs, and a second copy of a JWS builder would be a second
place for a token to be minted subtly differently, which fails looking like a permission bug.

**Every refusal here has a sibling that reads.** A guard tested only by its refusals is
satisfied by five routes that refuse everybody, and four of these five surfaces answer from
nothing but the source tree, so the positive case is cheap and there is no excuse for leaving it
out.

**The two unread surfaces are tested both ways, which is the only way the sentence means
anything.** `backup_objects` and `throttle_source` are attached to `app.state` by the fixtures
below and by nothing in this repository, so the tests that wire them are the ones proving the
route is not simply hard-coded to answer a sentence, and the tests that do not are the ones
proving it does not answer an empty panel instead. A route that always returned the sentence
would pass half of this file.

**The department-scoped case is a reading and not a refusal, and that is the decision under
test.** `brain.console.screens.for_department` withholds Rate limits from a department admin's
menu and offers the other four install screens, which `tests/unit/test_screens.py::
test_a_department_admin_is_offered_every_screen_but_the_one_that_would_disclose` pins as
M27.5.10 and argues at length. That is a menu decision rather than an authorisation, so the
route refuses nobody for it: what happens at a department's scope is that
`brain.console.installation.throttled_now` matches no row and the list comes back empty with no
count of what was dropped. Both halves are asserted here.

Task ids: M27.7.25, M27.7.27
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.installation import Fact as InstallationFact
from brain.console.installation import Source
from brain.console.reads import Plane, plane_capability
from brain.console.screens import NOT_AT_DEPARTMENT_SCOPE, for_department, navigation, screen
from brain.console.version_view import (
    COMMIT_FACT,
    PINNED_FACT,
    Running,
    Standing,
    Told,
    Unanswered,
    Unasked,
)
from brain.console.version_view import panel as updates_panel
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.deployment.release_feed import CHECK_VARIABLE, FEED_VARIABLE, ReleaseWatch
from brain.install_routes import (
    CAPACITY_READ,
    INSTALL_READ,
    LIMITS_READ,
    NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS,
    NOTHING_HERE_READS_THE_BACKUP_BUCKET,
    RECOVERY_READ,
    UPDATES_READ,
    FactView,
    LimitsView,
    RecoveryPanelView,
    RecoveryView,
    updates_view,
)
from brain.ops.install_docs import drill_figures
from brain.ops.limits import Limit, LimiterState, LimitScope
from brain.ops.recovery import Coverage
from brain.ops.release_manifest import ReleaseManifest
from brain.ops.reliability import recovery_objective
from brain.settings import settings_from
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

INSTALL_PATH = f"{API_PREFIX}/install"
UPDATES_PATH = f"{API_PREFIX}/install/updates"
RECOVERY_PATH = f"{API_PREFIX}/install/recovery"
LIMITS_PATH = f"{API_PREFIX}/install/limits"
CAPACITY_PATH = f"{API_PREFIX}/install/capacity"

#: Every address this router serves, in the order the console lists the screens.
#:
#: Written out rather than read off the application, because it is the subject: a route that
#: stopped being mounted would make a list derived from the application shorter and every
#: assertion over it would go on passing.
EVERY_SURFACE: tuple[str, ...] = (
    INSTALL_PATH,
    UPDATES_PATH,
    RECOVERY_PATH,
    LIMITS_PATH,
    CAPACITY_PATH,
)

WHOLE = Scope.unrestricted()
ONE_DEPARTMENT = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))


def _grant(capability: Capability, scope: Scope) -> Grant:
    return Grant(capability=capability, scope=scope)


#: The plane grant every one of these screens needs beside its own capability.
#:
#: `brain.console.reads.permitted` asks for both and the router calls that function rather than
#: checking the capability alone, so a caller holding `read:release` and no console plane is
#: refused. All five of these screens are `Plane.CONFIGURATION`; the grant below is for the
#: widest plane, because `admits` nests and a reader of content may certainly see configuration.
THE_CONSOLE_PLANE: Grant = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)


#: What each of `test_api_routes`' people holds over this deployment.
#:
#: Deliberately one capability each for four of them, so a test can ask what holding exactly one
#: of the five buys: a caller who reaches one surface and is refused the other four proves the
#: five checks are five checks rather than one check repeated.
#:
#: `u_prefix` holds the rate limit capability narrowed to one department, which is the reader
#: M27.5.10 is about, and is why that grant is a department clause rather than any other shape.
INSTALL_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (THE_CONSOLE_PLANE,),
    "u_narrow": (THE_CONSOLE_PLANE, _grant(INSTALL_READ, WHOLE)),
    "u_prefix": (THE_CONSOLE_PLANE, _grant(LIMITS_READ, ONE_DEPARTMENT)),
    "u_wide": (THE_CONSOLE_PLANE, _grant(RECOVERY_READ, WHOLE)),
    "u_admin": (
        THE_CONSOLE_PLANE,
        _grant(INSTALL_READ, WHOLE),
        _grant(UPDATES_READ, WHOLE),
        _grant(RECOVERY_READ, WHOLE),
        _grant(LIMITS_READ, WHOLE),
        _grant(CAPACITY_READ, WHOLE),
    ),
    "u_elsewhere": (THE_CONSOLE_PLANE, _grant(CAPACITY_READ, WHOLE)),
}

#: An `amr` a Keycloak session carries when a second factor was used. A literal rather than a
#: value read out of the module that decides it, for the reason `test_routing_routes` gives
#: about its own: reading the constant would compare it against itself.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

#: Far outside any plausible wall clock, because what these tests are about is not the present.
#: See `CLAUDE.md` on `test_memory_formation.py`: a fixture with a date near today is a clock.
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)


class InstallStore:
    """A `brain.gate.resolve.EntitlementStore` over `INSTALL_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=INSTALL_GRANTS[principal_id])


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=InstallStore(),
        cache=NoCache(),
    )


def _app() -> FastAPI:
    """The real application, built the way a deployment builds it.

    `create_app` produces the router registration under test as well as the routes: a test that
    mounted the router itself would prove the routes work and not that they are served, which is
    the failure this repository keeps finding.
    """
    return create_app(Settings(env="development"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An install with neither of the two optional readers, which is every install today."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        yield c


#: A list address no install has, for the tests that switch the check on.
A_LIST = "https://releases.example.invalid/brain/releases"


def _app_with(variables: Mapping[str, str]) -> FastAPI:
    """The real application, built from exactly these variables and nothing on this machine.

    `settings_from` rather than `Settings(...)`, because the fields under test are read under
    names pydantic populates from the environment, and a test that set them as keyword
    arguments would not be testing the names an install sets.
    """
    return create_app(settings_from({"BRAIN_ENV": "development", **variables}))


class HeldList:
    """A release list that does not answer until the test lets it.

    `answered` is filled only when the fetch returns, so a response that arrives while it is
    still empty is a response the route gave without waiting for the list.
    """

    def __init__(self, *tags: str) -> None:
        self.body = json.dumps(
            [
                {
                    "tag_name": tag,
                    "draft": False,
                    "prerelease": False,
                    "html_url": f"https://releases.example.invalid/{tag}",
                }
                for tag in tags
            ]
        ).encode()
        self.gate = threading.Event()
        self.asked: list[str] = []
        self.answered: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        self.gate.wait(timeout=5)
        self.answered.append(url)
        return self.body


def looked(watch: ReleaseWatch) -> None:
    """Wait, from the test's own thread, for the look a request started to finish."""
    for _ in range(500):
        if watch.last is not None and not watch.looking:
            return
        time.sleep(0.01)
    msg = "the look never finished"
    raise AssertionError(msg)


def get(c: TestClient, pid: str, path: str) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(path, headers={"authorization": f"Bearer {token}"})
    return response


def bucket_holding(*objects: tuple[str, str]) -> Any:
    """A `brain.install_routes.BackupObjects` over a fixed listing.

    A closure rather than a class, because the protocol has one method and the thing under test
    is what the route does with what it returns.
    """

    def read() -> tuple[tuple[str, str], ...]:
        return objects

    return read


def manifest_object(*, coverage: Coverage, at: datetime) -> tuple[str, str]:
    """One backup manifest in the bucket, as `brain.ops.backup_manifest.read_manifests` reads it.

    Written as the JSON a real run would leave rather than as a `Backup` built in memory,
    because a test that built the value the function under test produces has not tested that
    function: the parser is half of what makes the panel right, and handing the route a ready
    `Backup` would exercise the consumer twice.
    """
    stamp = at.isoformat()
    return (
        f"{coverage.value}-{int(at.timestamp())}.manifest.json",
        (
            '{"coverage": "' + coverage.value + '", '
            '"taken_at": "' + stamp + '", '
            '"recoverable_to": "' + stamp + '", '
            '"size_bytes": 4096}'
        ),
    )


def throttling(*rows: Limit) -> Any:
    """A `brain.install_routes.ThrottleSource` whose every limit is already over.

    The state is built by recording each limit's own ceiling's worth of requests through
    `LimiterState.record`, so the window arithmetic the route reaches is
    `brain.ops.limits.check`'s and not a boolean this file set. A state asserted to be over
    would make `throttled_now` a function this test had already answered for.
    """

    def source(now: datetime) -> tuple[Sequence[Limit], LimiterState]:
        state = LimiterState()
        for one in rows:
            for _ in range(one.limit):
                state = state.record(now, (one,))
        return rows, state

    return source


def a_limit(*, subject: str, scope: LimitScope = LimitScope.PRINCIPAL) -> Limit:
    """One allowance of two requests a minute.

    `period` is part of a limit's key because one subject legitimately has several, so it is
    named here rather than defaulted: two rows differing only in period are two windows, and a
    fixture that left them sharing one would be counting one subject's minute and day together.
    """
    return Limit(scope=scope, subject=subject, period="minute", limit=2, window_seconds=60)


def facts_of(body: Any) -> dict[str, dict[str, str]]:
    """The facts on a response, by name, so an assertion names a fact rather than an index."""
    return {one["name"]: one for one in body["facts"]}


# --- what a caller holding the capability is answered -----------------------------------------


def test_this_install_answers_the_profile_the_release_and_the_migration_level(
    client: TestClient,
) -> None:
    """The positive case for `/install`, and the sibling of every refusal below.

    Three facts are asserted by name and by source rather than by counting the list, because the
    list grows with every installation setting the wizard learns to hold and a count would go
    red for a reason nobody cares about. The release is unknown outside a built image, which is
    the case this machine is in and the case that matters: `Fact` refuses an unknown value
    carrying a string, so an unknown release on this response is a row with a sentence and no
    number rather than a plausible commit.

    The migration level is `declared` and never `measured` here, which is the whole of
    `A_CONNECTION_OPENED_OUTSIDE_THE_POOL_IS_A_CONNECTION_NOBODY_BUDGETED`: the route does not
    ask the database what revision it is on, so it must not label the head the source carries as
    a measurement.

    Delete this and the four refusal tests below are satisfied by a route that refuses
    everybody, and the one field somebody reads before deciding whether they are patched could
    be labelled measured while being read out of the source tree."""
    response = get(client, "u_narrow", INSTALL_PATH)

    assert response.status_code == 200
    facts = facts_of(response.json())
    assert facts["profile"]["source"] == Source.DECLARED.value
    assert facts["profile"]["value"] == Settings(env="development").profile
    assert facts["release"]["source"] == Source.UNKNOWN.value
    assert facts["release"]["value"] == ""
    assert facts["release"]["because"].strip() != ""
    assert facts["migration level"]["source"] == Source.DECLARED.value


def test_the_version_panel_names_no_release_and_says_what_would_have_to_change(
    client: TestClient,
) -> None:
    """The positive case for `/install/updates`, and it is a panel that refuses to answer.

    That is not a contradiction and it is the point of M42.3.9 being served rather than claimed.
    The release marker and the image pin are files on the host that no compose file mounts into
    this container, so `running_release` is handed the built commit and nothing else, names no
    release, and `standing_of` answers that there is nothing to compare a newer release against.
    What the panel owes the reader in that state is a sentence saying why and a sentence saying
    what to do, and both are on the response and both come from
    `brain.console.version_view.ANSWERS` rather than from anything a browser composed.

    The standing is asserted against the enumeration rather than against the string, so a
    renamed member fails here rather than being silently compared to a literal nobody updated.

    Delete this and the panel could be served with an empty `says`, which renders as a heading
    with nothing under it, on the screen a client reads before deciding they are up to date."""
    response = get(client, "u_admin", UPDATES_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["running"]["tag"] == ""
    assert body["running"]["cannot_say"].strip() != ""
    assert body["standing"] == Standing.UNKNOWN_RUNNING.value
    assert body["says"].strip() != ""
    assert body["what_to_do"].strip() != ""
    assert body["told"] is None
    assert body["unanswered"] is not None
    assert body["told_days_ago"] is None


def test_capacity_answers_both_memory_figures_and_every_declared_database(
    client: TestClient,
) -> None:
    """The positive case for `/install/capacity`, and the one surface with nothing unread.

    `deployed_mib` is null because this container mounts no compose file, and null rather than a
    copy of the declared figure is the property: two numbers equal by construction read as
    agreement between independent measurements, and agreement is what somebody opens this screen
    to check. A route that defaulted it would pass every other assertion here.

    The databases are asserted against `brain.ops.connections.DATABASES` rather than against a
    count, because the interesting failure is one going missing rather than the number changing.

    Delete this and the capacity screen could answer a deployed figure it did not measure, on
    the screen whose whole subject is whether this deployment has headroom."""
    from brain.ops.connections import DATABASES

    response = get(client, "u_elsewhere", CAPACITY_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["memory"]["profile"] == Settings(env="development").profile
    assert body["memory"]["host_total_mib"] > 0
    assert body["memory"]["deployed_mib"] is None
    assert [one["database"] for one in body["connections"]] == [one.name for one in DATABASES]
    for one in body["connections"]:
        assert one["headroom"] == one["admissible"] - one["demand"]


# --- a source nothing here can read, both ways ------------------------------------------------


def test_an_install_with_no_bucket_reader_is_told_nobody_looked_rather_than_nothing_copied(
    client: TestClient,
) -> None:
    """**The rule this whole group turns on.** A recovery panel built from no observations
    answers `NOTHING_COPIED`, which is a statement about the install, and on a process holding
    no reader it is a statement nobody established. Nothing copied and nobody looked are
    different facts and the difference is the entire value of a screen somebody reads before
    deciding whether to worry.

    The assertion is that there is no panel at all rather than that the panel says something
    cautious, because a panel is the thing a renderer draws rows from and a cautious panel with
    three empty coverage rows is the reassuring blank this screen exists to refuse.

    Delete this and the route may be changed to build a panel out of empty sequences, which
    renders as an install whose backups have never run and reads as measured."""
    response = get(client, "u_wide", RECOVERY_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["panel"] is None
    assert body["unread"] == NOTHING_HERE_READS_THE_BACKUP_BUCKET


def test_a_wired_bucket_reader_produces_a_panel_from_the_records_it_read(
    client: TestClient,
) -> None:
    """The sibling of the test above, and the one that proves the sentence is a branch rather
    than the route's only answer.

    The bucket holds a copy of one coverage and no rehearsal record at all, so the panel's
    verdict is `nothing copied`: the schedule covers three coverages and two of them have
    nothing behind them. That is the honest answer for the bucket handed in, and asserting it
    rather than a reassuring one is deliberate, because every reassuring answer on this panel is
    refused in `Panel.__post_init__` and a test that wanted one would have to build an install
    that does not exist.

    `last_verified` is a fact with a sentence and no value, which is the field the screen is
    named after: a null there is where a renderer draws a dash and a dash beside a backup date
    reads as not applicable.

    Delete this and the route could be hard-wired to the sentence, and attaching a real reader
    would change nothing while every test above went on passing."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.backup_objects = bucket_holding(
            manifest_object(coverage=Coverage.DATABASE, at=LONG_AGO)
        )
        response = get(c, "u_wide", RECOVERY_PATH)

    assert response.status_code == 200
    panel = response.json()["panel"]
    assert panel is not None
    assert response.json()["unread"] == ""
    assert [one["coverage"] for one in panel["copies"]] == [one.value for one in Coverage]
    assert panel["last_verified"]["source"] == Source.UNKNOWN.value
    assert panel["last_verified"]["because"].strip() != ""
    assert panel["drill_is_due"] is True
    assert panel["says"].strip() != ""


def test_rate_limits_answers_the_ceilings_and_no_empty_list_of_who_is_throttled(
    client: TestClient,
) -> None:
    """The ceilings are readable here and the throttling list is not, and the response says which
    half is which.

    An empty throttling list reads as nobody being throttled, which is the flattering direction
    on a screen an operator opens during an incident. So the ceilings are answered whole, the
    list is absent, and the reason is beside it.

    The ceilings are asserted against `brain.ops.limits.ceilings()` rather than against a count,
    and `derived` is checked to be present on every row because a daily figure calculated from a
    per-minute one always flatters the source.

    Delete this and the route could answer an empty list on every install, which is the one
    answer a person acts on by not acting."""
    from brain.ops.limits import ceilings

    response = get(client, "u_admin", LIMITS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["throttled"] is None
    assert body["unread"] == NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS
    assert [one["name"] for one in body["ceilings"]] == [one.name for one in ceilings()]
    assert all("derived" in one for one in body["ceilings"])


def test_a_wired_throttle_source_answers_the_rows_this_readers_grant_matches(
    client: TestClient,
) -> None:
    """The sibling of the test above, and the positive half of the narrowing rule.

    Two principals are over their ceiling. The reader holds `read:rate_limit` unrestricted, so
    both rows reach them, with the ceiling and the wait and no count of refused requests beside
    either name.

    The state is built by recording real requests through `LimiterState.record` rather than by
    asserting a window is over, so what decides each row is `brain.ops.limits.check` and the
    test has not answered the question it is asking.

    Delete this and the narrowing test below is satisfied by a route that returns nothing to
    everybody, which is the shape a scoped listing fails into most quietly."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.throttle_source = throttling(a_limit(subject="p_one"), a_limit(subject="p_two"))
        response = get(c, "u_admin", LIMITS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["unread"] == ""
    assert sorted(one["subject"] for one in body["throttled"]) == ["p_one", "p_two"]
    for one in body["throttled"]:
        assert one["retry_after_seconds"] > 0
        assert set(one) == {"scope", "subject", "limit", "retry_after_seconds"}


# --- M27.5.10: the installation's screens at a department's scope ------------------------------


def test_a_department_scoped_reader_is_answered_no_throttling_rows_and_no_count_of_them(
    client: TestClient,
) -> None:
    """**M27.5.10 as this router honours it, and it is a reading rather than a refusal.**

    `brain.console.screens.for_department` takes Rate limits out of a department admin's menu
    and that is a menu decision: the function's own docstring says a caller holding
    `read:rate_limit` reaches the address whatever it returns, because the tool decides that.
    What the tool decides is `brain.console.installation.throttled_now`, which matches each row
    against the scope on the reader's grant. `_limit_row` offers `{scope, subject}`,
    `Clause.matches` refuses a field the row does not have, and a grant clause naming a
    department therefore matches nothing.

    So the answer is 200 with an empty list, the ceilings unchanged, and nothing anywhere saying
    how many rows there were. The last of those is the assertion that matters: the response
    carries no total, no truncated flag and no count, so a reader cannot subtract their own
    empty list from anything.

    Delete this and a department-scoped reader could be answered every principal in the company
    who is currently being throttled, which is a directory of who is busy assembled from a
    screen whose subject looks like configuration."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.throttle_source = throttling(a_limit(subject="p_one"), a_limit(subject="p_two"))
        theirs = get(c, "u_prefix", LIMITS_PATH)
        unrestricted = get(c, "u_admin", LIMITS_PATH)

    assert theirs.status_code == 200
    assert theirs.json()["throttled"] == []
    assert len(unrestricted.json()["throttled"]) == 2
    assert theirs.json()["ceilings"] == unrestricted.json()["ceilings"]
    assert set(theirs.json()) == {"ceilings", "throttled", "unread"}


def test_rate_limits_is_the_one_install_screen_a_department_admin_is_not_offered() -> None:
    """Where the rule this router honours actually lives, asserted rather than cited.

    The five screens this router serves are `install`, `updates`, `recovery`, `limits` and
    `connections`. Of those, `for_department` drops exactly one, and the argument for dropping
    it is a `Disclosure` naming what a department-scoped reader would learn, the row form that
    cannot carry a department, and what would have to change. The other four are offered,
    deliberately, and `tests/unit/test_screens.py::
    test_a_department_admin_is_offered_every_screen_but_the_one_that_would_disclose` is where
    that decision is argued: a screen that renders empty at a department's scope has said the
    rows this reader may see are none, and withholding it instead is the subtraction disclosure.

    Asserted here as well as there because this is the file somebody opens when they add a sixth
    install screen, and the failure to avoid is a screen about the deployment being withheld by
    habit, or a screen listing people being offered by habit.

    Delete this and either mistake can be made with nothing between the two lists comparing
    them."""
    # Exactly the five capabilities this router asks for, so the menu computed from them is the
    # menu of the five screens it serves and nothing else. Built from the router's constants
    # rather than from the registry's, because the question is what a person who can open every
    # address this module registers is offered.
    everything = EntitlementSet(
        principal_id="p_everything",
        grants=(
            THE_CONSOLE_PLANE,
            *(
                _grant(one, WHOLE)
                for one in (INSTALL_READ, UPDATES_READ, RECOVERY_READ, LIMITS_READ, CAPACITY_READ)
            ),
        ),
    )

    ours = {one.key for one in navigation(everything)}
    theirs = {one.key for one in for_department(everything)}

    assert ours == {"install", "updates", "recovery", "limits", "connections"}
    assert ours - theirs == {"limits"}
    assert "limits" in {one.screen for one in NOT_AT_DEPARTMENT_SCOPE}


def test_each_route_asks_for_the_capability_its_own_screen_declares() -> None:
    """The five capabilities are read out of the registry and are not typed again.

    Asserted against `brain.console.screens.screen(...)` by key, which is the other end of the
    pairing: a capability retyped in the router would be correct on the day it was typed and
    would survive a change to the registry with nothing comparing the two, and the failure is
    permissive, because the route goes on answering under a capability the screen no longer
    requires.

    Delete this and the router can drift from the menu, so a screen appears for somebody who is
    then refused at its address, or worse, does not appear for somebody the route answers."""
    assert screen("install").read.requires == INSTALL_READ
    assert screen("updates").read.requires == UPDATES_READ
    assert screen("recovery").read.requires == RECOVERY_READ
    assert screen("limits").read.requires == LIMITS_READ
    assert screen("connections").read.requires == CAPACITY_READ

    # The two release screens share a capability deliberately, which `brain.console.screens`
    # argues by name: a capability of its own would be unreachable from every grant an install
    # has already written, because `Capability.covers` expands only a trailing `.*`.
    assert INSTALL_READ == UPDATES_READ


# --- the refusals, and what they do not say ---------------------------------------------------


def test_a_caller_holding_nothing_is_refused_every_install_surface(client: TestClient) -> None:
    """The refusal sibling of every positive test above, over all five addresses at once.

    404 rather than 403, which is `brain.app.handle_brain_error`'s rule: DENIED and ABSENT leave
    with one status and one body, because a caller who can tell a refusal from an absence can
    map what exists by asking.

    Delete this and one of the five routes can lose its check while the other four keep theirs,
    which is exactly the shape a copied route acquires."""
    for path in EVERY_SURFACE:
        response = get(client, "u_none", path)
        assert response.status_code == 404, path


def test_holding_one_install_capability_opens_one_surface_and_refuses_the_other_four(
    client: TestClient,
) -> None:
    """Five checks rather than one check repeated, proved from the caller's side.

    Three callers, each holding exactly one of the five capabilities, and each answered at one
    address and refused at the rest. The two release screens share a capability, so the caller
    holding it reaches two, which is asserted rather than worked around: it is the decision
    `brain.console.screens` argues for and a test that hid it would be pinning the wrong thing.

    Delete this and a route could be wired to the wrong screen's capability, which every
    single-address test above would go on passing."""
    expected: dict[str, set[str]] = {
        # `read:release`, which is This install and Version and updates.
        "u_narrow": {INSTALL_PATH, UPDATES_PATH},
        "u_wide": {RECOVERY_PATH},
        "u_elsewhere": {CAPACITY_PATH},
    }
    for pid, answerable in expected.items():
        for path in EVERY_SURFACE:
            response = get(client, pid, path)
            wanted = 200 if path in answerable else 404
            assert response.status_code == wanted, f"{pid} at {path}"


def test_a_refusal_names_neither_the_capability_nor_which_surface_was_asked_for(
    client: TestClient,
) -> None:
    """One refusal for five surfaces, so the body says nothing about which of five grants a
    caller is short of.

    The messages are compared to each other rather than to a literal, because the literal is the
    thing under test and an assertion against it would be satisfied by every value it could
    hold. What is asserted about the content is the negative: no capability value and no screen
    key appears anywhere in the body.

    Delete this and a route can grow a helpful sentence naming what it wanted, which turns the
    404 into an oracle for what this install holds."""
    bodies = [get(client, "u_none", path).json() for path in EVERY_SURFACE]
    messages = {one["message"] for one in bodies}

    assert len(messages) == 1
    only = messages.pop()
    for capability in (INSTALL_READ, RECOVERY_READ, LIMITS_READ, CAPACITY_READ):
        assert capability.value not in only
    for key in ("install", "updates", "recovery", "limits", "connections"):
        assert key not in only.split()


def test_a_caller_with_no_grant_cannot_tell_whether_this_process_can_read_the_bucket() -> None:
    """**The order of the two checks, which is the property the module docstring is about.**

    The capability is checked before anything is read, so an unentitled caller is refused
    identically on a process holding a bucket reader and on one holding none. Reading first
    would make the unentitled answer depend on how this deployment is wired, which publishes the
    deployment's state to anybody who can reach the port.

    Both responses are compared whole rather than by status, because the interesting leak is a
    difference in the body: a process that read first and then refused could answer the same
    404 with a different trace shape or a different message.

    Delete this and moving the capability check below the reader is a change that passes every
    other test in this file."""
    wired = _app()
    bare = _app()
    with (
        TestClient(wired, raise_server_exceptions=False) as with_reader,
        TestClient(bare, raise_server_exceptions=False) as without,
    ):
        wired.state.gate = _wiring()
        wired.state.backup_objects = bucket_holding(
            manifest_object(coverage=Coverage.DATABASE, at=LONG_AGO)
        )
        bare.state.gate = _wiring()
        refused_here = get(with_reader, "u_none", RECOVERY_PATH)
        refused_there = get(without, "u_none", RECOVERY_PATH)

    assert refused_here.status_code == refused_there.status_code == 404
    assert refused_here.json()["message"] == refused_there.json()["message"]


def test_no_install_response_carries_a_total_or_a_count_of_anything_withheld(
    client: TestClient,
) -> None:
    """No screen in this group counts. The throttling list is the one collection a reader's grant
    narrows, so it is the one where a number would be a subtraction, and the rule is kept on all
    five rather than on the one that needs it: a screen counting where it was harmless is the
    worked example somebody copies onto a screen where it is not.

    Asserted over the response bodies rather than over the response models, because the leak
    would arrive through whatever a model inherited: `brain.api.Page` carries `total`, and a
    page-shaped response added to this router later would bring it along.

    Delete this and a `total` can be added to the throttling list in one line, on the one
    listing here whose rows are people."""
    forbidden = {"total", "truncated", "hidden", "withheld", "omitted", "count"}
    for path in EVERY_SURFACE:
        body = get(client, "u_admin", path).json()
        assert forbidden.isdisjoint(_every_key(body)), path


def _every_key(value: Any) -> set[str]:
    """Every key anywhere in a response body, however deeply nested."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inside in value.items():
            found.add(str(key))
            found |= _every_key(inside)
    elif isinstance(value, list):
        for inside in value:
            found |= _every_key(inside)
    return found


def test_an_install_surface_refuses_an_unauthenticated_caller_before_anything_else(
    client: TestClient,
) -> None:
    """Every address under the prefix authenticates, and these five are not an exception.

    401 rather than 404, which is the one place the two are allowed to differ: nothing has been
    asked about yet, so there is nothing for the distinction to disclose.

    Delete this and a route mounted without the `asking` dependency would answer everybody, and
    nothing else in this file would notice because every other test sends a token."""
    for path in EVERY_SURFACE:
        assert client.get(path).status_code == 401, path


# --- the two shapes that refuse to be built wrong ---------------------------------------------


def test_a_recovery_view_holds_a_panel_or_a_reason_for_having_none_and_never_both() -> None:
    """The model refuses the two shapes a renderer cannot draw honestly.

    Both together is a verdict about backups with a caveat beside it, and a caveat beside a
    verdict is read as the verdict. Neither is a screen that has not loaded, which is the worst
    of the three: it is indistinguishable from a slow network and the reader waits and then
    stops.

    Both directions are asserted, because a validator written as one comparison passes the other
    case for free and the half nobody tests is the half that is wrong.

    Delete this and the route may be changed to return an empty `RecoveryView`, which serialises
    as `{"panel": null, "unread": ""}` and renders as nothing at all."""
    with pytest.raises(ValidationError):
        RecoveryView()

    with pytest.raises(ValidationError):
        RecoveryView(panel=None, unread="")

    assert RecoveryView(unread="nobody looked").panel is None


def test_a_limits_view_holds_a_throttling_list_or_a_reason_for_having_none_and_never_both() -> None:
    """The same rule on the other unread surface, and it matters more here.

    An absent list and an empty list serialise differently and read identically to somebody
    skimming: both draw no rows. So the model refuses a response that carries neither, and
    refuses one that carries both, and the route's two branches are the only two shapes it can
    produce.

    Delete this and `throttled: []` with an `unread` sentence beside it becomes constructible,
    which tells a reader nobody is throttled and that nobody looked, at the same time."""
    with pytest.raises(ValidationError):
        LimitsView(ceilings=[])

    with pytest.raises(ValidationError):
        LimitsView(ceilings=[], throttled=[], unread="nothing enumerates the windows")

    assert LimitsView(ceilings=[], throttled=[]).unread == ""


def test_an_unread_surface_answers_a_sentence_a_person_can_act_on() -> None:
    """The two sentences are written for somebody with a server and no source tree.

    Held to the same bar `brain.console.recovery_view.ANSWERS` and
    `brain.console.version_view.ANSWERS` are held to, and for the reason those are: a reader who
    is told a thing cannot be read and not what to do about it has been given a shrug. The
    assertion is that neither names a module, a function or a task id, which is the way this
    kind of sentence usually goes wrong.

    Delete this and either can be shortened to the name of the class that is missing."""
    for sentence in (
        NOTHING_HERE_READS_THE_BACKUP_BUCKET,
        NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS,
    ):
        assert len(sentence.split()) >= 30
        assert "brain." not in sentence
        assert "M27" not in sentence and "M30" not in sentence


def test_a_telling_that_went_off_long_ago_is_stale_rather_than_current() -> None:
    """The panel this route serves is `brain.console.version_view.panel`, and the boundary it
    turns on is reachable only through a clock that is a parameter.

    Asserted here rather than left to that module's own tests because what this file is about is
    what the route hands over: the route passes `asked.now` and the module's default window, and
    a route that passed a window of its own would make the console and the module disagree about
    how long a reassurance lasts.

    The instants are 2019 and 2999 deliberately, for the reason
    `tests/unit/test_scope_and_capability.py` gives: a fixture with a date near today is a clock
    and it goes off.

    Delete this and the route could pass a window argument, and the one answer on this panel
    whose whole value is that somebody looked recently would be decided somewhere else."""
    running = Running(
        tag="v1.2.0",
        facts=(InstallationFact(name="release marker", source=Source.DECLARED, value="v1.2.0"),),
    )
    told = Told(tag="v1.2.0", at=LONG_AGO, by="an administrator, once")

    fresh = updates_panel(running, told, now=LONG_AGO + timedelta(days=1))
    aged = updates_panel(running, told, now=datetime(2999, 1, 1, tzinfo=UTC))

    assert fresh.standing is Standing.CURRENT
    assert aged.standing is Standing.STALE


# --- the guards a first pass could not reach --------------------------------------------------


def test_a_process_built_without_settings_reports_a_fault_rather_than_answering() -> None:
    """A process with no settings is broken rather than unconfigured, and says so as a 500.

    The alternative this refuses is a `Settings()` constructed in the route, which reads the
    environment a second time and answers about a profile nobody deployed. That is the failure
    `brain.console.installation.install_facts` refuses when it checks the profile itself, and
    `brain.ops.independence` is the sweep that refuses a second reader of an installation value.

    A `Failed` rather than an `Absent`, which is `brain.routing_routes._require_sessions`' rule:
    only a caller who already holds the capability reaches that line, so the 500 discloses
    nothing about how this deployment is wired to anybody who was not already told.

    Delete this and the check can be removed, and every install screen answers about the
    default profile on a process that declared another one."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.settings = None
        answered = get(c, "u_narrow", INSTALL_PATH)
        refused = get(c, "u_none", INSTALL_PATH)

    assert answered.status_code == 500
    # The body, not only the status, and that is the assertion that means anything here. An
    # unguarded route reaches the same 500 through an AttributeError on `None`, which leaves
    # Starlette to answer with plain text and no trace id, so a test reading the status alone
    # cannot tell a fault this module reported from one it fell over. `brain.api.ErrorBody` is
    # what a refusal and a fault both arrive as, and the trace id in it is the whole of what
    # makes a support conversation short.
    body = answered.json()
    assert set(body) == {"message", "trace_id"}
    assert body["trace_id"] != ""

    # And the unentitled caller still gets the refusal rather than the fault, which is the
    # order property again: a 500 here for somebody holding nothing would say this process is
    # misconfigured to anybody who can reach the port.
    assert refused.status_code == 404


def test_a_recovery_view_cannot_hold_a_panel_and_a_reason_for_having_none_at_once() -> None:
    """The other half of the model's refusal, and the half a validator written as one
    comparison passes for free.

    A panel with a sentence beside it saying nothing looked is a verdict about backups with a
    caveat next to it, and a caveat beside a verdict is read as the verdict. The panel built
    here is the alarming one, because the reassuring one is refused by
    `brain.console.recovery_view.Panel` before it could reach this model at all.

    Delete this and `RecoveryView(panel=..., unread=...)` becomes constructible, which tells a
    reader what their copies are and that nobody looked at them, at the same time."""
    panel = RecoveryPanelView(
        profile="standard",
        copies=[],
        last_verified=FactView(
            name="last verified restore",
            source=Source.UNKNOWN.value,
            value="",
            because="no restore has ever been verified on this install",
        ),
        measured_rto_seconds=None,
        assurance="never verified",
        says="no copy this install holds has ever been restored and checked",
        what_to_do="rehearse a restore",
        drill_is_due=True,
        unreadable=[],
    )

    with pytest.raises(ValidationError):
        RecoveryView(panel=panel, unread="nobody looked")

    assert RecoveryView(panel=panel).unread == ""


def test_something_attached_that_is_not_a_reader_is_the_same_as_nothing_attached() -> None:
    """Both optional readers are checked before they are called, and the check is a real branch.

    A process that attached a value of the wrong shape is a misconfigured process, and the
    answer it gets is the one it would get having attached nothing: the sentence saying nobody
    looked. That is the safe direction. The alternative is a `TypeError` inside the route, which
    reaches a caller as a 500 and reads like a bug in the gate rather than like a process
    somebody wired wrongly.

    Delete this and the two `callable` checks can be removed, because nothing else in this file
    attaches anything but a function to either attribute."""
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.backup_objects = "not a reader"
        app.state.throttle_source = "not a reader either"
        recovery = get(c, "u_wide", RECOVERY_PATH)
        limits = get(c, "u_admin", LIMITS_PATH)

    assert recovery.status_code == 200
    assert recovery.json()["panel"] is None
    assert recovery.json()["unread"] == NOTHING_HERE_READS_THE_BACKUP_BUCKET
    assert limits.status_code == 200
    assert limits.json()["throttled"] is None
    assert limits.json()["unread"] == NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS


def test_a_telling_and_an_unanswered_question_reach_a_console_as_two_different_shapes() -> None:
    """`updates_view` splits a union into two nullable fields, and never populates both.

    Asserted against the projection rather than through the route, because reaching either
    shape through a request means configuring a release list and answering it, which is a test
    about `brain.deployment.release_feed` rather than about what a console is handed.

    The two shapes differ in what a reader can do about them, which is why they are two fields
    rather than one tagged object: a telling names who said so, and an unanswered question names
    what went wrong. A console given one field would have to tell them apart itself, which is a
    second copy of a distinction the API has already drawn.

    Delete this and both conditional expressions in `updates_view` can be inverted, which puts a
    telling into the field a page draws a failure reason from."""
    running = Running(
        tag="v1.2.0",
        facts=(InstallationFact(name="release marker", source=Source.DECLARED, value="v1.2.0"),),
    )
    told = Told(
        tag="v1.2.0",
        at=LONG_AGO,
        by="an administrator, once",
        notes="https://releases.example.invalid/v1.2.0",
    )
    unanswered = Unanswered(
        why=Unasked.UNREACHABLE,
        detail="the release list could not be reached",
        at=LONG_AGO,
    )

    said = updates_view(updates_panel(running, told, now=LONG_AGO + timedelta(days=1)))
    silent = updates_view(updates_panel(running, unanswered, now=LONG_AGO + timedelta(days=1)))

    assert said.told is not None
    assert said.told.by == "an administrator, once"
    assert said.told.notes == "https://releases.example.invalid/v1.2.0"
    assert said.unanswered is None

    assert silent.told is None
    assert silent.unanswered is not None
    assert silent.unanswered.why == Unasked.UNREACHABLE.value


def test_a_built_image_reports_its_own_commit_and_a_checkout_reports_that_it_has_none(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest is read on both surfaces, and both branches of its absence are exercised.

    A checkout has no manifest and both screens say so in words rather than falling back to
    something plausible: `brain.console.installation.install_facts` argues that a console
    showing a working tree's commit on a developer's machine and an image's commit in
    production would be showing two different things under one heading.

    A built image carries one, and what the version screen does with it is label it as the
    commit rather than as the release: a client cannot look a commit up in a list of releases,
    ask for its notes, or hand it to the update script. So the running release is still unnamed
    on an install whose containers mount no marker, and the commit is a row beside that.

    `read_manifest` is replaced rather than a file written, because the real one reads a fixed
    path inside a container image and a test that created it would be writing to the machine
    running the suite.

    Delete this and the conditional that turns an absent manifest into an empty commit can be
    fixed to either side, which either hides a built image's commit or invents one for a
    checkout."""
    absent = get(client, "u_admin", UPDATES_PATH).json()
    commit_fact = next(one for one in absent["running"]["facts"] if one["name"] == "built commit")
    assert commit_fact["source"] == Source.UNKNOWN.value
    assert commit_fact["value"] == ""
    assert absent["running"]["commit"] == ""

    a_commit = "c0ffee" * 6 + "abcd"
    monkeypatch.setattr(
        "brain.install_routes.read_manifest",
        lambda: ReleaseManifest(commit=a_commit, built_at=LONG_AGO, task_ids=()),
    )
    built = get(client, "u_admin", UPDATES_PATH).json()
    facts = {one["name"]: one for one in built["running"]["facts"]}

    assert facts["built commit"]["source"] == Source.MEASURED.value
    assert facts["built commit"]["value"] == a_commit
    assert built["running"]["commit"] == a_commit
    # Still no release named, which is the point: the one measured statement is the wrong
    # answer to the question the heading asks.
    assert built["running"]["tag"] == ""
    assert built["standing"] == Standing.UNKNOWN_RUNNING.value

    on_the_install = get(client, "u_admin", INSTALL_PATH).json()
    assert facts_of(on_the_install)["release"]["source"] == Source.MEASURED.value


# --- the running release and the release list (M42.3.9) ----------------------------------------


def test_the_running_release_is_the_image_reference_the_application_was_started_with() -> None:
    """**The version marker, end to end.** The compose files hand the application `APP_IMAGE`,
    `Settings` reads it, and the screen names the release in it with the built commit beside it.
    With the check left off, the standing says so rather than anything about being current.

    Delete this and the route can go back to handing `running_release` the commit alone, which
    is the panel that named no release on every install."""
    app = _app_with({"APP_IMAGE": "ghcr.io/example/brain:v1.4.0"})
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        body = get(c, "u_admin", UPDATES_PATH).json()

    facts = {one["name"]: one for one in body["running"]["facts"]}
    assert body["running"]["tag"] == "v1.4.0"
    assert body["running"]["cannot_say"] == ""
    assert facts[PINNED_FACT]["source"] == Source.DECLARED.value
    assert facts[PINNED_FACT]["value"] == "ghcr.io/example/brain:v1.4.0"
    assert COMMIT_FACT in facts
    assert body["standing"] == Standing.SWITCHED_OFF.value
    assert body["unanswered"]["why"] == Unasked.SWITCHED_OFF.value
    assert CHECK_VARIABLE in body["unanswered"]["detail"]


def test_an_image_reference_that_is_not_a_release_names_none_and_says_why() -> None:
    """The sibling: the same route handed `latest` names no release, because that tag runs
    whatever was newest when it was pulled.

    Delete this and the route could pass any tag through as a release, which the positive test
    above is satisfied by."""
    app = _app_with({"APP_IMAGE": "ghcr.io/example/brain:latest"})
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        body = get(c, "u_admin", UPDATES_PATH).json()

    assert body["running"]["tag"] == ""
    assert "pins no release" in body["running"]["cannot_say"]
    assert body["standing"] == Standing.UNKNOWN_RUNNING.value


def test_the_updates_screen_answers_before_the_release_list_does() -> None:
    """**The page never waits for the list, through the real route.** The list is held until the
    first response has arrived, so the first response saying no look has finished, with the
    list still unanswered, is the route not having waited. Then the list answers, and the next
    load is told a newer release exists, which one, and where its notes are.

    Delete this and the route can await the look again, which passes every other test in this
    file and puts somebody else's server in front of the screen on every load."""
    held = HeldList("v1.5.0")
    watch = ReleaseWatch(fetch=held)
    app = _app_with(
        {
            "APP_IMAGE": "ghcr.io/example/brain:v1.4.0",
            CHECK_VARIABLE: "true",
            FEED_VARIABLE: A_LIST,
        }
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.release_watch = watch
        try:
            first = get(c, "u_admin", UPDATES_PATH)
            assert held.answered == []
        finally:
            held.gate.set()
        looked(watch)
        second = get(c, "u_admin", UPDATES_PATH)

    assert first.status_code == 200
    assert first.json()["standing"] == Standing.NOT_LOOKED_YET.value
    assert first.json()["told"] is None
    assert first.json()["unanswered"] is None
    assert held.asked == [A_LIST]

    body = second.json()
    assert body["standing"] == Standing.BEHIND.value
    assert body["told"]["tag"] == "v1.5.0"
    assert body["told"]["notes"] == "https://releases.example.invalid/v1.5.0"
    assert A_LIST in body["told"]["by"]


def test_a_caller_who_may_not_open_the_screen_makes_the_server_ask_nothing() -> None:
    """The capability is checked before the watch is touched, so somebody who can reach the
    port and holds nothing cannot make this server send a request outside its network, however
    often they ask. The sibling is the test above, where a reader who may open it does.

    Delete this and the look can be started before the refusal, which turns the updates address
    into a way for anybody to make a client's server call out on demand."""
    held = HeldList("v1.5.0")
    held.gate.set()
    watch = ReleaseWatch(fetch=held)
    app = _app_with({CHECK_VARIABLE: "true", FEED_VARIABLE: A_LIST})
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.release_watch = watch
        refused = [get(c, "u_none", UPDATES_PATH) for _ in range(3)]
        time.sleep(0.2)

    assert [one.status_code for one in refused] == [404, 404, 404]
    assert held.asked == []
    assert watch.last is None


def test_the_screen_attaches_one_watch_and_keeps_it() -> None:
    """A process builds its watch the first time the screen is opened and reuses it, so the last
    look is remembered between loads. Something of the wrong kind in its place is replaced rather
    than called.

    Delete this and a watch can be built per request, which starts a look on every load and
    never has a last look to answer from, so the screen says not looked yet for ever."""
    app = _app_with({})
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.release_watch = "not a watch"
        get(c, "u_admin", UPDATES_PATH)
        first = app.state.release_watch
        get(c, "u_admin", UPDATES_PATH)
        second = app.state.release_watch

    assert isinstance(first, ReleaseWatch)
    assert second is first


# --- the rehearsal card, and the control that is not there -------------------------------------
def test_the_recovery_screen_says_how_a_rehearsal_is_done_whether_or_not_anything_looked(
    client: TestClient,
) -> None:
    """M30.3.9 asks for a one-click drill and nothing this process runs can perform one, so the
    screen gets the figures a rehearsal is judged against and the sentence saying why there is no
    control, on both shapes of the answer.

    The figures are held against `brain.ops.install_docs.drill_figures`, which the restore drill
    page is itself held against, and the recovery time against the profile's own objective, so the
    screen, the page an administrator follows and the promise cannot say three different things.

    Delete this and the card can drop off the unread shape, which is the shape every install has,
    or state an interval the drill page does not."""
    unread = get(client, "u_wide", RECOVERY_PATH).json()
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.backup_objects = bucket_holding(
            manifest_object(coverage=Coverage.DATABASE, at=LONG_AGO)
        )
        read = get(c, "u_wide", RECOVERY_PATH).json()

    figures = dict(drill_figures())
    for body in (unread, read):
        card = body["rehearsal"]
        assert card is not None
        assert str(card["every_days"]) == figures["Days between rehearsals"]
        assert str(card["copies_kept_days"]) == figures["Days a copy is kept"]
        assert card["manifest_ends"] == figures["A copy's manifest name ends"]
        assert card["record_ends"] == figures["A drill record's name ends"]
        assert (
            card["promised_recovery_seconds"]
            == recovery_objective(Settings(env="development").profile).rto_seconds
        )
        assert "no control" in card["no_control_here"]


def test_the_recovery_screen_accepts_no_write_and_no_route_offers_a_drill() -> None:
    """A drill button that cannot run a drill must not exist, and the API half of that is that the
    recovery address takes only a read and no address anywhere offers a rehearsal to press.

    Held over the application's own OpenAPI document rather than this router, so a drill route
    added by another module is caught as well. Delete this and a POST that starts nothing could
    be added beside the recovery panel, and a console would draw it as a control that works."""
    paths = _app().openapi()["paths"]

    assert set(paths[RECOVERY_PATH]) == {"get"}
    offered = [
        path
        for path, operations in paths.items()
        if set(operations) - {"get"}
        and any(word in path for word in ("drill", "rehears", "restore"))
    ]
    assert offered == []
