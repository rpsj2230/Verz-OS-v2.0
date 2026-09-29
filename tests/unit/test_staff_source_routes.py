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

**The trial is a request to the worker, and what is tested here is the asking.** Since
2026-09-29 Try a read writes when it was asked and the worker reads the source
(`brain.ops.staff_trial`); the read itself is `tests/unit/test_staff_sync_run.py`'s. The session
factory and the two statements are replaced here, because this file runs with no database, so what
is held is who may ask, what is refused in words, and that the asking is attributed before it is
written.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain import staff_source_routes
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
    selectable_names,
    selected_source,
)
from brain.install import hold_saved, value_of
from brain.ops.jobs import hidden_count_fields
from brain.ops.staff_trial import TRIAL_WAITING
from brain.staff_source_routes import (
    ADDRESSES,
    NOT_READ_BY_THE_WORKER,
    NOTHING_TO_TRY,
    SCREEN_PATH,
    WHERE_A_SOURCE_IS_CHOSEN,
    RoleAssertionView,
    RosterPersonView,
    SelectionView,
    SourceOptionView,
    StaffSourcesView,
    StaffTrialView,
    TrialPlanView,
    TrialRunView,
    TrialView,
    sources_offered,
)
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
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

#: The one source that needs no setting at all, so the screen answers without pointing anything
#: anywhere. `brain.identity.staff_source.SELECTABLE` declares it with `needs=()`. The worker has
#: nothing to read for it, which is one of the trial's refusals.
SPREADSHEET = "spreadsheet"

