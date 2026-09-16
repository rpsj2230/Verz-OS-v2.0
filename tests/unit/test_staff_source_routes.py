"""The Staff sources screen over HTTP: who is answered what, and what a trial may say.

Driven through the real application. The token machinery, the identity directory and the key
source are imported from `tests/unit/test_api_routes.py` rather than rebuilt, for the reason
`tests/unit/test_govern_routes.py` gives about the same imports: what is under test is a
capability and not an identity, and a second copy of a JWS builder would be a second place for
a token to be minted subtly differently, producing failures that look like permission bugs.

**No database anywhere in this file, and that is the screen rather than the fixture.** The
choice and the location are installation settings and `brain.install.value_of` is their one
reader, so both routes answer without a session. `brain.install.hold_saved` is how this file
sets them, because it is the one writer of that process state and it returns what it replaced,
which is what lets a test put it back; a test that left a setting held would configure the next
one.

**A refusal and an empty answer are compared byte for byte rather than described.** The
property this screen turns on is that a caller holding no capability is answered exactly what a
caller who holds it in one department is answered, because a source sits nowhere and a
department-scoped grant reaches none of them. Asserting that each is "empty" would pass for two
answers that differed in a field, so the two bodies are compared with each other.

**Every refusal has a sibling proving the screen still answers.** A guard tested only by its
refusals is satisfied by a route that refuses everybody, and on this screen that would be
invisible: the refusal *is* an empty page, so a route that answered nobody would look exactly
like a correct route in front of a reader with no grant.

**The credential rule is measured rather than asserted.** `INSTALL_STAFF_SOURCE_LOCATION` is set
to a sentinel that appears nowhere else, and the whole response body and every log line are
searched for it. That is the check `brain.console.staff_source_view.staff_source_gaps` makes
about the rows and this file makes about the bytes that leave the process.

**The trial's success path is exercised against a source built here and never against a
directory.** Nothing in this repository fetches a roster, so a gatherer is attached to
`app.state` and the plan it produces is compared with `dry_run`'s own answer over the same
inputs, which is what stops this file agreeing with a projection that dropped a field.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.staff_source_view import THE_SCREEN
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    Roster,
    StaffRecord,
    selectable_names,
    selected_source,
)
from brain.identity.staff_sync import dry_run
from brain.install import hold_saved, value_of
from brain.ops.jobs import hidden_count_fields
from brain.staff_source_routes import (
    ADDRESSES,
    CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS,
    NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE,
    SCREEN_PATH,
    RoleAssertionView,
    RosterPersonView,
    SelectionView,
    SourceOptionView,
    StaffSourcesView,
    TrialInputs,
    TrialPlanView,
    TrialRunView,
    TrialView,
    sources_offered,
)
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

PAGE_PATH = f"{API_PREFIX}{SCREEN_PATH}"
TRIAL_PATH = f"{PAGE_PATH}/trial"

#: Pinned far outside any plausible wall clock, which is `CLAUDE.md`'s rule about a fixture with
#: a date in it. Nothing here is about the present.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

MAINTENANCE = "maintenance"
WHOLE = Scope.unrestricted()
IN_MAINTENANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value=MAINTENANCE),))

#: The screen's own capability, spelled out rather than read off the registry. A test reading
#: `screen(THE_SCREEN).read.requires` to build the grant it then asserts against would be
#: comparing the registry with itself: repointing the screen's capability would move both sides
#: and stay green. `test_the_capability_this_file_grants_is_the_one_the_registry_requires` is
#: where the two are held together, once, deliberately.
STAFF_SOURCE_CAPABILITY = "read:staff_source"

#: A value that appears nowhere else in this repository, so finding it anywhere is evidence.
#: It stands in for the half of a share link, the tenant or the directory address that
#: `INSTALL_STAFF_SOURCE_LOCATION` carries on a real install.
SENTINEL_LOCATION = "zzsentinel-location-9f2c"

#: The one source that needs no setting at all, so a trial can be run without pointing anything
#: anywhere. `brain.identity.staff_source.SELECTABLE` declares it with `needs=()`.
SPREADSHEET = "spreadsheet"

#: A source that needs a setting, for the refusal a chosen-and-unpointed install meets.
GOOGLE_SHEET = "google_sheet"


def _grant(value: str, scope: Scope) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


def _plane(plane: Plane, scope: Scope = WHOLE) -> Grant:
    return _grant(plane_capability(plane).value, scope)


#: What each of `test_api_routes`' six people holds here.
#:
#: The three planes nest, so a reader granted the content plane reaches the configuration one as
#: well; `u_admin` is therefore granted content alone and the page is expected to answer them,
#: which is `brain.console.reads.admits` being exercised rather than assumed.
STAFF_GRANTS: dict[str, tuple[Grant, ...]] = {
    # Nobody. The answer this screen gives without refusing.
    "u_none": (),
    # The console plane and no screen capability: the half that is usually forgotten.
    "u_prefix": (_plane(Plane.CONFIGURATION),),
    # The screen capability and no plane: the half a `reach.holds` check would let through.
    "u_narrow": (_grant(STAFF_SOURCE_CAPABILITY, WHOLE),),
    # May read the screen and may not run a trial. The plane pulled apart from the capability,
    # which is what `TRIAL_READ` is for.
    "u_wide": (
        _grant(STAFF_SOURCE_CAPABILITY, WHOLE),
        _plane(Plane.CONFIGURATION),
    ),
    # May read the screen and may run a trial.
    "u_admin": (
        _grant(STAFF_SOURCE_CAPABILITY, WHOLE),
        _plane(Plane.CONTENT),
    ),
    # The same person narrowed to one department. A source sits nowhere, so they reach none of
    # them and are answered what `u_none` is answered.
    "u_elsewhere": (
        _grant(STAFF_SOURCE_CAPABILITY, IN_MAINTENANCE),
        _plane(Plane.CONTENT, IN_MAINTENANCE),
    ),
}


class StaffStore:
    """A `brain.gate.resolve.EntitlementStore` over `STAFF_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=STAFF_GRANTS[principal_id])


# ------------------------------------------------------------------ the source and the inputs


@dataclass
class Sheet:
    """A staff source that answers from rows this test wrote, and counts how often it was asked.

    A real `brain.identity.staff_source.StaffSource` rather than a mock, because the protocol
    has exactly one method and a double of it would be the same code with a library between.
    The count is what makes the ordering property assertable: a reader who may not run a trial
    must not cause the source to be read, and the only evidence of that is that nothing asked.
    """

    people: tuple[StaffRecord, ...]
    source: str = SPREADSHEET
    complete: bool = False
    asked: int = 0

    def roster(self) -> Roster:
        self.asked += 1
        return Roster(source=self.source, people=self.people, complete=self.complete)


@dataclass
class Gatherer:
    """A stand-in for whatever a wired process would attach, counting how often it was called.

    The count is the second half of the ordering property. `trial_source_of` returning the
    gatherer is cheap; calling it is what opens a connection and contacts the source on a real
    install, so a reader who reaches nothing must not reach this either.
    """

    sheet: Sheet
    known: Mapping[str, str]
    last_applied: datetime | None = None
    called: int = 0

    def __call__(self, now: datetime) -> TrialInputs:
        self.called += 1
        return TrialInputs(
            source=self.sheet,
            known=self.known,
            last_applied=self.last_applied,
        )


ADA = StaffRecord(work_address="ada@example.test", display_name="Ada", department="maintenance")
GRACE = StaffRecord(work_address="grace@example.test", display_name="Grace")


def _gatherer() -> Gatherer:
    """One person the system already holds and one it does not, which is a plan with both halves."""
    return Gatherer(
        sheet=Sheet(people=(ADA, GRACE)),
        known={"grace@example.test": "u_2", "hopper@example.test": "u_3"},
    )


# ------------------------------------------------------------------------- the wiring


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
        store=StaffStore(),
        cache=NoCache(),
    )


@pytest.fixture
def held() -> Iterator[None]:
    """This install set to the source that needs nothing, with a sentinel in the location.

    Both are held for the duration of one test and put back afterwards. The location is set even
    though the chosen source does not need it, deliberately: the credential check is about a
    value this install carries reaching a response, and a value nothing asks for is exactly the
    one a later edit would print beside a setting's name without anybody noticing.
    """
    before = hold_saved(
        {
            STAFF_SOURCE_SETTING: SPREADSHEET,
            STAFF_SOURCE_LOCATION_SETTING: SENTINEL_LOCATION,
        }
    )
    yield
    hold_saved(before)


@pytest.fixture
def client(held: None) -> Iterator[TestClient]:
    """The real application, with no session factory, which is every deployment today.

    `create_app` produced the router registration under test: a test that mounted the router
    itself would prove the routes work and not that they are served.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        yield c


def get(c: TestClient, path: str, pid: str) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.get(path, headers={"authorization": f"Bearer {token}"})
    return response


def body(c: TestClient, path: str, pid: str) -> Any:
    answer = get(c, path, pid)
    assert answer.status_code == 200, answer.text
    return answer.json()


# -------------------------------------------------------------- what the screen answers


def test_the_screen_lists_every_source_this_install_could_choose(client: TestClient) -> None:
    """Delete this and the screen can stop offering a source and nothing says which.

    The order is asserted as well as the membership, because `SELECTABLE` is declared in the
    order a refusal lists its members in, so a screen that sorted its own rows would disagree
    with the message somebody gets when they mistype a name.
    """
    page = body(client, PAGE_PATH, "u_admin")
    offered = sources_offered([SourceOptionView(**one) for one in page["options"]])

    assert offered == selectable_names()
    assert page["selection"]["name"] == SPREADSHEET


@pytest.mark.parametrize("pid", ["u_none", "u_prefix", "u_narrow", "u_elsewhere"])
def test_a_caller_with_nothing_is_answered_what_a_reader_who_reaches_nothing_is(
    client: TestClient, pid: str
) -> None:
    """Delete this and the difference between a 404 and an empty page says who holds what.

    Four readers and one answer. `u_none` holds nothing; `u_prefix` holds the console plane and
    not the screen's capability; `u_narrow` holds the capability and no plane, which is the case
    a route written with `reach.holds(...)` would answer; and `u_elsewhere` holds both, scoped to
    one department, which reaches no source at all because a source sits at
    `brain.console.govern.NOWHERE`. The last one is a real reader with a real grant, so if the
    other three were refused instead, the pair of answers would tell anybody who could reach the
    port that somebody else holds a capability.

    The bodies are compared with `u_none`'s rather than described as empty, because "empty" is
    satisfied by two answers that differ in a field.
    """
    assert body(client, PAGE_PATH, pid) == body(client, PAGE_PATH, "u_none")


def test_a_reader_who_holds_the_screen_is_answered_something(client: TestClient) -> None:
    """Delete this and a route that answered nobody would pass every test above.

    The sibling every refusal on this screen needs, and it matters more here than elsewhere:
    the refusal on this screen *is* an empty page, so a route that had stopped answering would
    be indistinguishable from a correct one in front of a reader with no grant.
    """
    page = body(client, PAGE_PATH, "u_wide")

    assert page["options"] != []
    assert page["selection"] is not None
    assert body(client, PAGE_PATH, "u_none")["options"] == []


def test_the_capability_this_file_grants_is_the_one_the_registry_requires() -> None:
    """Delete this and every grant above is a string this file agreed with itself about.

    The one place the spelled-out capability is compared with the registry. Everywhere else it
    is written out, so that repointing the screen's capability fails here rather than moving
    both sides of every other assertion at once.
    """
    assert screen(THE_SCREEN).read.requires.value == STAFF_SOURCE_CAPABILITY


def test_the_addresses_are_the_screen_key_so_the_registry_and_the_browser_agree() -> None:
    """Delete this and the console's address can drift off the list of reads with no screen.

    `brain.ops.console_screens.routed_screen_keys` matches the first segment of a console path
    against the registry's keys, so an address that is not the key leaves this screen reported
    as one nobody can open while a person opens it every day.
    """
    assert SCREEN_PATH.endswith(f"/{THE_SCREEN}")
    assert (SCREEN_PATH, f"{SCREEN_PATH}/trial") == ADDRESSES


# ------------------------------------------------------------------ what it may never carry


def test_no_response_carries_what_a_setting_is_set_to(client: TestClient) -> None:
    """Delete this and the value of a setting can be rendered beside its name.

    `brain.console.staff_source_view.A_PAGE_THAT_RENDERS_A_SETTING_IS_A_PAGE_THAT_RENDERS_A_
    CREDENTIAL` is the argument: `INSTALL_STAFF_SOURCE_LOCATION` carries a directory address, a
    sheet identifier or a tenant, and the source needing an address and a credential is the
    obvious next one to add. This is that rule measured over the bytes that leave the process
    rather than over the rows, so an edit that interpolated the value into a sentence is caught
    by the same check as one that added a field.

    The log is searched as well as the body, because a value written to a log is a value
    printed: `brain.deployment.installer.value_leaks_in` learned that on the one step of the
    installer that reads a credential out of a file.
    """
    with capture_logs() as events:
        page = get(client, PAGE_PATH, "u_admin")
        trial = get(client, TRIAL_PATH, "u_admin")

    assert value_of(STAFF_SOURCE_LOCATION_SETTING) == SENTINEL_LOCATION
    assert SENTINEL_LOCATION not in page.text
    assert SENTINEL_LOCATION not in trial.text
    assert SENTINEL_LOCATION not in str(events)


def test_no_shape_on_this_screen_can_carry_a_count_of_what_was_withheld() -> None:
    """Delete this and a field saying how many sources a reader was not shown can be added.

    `brain.ops.jobs.hidden_count_fields` is the check `staff_source_view` already runs over its
    own rows, asked here of the models that carry them onto the wire. A projection is exactly
    where such a field arrives, because it looks like a convenience for whatever draws the page
    rather than like a disclosure.
    """
    assert (
        hidden_count_fields(
            (
                SourceOptionView,
                SelectionView,
                StaffSourcesView,
                RosterPersonView,
                RoleAssertionView,
                TrialPlanView,
                TrialRunView,
                TrialView,
            )
        )
        == ()
    )


def test_the_screen_says_where_a_source_is_chosen_because_no_route_writes_one(
    client: TestClient,
) -> None:
    """Delete this and the screen looks unfinished rather than honest.

    The choice and the location are installation settings and nothing in this application writes
    one, so a picker here would collect an answer and have nowhere to send it. The sentence
    names both settings, which is what makes it actionable rather than an apology.
    """
    page = body(client, PAGE_PATH, "u_admin")

    assert page["not_written_here"] == CHOOSING_A_SOURCE_IS_NOT_A_WRITE_THIS_APPLICATION_HAS
    assert STAFF_SOURCE_SETTING in page["not_written_here"]
    assert STAFF_SOURCE_LOCATION_SETTING in page["not_written_here"]


@pytest.mark.parametrize("path", [PAGE_PATH, TRIAL_PATH])
def test_neither_address_answers_a_verb_that_could_write(client: TestClient, path: str) -> None:
    """Delete this and a write can be added to a screen whose whole subject is a read.

    A trial reads a source and changes nothing, and applying what one proposes is a different
    authority that belongs to whatever runs the scheduled sync. The property is that there is no
    verb here at all rather than a verb that refuses, so this asserts the method is not allowed
    rather than that a POST is refused for want of a capability.
    """
    token = token_for("u_admin", claims={"amr": ["otp"]})
    answer = client.post(path, headers={"authorization": f"Bearer {token}"}, json={})

    assert answer.status_code == 405


# --------------------------------------------------------------- what the selection says


def test_the_chosen_source_is_the_one_the_setting_names(client: TestClient) -> None:
    """Delete this and the screen can show a source nobody chose.

    The setting is moved to a source that needs an address and the screen has to follow it: the
    selection names it, and exactly one option carries the chosen mark, because two would mean
    the screen was comparing something other than the name.
    """
    before = hold_saved(
        {STAFF_SOURCE_SETTING: GOOGLE_SHEET, STAFF_SOURCE_LOCATION_SETTING: SENTINEL_LOCATION}
    )
    try:
        page = body(client, PAGE_PATH, "u_admin")
    finally:
        hold_saved(before)

    assert page["selection"]["name"] == GOOGLE_SHEET
    assert [one["name"] for one in page["options"] if one["chosen"]] == [GOOGLE_SHEET]


def test_a_source_pointed_nowhere_is_refused_in_the_words_of_the_module_that_refused_it(
    client: TestClient,
) -> None:
    """Delete this and the console starts composing its own account of a configuration.

    The refusal is compared with the exception `selected_source` raises over the same settings,
    rather than with a sentence typed here: a copy of the words would agree with itself for ever
    and would be exactly the second opinion
    `A_SECOND_OPINION_ABOUT_A_CONFIGURATION_IS_THE_ONE_AN_ADMINISTRATOR_READS` names.
    """
    before = hold_saved({STAFF_SOURCE_SETTING: GOOGLE_SHEET})
    try:
        with pytest.raises(Exception) as why:
            selected_source()
        page = body(client, PAGE_PATH, "u_admin")
    finally:
        hold_saved(before)

    assert page["selection"]["ready"] is False
    assert page["selection"]["refusal"] == str(why.value)
    assert page["selection"]["unsupplied"] == [STAFF_SOURCE_LOCATION_SETTING]


def test_a_source_this_install_can_read_is_shown_as_ready(client: TestClient) -> None:
    """Delete this and a screen that reported every source as refused would pass the test above.

    The sibling of the refusal, and the case an install that is wired correctly is in. `ready`
    is derived on the row from the refusal being empty, so this also pins that the two cannot
    disagree on the wire.
    """
    page = body(client, PAGE_PATH, "u_admin")

    assert page["selection"]["ready"] is True
    assert page["selection"]["refusal"] == ""
    assert page["selection"]["unsupplied"] == []


# ----------------------------------------------------------------------------- the trial


def test_a_trial_nothing_can_gather_answers_a_sentence_and_not_an_empty_plan(
    client: TestClient,
) -> None:
    """Delete this and an install that never looked reports that nobody would be added.

    `brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` asked about a roster, and the
    direction matters: a plan computed from no roster is a statement about this install rendered
    as a statement about a client's directory, and it would be believed.
    """
    answer = body(client, TRIAL_PATH, "u_admin")

    assert answer["trial"] is None
    assert answer["unread"] == NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE


def test_a_reader_who_may_not_run_a_trial_is_answered_what_an_unwired_install_answers(
    client: TestClient,
) -> None:
    """Delete this and the trial's refusal becomes distinguishable from its absence.

    `u_wide` holds the screen's capability and the configuration plane, which is the whole of
    the page and none of the trial, because naming who would be added is a content disclosure.
    The install is wired here, so the difference between this reader and `u_admin` is a grant and
    nothing else, and the two answers must not differ in a way that says so.

    The gatherer's own count is the second half: a refused reader must not cause the source to be
    contacted at all, which is why the check is asked before anything is assembled.
    """
    gathers = _gatherer()
    client.app.state.staff_trial_source = gathers  # type: ignore[attr-defined]

    refused = body(client, TRIAL_PATH, "u_wide")

    assert refused["trial"] is None
    assert refused["unread"] == NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE
    assert (gathers.called, gathers.sheet.asked) == (0, 0)
    assert body(client, TRIAL_PATH, "u_admin")["trial"] is not None


def test_a_gatherer_that_is_not_callable_is_the_same_as_no_gatherer(client: TestClient) -> None:
    """Delete this and a string on `app.state` is invoked and reaches a caller as a 500.

    The `callable` check in `trial_source_of` is the whole of the structural match, which the
    module says out loud rather than pretending an `isinstance` against a single-method protocol
    would have been stronger. This is the test that makes that comment true.
    """
    client.app.state.staff_trial_source = "not a gatherer"  # type: ignore[attr-defined]

    assert body(client, TRIAL_PATH, "u_admin")["unread"] == NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE


def test_a_trial_is_the_plan_the_sync_would_compute_over_the_same_inputs(
    client: TestClient,
) -> None:
    """Delete this and a projection can drop half of what a run would do and still read well.

    The plan is compared with `dry_run`'s own answer over the same roster and the same holdings,
    rather than with fields typed here: a trial assembled any other way is a rehearsal of a
    different performance, which is `brain.identity.staff_sync`'s opening sentence, and a test
    that built the expected lists by hand would be agreeing with whatever the projection did.

    Grace is held already and Ada is not, so the plan has both halves: somebody who would be
    added and somebody the system holds whom the sheet did not mention. Nothing is removed,
    because a spreadsheet never promises completeness and this source has never been applied,
    and both of those reasons are carried in `withheld` rather than inferred.
    """
    gathers = _gatherer()
    client.app.state.staff_trial_source = gathers  # type: ignore[attr-defined]

    answer = body(client, TRIAL_PATH, "u_admin")
    expected = dry_run(
        Roster(source=SPREADSHEET, people=(ADA, GRACE), complete=False),
        known=gathers.known,
        last_applied=None,
    )

    assert answer["trial"]["source"] == SPREADSHEET
    assert answer["trial"]["plan"]["would_add"] == [
        {
            "work_address": one.work_address,
            "display_name": one.display_name,
            "department": one.department,
            "groups": list(one.groups),
            "active": one.active,
        }
        for one in expected.would_add
    ]
    assert answer["trial"]["plan"]["absent"] == list(expected.absent)
    assert answer["trial"]["plan"]["would_remove"] == list(expected.would_remove)
    assert answer["trial"]["plan"]["withheld"] == list(expected.withheld)
    assert answer["trial"]["plan"]["gaps"] == list(expected.gaps)
    assert answer["trial"]["safe_to_apply"] is expected.safe_to_apply


def test_a_trial_reads_the_source_once_and_writes_nothing(client: TestClient) -> None:
    """Delete this and a screen somebody presses repeatedly can start asking twice per press.

    A trial is a read and the count is the only evidence of how many. It also pins that the
    route reaches the source through `roster_from` rather than through a second path of its own:
    two readings would be two rosters, and a diff computed against the second of them is a diff
    nobody looked at.
    """
    gathers = _gatherer()
    client.app.state.staff_trial_source = gathers  # type: ignore[attr-defined]

    body(client, TRIAL_PATH, "u_admin")

    assert (gathers.called, gathers.sheet.asked) == (1, 1)
    assert client.app.state.db_sessions is None  # type: ignore[attr-defined]


def test_a_roster_from_somewhere_else_is_carried_as_a_refusal_and_not_as_a_plan(
    client: TestClient,
) -> None:
    """Delete this and a source answering for a different install reads as a working trial.

    `roster_from` refuses a roster whose source is not the one this install chose, because
    reconciliation compares a source's rows against that same source's previous rows and the two
    would delete each other's assertions on every run. A trial is read at exactly the moment
    somebody is finding out whether a source is wired correctly, so the refusal is reported
    rather than raised, and the shape that carries it is a run with no plan.
    """
    gathers = _gatherer()
    gathers.sheet.source = GOOGLE_SHEET
    client.app.state.staff_trial_source = gathers  # type: ignore[attr-defined]

    answer = body(client, TRIAL_PATH, "u_admin")

    assert answer["trial"]["plan"] is None
    assert answer["trial"]["refusals"] != []
    assert answer["trial"]["safe_to_apply"] is False


def test_a_trial_carries_a_plan_or_a_refusal_and_never_neither() -> None:
    """Delete this and a response can arrive with no run and nothing saying why.

    The model's own refusal, asked directly rather than through a route, because the route has
    no way to produce either shape: both halves absent is a reader looking for a setting that
    would not have helped, and both present is a plan beside a refusal, which is a plan somebody
    applies.
    """
    with pytest.raises(ValueError, match="never both and never neither"):
        TrialView()
    with pytest.raises(ValueError, match="never both and never neither"):
        TrialView(
            trial=TrialRunView(source=SPREADSHEET, plan=None, refusals=["no"], safe_to_apply=False),
            unread=NOTHING_HERE_READS_A_LIVE_STAFF_SOURCE,
        )