#: A source the worker reads, for the trial that is accepted.
LARK = "lark"

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
def client(held: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real application, with no session factory, which is every deployment today.

    `create_app` produced the router registration under test: a test that mounted the router
    itself would prove the routes work and not that they are served.

    **No database is named in the settings, and the premise is asserted rather than assigned.**
    Until 2026-09-17 this built `Settings` from the host's environment and set `db_sessions` to
    None once the application had started. In CI, where `DATABASE_URL` is set, the lifespan had
    already run `brain.ops.install_settings.refresh` by then, which holds the saved rows (none) in
    place of everything `held` had held, so four tests read the source as unset and the location
    as the default. `DATABASE_URL` is set here to an address nothing listens on, so dropping the
    pin fails the assertion below on a laptop too, before any test reads a setting.
    """
    as_if_ci_had_a_database(monkeypatch)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        assert app.state.db_sessions is None
        app.state.gate = _wiring()
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
                StaffTrialView,
            )
        )
        == ()
    )


def test_the_screen_says_a_source_is_chosen_on_it_and_that_the_server_needs_no_edit(
    client: TestClient,
) -> None:
    """Delete this and the page can go back to telling somebody to edit a file on the server.

    Since 2026-09-21 a source is connected on this screen and saved in `ops.setting`, so the
    sentence the page carries says where on the screen, and that nothing on the server changes.
    """
    page = body(client, PAGE_PATH, "u_admin")

    assert page["how_to_choose"] == WHERE_A_SOURCE_IS_CHOSEN
    assert "Connect a staff source" in page["how_to_choose"]
    assert "not_written_here" not in page


def test_the_page_answers_no_verb_that_could_write(client: TestClient) -> None:
    """Delete this and a write can be added to the page whose whole subject is a read.

    Applying a plan is a different authority: the first sync, at its own address, under the two
    authorities a connection needs. The trial's address takes a POST since 2026-09-29, and what it
    writes is when it was asked and nothing else, which the trial's tests below hold. The property
    here is that the page's own address has no verb at all rather than one that refuses.
    """
    token = token_for("u_admin", claims={"amr": ["otp"]})
    answer = client.post(PAGE_PATH, headers={"authorization": f"Bearer {token}"}, json={})

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
def post(c: TestClient, path: str, pid: str) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.post(path, headers={"authorization": f"Bearer {token}"}, json={})
    return response


class Session:
    """The one transaction a trial request is written in, recording what was done in it."""

    def __init__(self, done: list[str]) -> None:
        self.done = done

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> Session:
        return self


class Asking:
    """Stands in for the database a trial request is written to and read back from."""

    def __init__(self, requested: datetime | None = None, started: datetime | None = None):
        self.done: list[str] = []
        self.asked_at: list[datetime] = []
        self.requested = requested
        self.started = started

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def attribute(session: Session, asked: object) -> None:
            session.done.append("attributed")

        async def request_trial(session: Session, *, at: datetime, by: str) -> None:
            session.done.append(f"asked by {by}")
            self.asked_at.append(at)

        async def trial_requested(session: Session) -> datetime | None:
            return self.requested

        async def read_last_started(session: Session) -> datetime | None:
            return self.started

        monkeypatch.setattr(
            staff_source_routes, "sessions_of", lambda _: lambda: Session(self.done)
        )
        monkeypatch.setattr(staff_source_routes, "attribute", attribute)
        monkeypatch.setattr(staff_source_routes, "request_trial", request_trial)
        monkeypatch.setattr(staff_source_routes, "trial_requested", trial_requested)
        monkeypatch.setattr(staff_source_routes, "read_last_started", read_last_started)


@pytest.fixture
def reads_lark() -> Iterator[None]:
    """This install set to a source the worker reads, pointed at its platform."""
    before = hold_saved(
        {STAFF_SOURCE_SETTING: LARK, STAFF_SOURCE_LOCATION_SETTING: "larksuite.com"}
    )
    yield
    hold_saved(before)


def test_a_trial_asked_for_is_written_attributed_and_the_screen_is_told_it_waits(
    client: TestClient, reads_lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Try a read writes when it was asked, after attributing the transaction so the ledger names
    who pressed it, and answers that the worker reads it next. Delete this and the button can go
    back to saying nothing here reads a staff list while the worker reads one every night."""
    asking = Asking()
    asking.install(monkeypatch)

    answer = post(client, TRIAL_PATH, "u_admin")

    assert answer.status_code == 200, answer.text
    assert answer.json()["waiting"] is True
    assert answer.json()["told"] == TRIAL_WAITING
    assert asking.done == ["attributed", "asked by u_admin"]
    assert len(asking.asked_at) == 1


def test_a_reader_who_may_not_run_a_trial_cannot_ask_for_one(
    client: TestClient, reads_lark: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`u_wide` holds the page and not the trial, because what a trial reads names the company's
    staff. Delete this and anybody who can open the page can make the worker read the directory.
    The sibling above is the reader who may."""
    asking = Asking()
    asking.install(monkeypatch)

    answer = post(client, TRIAL_PATH, "u_wide")

    assert answer.status_code == 404
    assert asking.done == []


@pytest.mark.parametrize(
    ("chosen", "told"), [("none", NOTHING_TO_TRY), (SPREADSHEET, NOT_READ_BY_THE_WORKER)]
)
def test_a_source_the_worker_cannot_read_is_refused_in_words_and_nothing_is_asked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, chosen: str, told: str
) -> None:
    """No list chosen, and a hand-kept spreadsheet, which is read when uploaded, give the worker
    nothing to read. Delete this and a press waits a quarter of an hour for a read that cannot
    happen."""
    asking = Asking()
    asking.install(monkeypatch)
    before = hold_saved({STAFF_SOURCE_SETTING: chosen})
    try:
        answer = post(client, TRIAL_PATH, "u_admin")
    finally:
        hold_saved(before)

    assert answer.status_code == 422
    assert answer.json()["message"] == told
    assert asking.done == []


def test_a_source_pointed_nowhere_is_refused_with_the_selection_s_own_words(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chosen source missing its location is refused with `selected_source`'s sentence, the
    one the page already shows. Delete this and a trial is asked of a source the worker will
    refuse, and the person finds out from a failed row a minute later."""
    asking = Asking()
    asking.install(monkeypatch)
    before = hold_saved({STAFF_SOURCE_SETTING: GOOGLE_SHEET})
    try:
        with pytest.raises(Exception) as why:
            selected_source()
        answer = post(client, TRIAL_PATH, "u_admin")
    finally:
        hold_saved(before)

    assert answer.status_code == 422
    assert answer.json()["message"] == str(why.value)
    assert asking.done == []


def test_the_screen_is_told_a_trial_waits_until_a_run_starts_after_the_press(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GET` says a press is waiting while no run has started since it, and not once one has.
    Delete this and the page cannot say the worker has not read yet, or says so for ever."""
    pressed = datetime.now(tz=UTC) - timedelta(seconds=5)
    Asking(requested=pressed).install(monkeypatch)
    waiting = body(client, TRIAL_PATH, "u_admin")
    Asking(requested=pressed, started=pressed + timedelta(seconds=1)).install(monkeypatch)
    answered = body(client, TRIAL_PATH, "u_admin")

    assert waiting["waiting"] is True
    assert waiting["told"] == TRIAL_WAITING
    assert answered == {"requested_at": None, "waiting": False, "told": ""}


def test_a_reader_who_may_not_run_a_trial_is_told_nothing_waits_as_on_an_install_never_asked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live request is answered to `u_admin` and not to `u_wide`, who is answered exactly what
    an install with no request is. Delete this and whether a trial is waiting tells a reader
    something about a read they may not see."""
    Asking(requested=datetime.now(tz=UTC)).install(monkeypatch)

    assert body(client, TRIAL_PATH, "u_wide") == body(client, TRIAL_PATH, "u_none")
    assert body(client, TRIAL_PATH, "u_wide") == {
        "requested_at": None,
        "waiting": False,
        "told": "",
    }
    assert body(client, TRIAL_PATH, "u_admin")["waiting"] is True


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
            unread="There is no trial.",
        )


def test_the_screen_says_how_people_first_sign_in_and_what_stops_them_with_nothing_sent(
    client: TestClient,
) -> None:
    """The owner's flow, on the page an administrator connects the list from: nobody is sent
    anything, a person presses Forgot password, and without the sign-in service's email settings
    nobody can, with what to fill in. Delete this and the screen can promise invitations the sync
    never sends, or leave an install with no email settings wondering why nobody can sign in."""
    page = body(client, PAGE_PATH, "u_admin")

    assert "sends nobody anything" in page["accounts"]
    assert "Forgot password" in page["accounts"]
    assert page["email_settings"].startswith(
        "If the sign-in service has no email settings, nobody can set a password yet"
    )
    for field in ("Realm settings", "Email", "From address", "Host", "Port", "Test connection"):
        assert field in page["email_settings"]
    assert page["account_ready"] == (
        "Your account is ready. Go to the sign-in page, press Forgot password and enter your "
        "work email."
    )
