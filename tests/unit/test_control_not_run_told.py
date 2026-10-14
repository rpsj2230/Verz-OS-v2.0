"""The holders of the operations alert are told once, in chat, when a safety mechanism has not run,
and by email only when none of them has used a chat tool for a week.

The pure half holds the sentence, the key, the window and who may be told. The sending half drives
`brain.control_not_run_told.tell_overdue_controls` with the sender, the address book, the reaches
and the relay replaced by fakes that keep what they were asked, so a second pass is seen to send
nothing and the email is seen to leave only when it should. Dates are far outside any wall clock,
because none of this is about the present.

Task ids: M17.7.2, M17.7.6
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from brain import control_not_run_told as told_module
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.control_not_run_told import (
    ALERT_EMAIL_SETTING,
    CHAT_USE_WINDOW,
    INCIDENTS_SCREEN,
    INTENT_PREFIX,
    NOT_TOLD,
    TELL_EVERY,
    Late,
    Told,
    alert_email,
    audiences_for,
    control_text,
    how_long,
    intent_ref_for,
    late_controls,
    may_be_told,
    no_chat_lately,
    tell_overdue_controls,
)
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.ops.alerting import (
    OPERATIONS_ALERT,
    OPERATIONS_INCIDENT,
    Severity,
    disclosure_findings,
)
from brain.ops.controls import CONTROLS, Control, Invocation, Missed, overdue
from brain.ops.idempotency import CallOutcome
from brain.ops.mail import MailAnswer, Message
from brain.ops.notices import NoticeKind, notice
from brain.tables.channel import DeliveryOutcome
from tests.fixtures.operation_ledger import MemoryLedger

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "brain"
# Far outside any wall clock: nothing here is about the present.
NOW: Final = datetime(2999, 6, 10, 12, 0, tzinfo=UTC)
LONG_AGO: Final = datetime(2999, 1, 1, tzinfo=UTC)
WHOLE: Final = Scope.unrestricted()
IN_ONE_DEPARTMENT: Final = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
OPEN_INCIDENTS: Final = (
    Grant(capability=screen(INCIDENTS_SCREEN).read.requires, scope=WHOLE),
    Grant(capability=plane_capability(Plane.CONFIGURATION), scope=WHOLE),
)


def control(
    name: str, *, severity: Severity = Severity.RAISED, invoked_by: Invocation | None = None
) -> Control:
    """A control of the check's own, run every hour, so it is late after two."""
    return Control(
        name=name,
        symbols=("brain.x:run",),
        guards="the thing this guards, in words a client can read",
        lost_silently="something quietly stops being true",
        every=timedelta(hours=1),
        severity=severity,
        invoked_by=Invocation.IN_PROCESS if invoked_by is None else invoked_by,
    )


QUIET: Final = control("quiet_sweep")
LOUD: Final = control("loud_sweep", severity=Severity.WOKEN)


def reach(who: str, *held: Any, not_after: datetime | None = None) -> EntitlementSet:
    """Somebody holding exactly these capabilities across the install, and no screen."""
    return EntitlementSet(
        principal_id=who,
        grants=tuple(Grant(capability=one, scope=WHOLE) for one in held),
        not_after=not_after,
    )


def holder(who: str, *, alert: bool = True, incident: bool = False) -> EntitlementSet:
    """Somebody who opens Incidents across the install, with the alert and/or the incident one."""
    capabilities = ([OPERATIONS_ALERT] if alert else []) + (
        [OPERATIONS_INCIDENT] if incident else []
    )
    return EntitlementSet(
        principal_id=who,
        grants=(*OPEN_INCIDENTS, *(Grant(capability=c, scope=WHOLE) for c in capabilities)),
    )


# ------------------------------------------------------------------------ the pure half
def test_a_control_that_ran_and_went_quiet_is_told_and_one_inside_its_window_is_not() -> None:
    """The positive and the refusal over one clock: two hours is late for an hourly control and
    ninety minutes is not. Delete this and the alert fires on every jitter, or never fires."""
    late = late_controls(
        {QUIET.name: NOW - timedelta(hours=3)}, now=NOW, since=LONG_AGO, controls=[QUIET]
    )
    inside = late_controls(
        {QUIET.name: NOW - timedelta(minutes=90)}, now=NOW, since=LONG_AGO, controls=[QUIET]
    )

    assert [one.name for one in late] == [QUIET.name]
    assert late[0].last_success == NOW - timedelta(hours=3)
    assert inside == ()


def test_a_control_that_never_ran_is_told_only_once_this_process_has_watched_for_its_window() -> (
    None
):
    """A freshly started install has run nothing and the worker's first tick is minutes away. Delete
    this and the first pass after every deploy tells everybody that everything is late."""
    just_started = late_controls({}, now=NOW, since=NOW - timedelta(minutes=5), controls=[QUIET])
    boundary = late_controls({}, now=NOW, since=NOW - QUIET.alert_after, controls=[QUIET])
    watched = late_controls(
        {}, now=NOW, since=NOW - QUIET.alert_after - timedelta(seconds=1), controls=[QUIET]
    )

    assert just_started == () and boundary == ()
    assert [(one.name, one.last_success) for one in watched] == [(QUIET.name, None)]


def test_a_control_that_ran_and_went_quiet_is_told_however_recently_this_process_started() -> None:
    """The watching window is for a control that has never run, because only then is there nothing
    to measure from. Delete this and a deploy silences every genuinely late control for the length
    of its window, which is the moment somebody most wants to hear about one."""
    found = late_controls(
        {QUIET.name: NOW - timedelta(days=2)},
        now=NOW,
        since=NOW - timedelta(seconds=30),
        controls=[QUIET],
    )

    assert [one.name for one in found] == [QUIET.name]


def test_a_control_nothing_calls_is_never_told_and_the_missed_reasons_not_told_are_named() -> None:
    """`WHAT_IS_NOT_A_MISSED_RUN`: a statement about the software, true on every install every pass.
    Delete this and every install is sent one message per unreachable control on its first pass."""
    nothing = control("unwired_sweep", invoked_by=Invocation.NOTHING)

    assert late_controls({}, now=NOW, since=LONG_AGO, controls=[nothing]) == ()
    assert overdue(last_run={}, now=NOW, controls=[nothing])[0].missed is Missed.UNREACHABLE
    assert frozenset(Missed) - {Missed.NEVER_RUN, Missed.BEHIND} == NOT_TOLD


def test_a_control_a_route_starts_is_not_this_loops_to_ask_about() -> None:
    """`schedulable` leaves out what something outside the process starts, and so does this. Delete
    this and the audit anchor, which the worker never records, is reported never run."""
    routed = Control(
        name="routed_sweep",
        symbols=("brain.x:run",),
        guards="g",
        lost_silently="l",
        every=timedelta(hours=1),
        severity=Severity.RAISED,
        invoked_by=Invocation.ON_A_ROUTE,
        route="/x",
        schedule_file=".github/workflows/x.yml",
    )

    assert late_controls({}, now=NOW, since=LONG_AGO, controls=[routed]) == ()


def test_the_loudest_control_is_told_first() -> None:
    """Delete this and a person reading down their chat meets the knowledge badge before the side
    effect that may have happened twice."""
    found = late_controls(
        {QUIET.name: LONG_AGO, LOUD.name: LONG_AGO}, now=NOW, since=LONG_AGO, controls=[QUIET, LOUD]
    )

    assert [one.name for one in found] == [LOUD.name, QUIET.name]


def test_the_sentence_names_the_mechanism_and_how_long_and_never_what_it_guards() -> None:
    """**The disclosure rule.** Delete this and the chat message carries `Overdue.text`, which says
    what the control guards and what is lost until it runs, to a screen a person has not opened."""
    late = Late(
        overdue(last_run={QUIET.name: NOW - timedelta(days=3)}, now=NOW, controls=[QUIET])[0],
        NOW - timedelta(days=3),
    )
    said = control_text(late, now=NOW)

    assert QUIET.name in said and "3 days" in said and "every 1 hour" in said
    assert QUIET.guards not in said and QUIET.lost_silently not in said
    assert late.overdue.text not in said


def test_a_control_that_never_ran_says_so_and_not_a_duration() -> None:
    """Delete this and a never-run control says it has not run for the age of the epoch."""
    late = Late(overdue(last_run={QUIET.name: None}, now=NOW, controls=[QUIET])[0], None)

    assert "has not run since this system was started" in control_text(late, now=NOW)


def test_the_link_is_the_incidents_page_when_the_install_has_an_address_and_absent_when_not() -> (
    None
):
    """Delete this and the alert says what stopped and leaves the person to find where, or carries
    half a link on an install with no address of its own."""
    late = Late(overdue(last_run={QUIET.name: LONG_AGO}, now=NOW, controls=[QUIET])[0], LONG_AGO)

    linked = control_text(late, now=NOW, link="https://brain.example.test/incidents")
    plain = control_text(late, now=NOW)

    assert linked.endswith("Open Incidents: https://brain.example.test/incidents")
    assert linked.startswith(plain)
    assert "Open Incidents" not in plain and "https" not in plain


def test_no_control_in_the_registry_is_alerted_in_words_that_disclose_the_estate() -> None:
    """`disclosure_findings` over the text for every control the registry holds, as late and as
    never run, with a link. Delete this and a control added with a name that is a capability, or a
    word about somebody's data, is the sentence that lands on a phone."""
    for one in CONTROLS:
        for last in (None, NOW - timedelta(days=40)):
            late = Late(overdue(last_run={one.name: last}, now=NOW, controls=[one])[0], last)
            said = control_text(late, now=NOW, link="https://brain.example.test/incidents")
            assert disclosure_findings(said) == (), (one.name, said)


def test_how_long_is_whole_days_then_hours_then_minutes() -> None:
    """Delete this and a person is told a figure to the second, or "0 days" for a ninety-minute
    silence."""
    assert how_long(timedelta(days=3, hours=5)) == "3 days"
    assert how_long(timedelta(days=1)) == "1 day"
    assert how_long(timedelta(hours=5, minutes=59)) == "5 hours"
    assert how_long(timedelta(hours=1)) == "1 hour"
    assert how_long(timedelta(minutes=45)) == "45 minutes"
    assert how_long(timedelta(seconds=20)) == "less than a minute"
    assert how_long(timedelta(hours=-2)) == "less than a minute"


def test_an_episode_is_keyed_by_the_control_and_the_success_that_began_its_silence() -> None:
    """A control that runs again and stops again is a second message; the same silence is the same
    one. Delete this and a control that recovered and failed again is never told twice, or every
    pass tells the same silence."""

    def late_since(last: datetime | None) -> Late:
        return Late(overdue(last_run={QUIET.name: last}, now=NOW, controls=[QUIET])[0], last)

    first = late_since(LONG_AGO)
    assert intent_ref_for(first) == intent_ref_for(late_since(LONG_AGO))
    assert intent_ref_for(first) != intent_ref_for(late_since(LONG_AGO + timedelta(days=1)))
    assert intent_ref_for(late_since(None)) == f"{INTENT_PREFIX}.{QUIET.name}.never"
    assert intent_ref_for(first).startswith(f"{INTENT_PREFIX}.{QUIET.name}.2999-01-01")


def test_the_incident_capability_is_told_for_a_route_that_wakes_somebody_and_not_otherwise() -> (
    None
):
    """Asked of `alerting.route_for` and not written here. Delete this and a mechanism that wakes
    somebody is told to the alert's holders only, or every nudge goes to the incident's."""
    assert audiences_for(Severity.NOTICED) == (OPERATIONS_ALERT,)
    assert audiences_for(Severity.RAISED) == (OPERATIONS_ALERT,)
    assert audiences_for(Severity.WOKEN) == (OPERATIONS_ALERT, OPERATIONS_INCIDENT)


def test_a_person_is_told_only_if_they_hold_an_audience_and_open_incidents_install_wide() -> None:
    """Both halves, with the positive sibling first. Delete this and an alert points a person at a
    screen they would be refused, or reaches somebody who holds nothing."""
    assert may_be_told(holder("u_ops"), Severity.RAISED, NOW)
    # Holds the alert and cannot open Incidents.
    assert not may_be_told(reach("u_blind", OPERATIONS_ALERT), Severity.RAISED, NOW)
    # Opens Incidents and holds neither.
    assert not may_be_told(holder("u_screen", alert=False), Severity.RAISED, NOW)
    # Opens Incidents in one department only, which is not across the install.
    narrow = EntitlementSet(
        principal_id="u_narrow",
        grants=(
            Grant(capability=screen(INCIDENTS_SCREEN).read.requires, scope=IN_ONE_DEPARTMENT),
            Grant(capability=plane_capability(Plane.CONFIGURATION), scope=WHOLE),
            Grant(capability=OPERATIONS_ALERT, scope=WHOLE),
        ),
    )
    assert not may_be_told(narrow, Severity.RAISED, NOW)


def test_the_incident_holder_is_told_at_the_loud_severity_only() -> None:
    """Delete this and the incident capability is read as an alert holder's at every severity, or
    not honoured at the one it exists for."""
    only_incident = holder("u_inc", alert=False, incident=True)

    assert may_be_told(only_incident, Severity.WOKEN, NOW)
    assert not may_be_told(only_incident, Severity.RAISED, NOW)
    assert not may_be_told(only_incident, Severity.NOTICED, NOW)


def test_a_reach_that_has_lapsed_is_nobodys_to_tell() -> None:
    """Asked at the instant of the pass. Delete this and a person who has left is still counted as
    the holder who has been told, so nobody else is."""
    lapsed = holder("u_gone").model_copy(update={"not_after": NOW - timedelta(seconds=1)})

    assert not may_be_told(lapsed, Severity.RAISED, NOW)
    assert may_be_told(
        holder("u_gone").model_copy(update={"not_after": NOW + timedelta(days=1)}),
        Severity.RAISED,
        NOW,
    )


def test_nobody_has_used_chat_lately_only_when_no_holder_wrote_inside_the_window() -> None:
    """The window is closed at its end and a person with no record at all has not used chat. Delete
    this and the email goes when somebody did write, or never goes when nobody did."""
    day = timedelta(days=1)
    assert no_chat_lately([], {}, now=NOW)
    assert no_chat_lately(["u_a"], {}, now=NOW)
    assert no_chat_lately(["u_a"], {"u_a": NOW - CHAT_USE_WINDOW - day}, now=NOW)
    assert not no_chat_lately(["u_a"], {"u_a": NOW - CHAT_USE_WINDOW}, now=NOW)
    assert not no_chat_lately(["u_a", "u_b"], {"u_a": NOW - 9 * day, "u_b": NOW - day}, now=NOW)
    # A record for somebody who is not a holder is nobody's.
    assert no_chat_lately(["u_a"], {"u_other": NOW - day}, now=NOW)


def test_the_window_is_a_week_and_the_loop_asks_often_enough_to_be_prompt() -> None:
    """The week is the owner's figure (decision 221) and the loop is between a minute and an hour,
    which is prompt without being a poll. Delete this and a tidy-up shortens the window to hours,
    or slows the loop to a day."""
    assert timedelta(days=7) == CHAT_USE_WINDOW
    assert timedelta(minutes=1) <= TELL_EVERY <= timedelta(hours=1)


def test_the_incidents_screen_named_here_is_the_one_system_health_asks_about() -> None:
    """Two places spell it. Delete this and one is renamed and this alert asks about a screen the
    health read no longer guards."""
    from brain.system_health_routes import INCIDENTS_SCREEN as HEALTH

    assert INCIDENTS_SCREEN == HEALTH


def test_the_address_is_read_where_installation_values_are_read_and_unset_means_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the fallback reads the environment itself, or treats the word `unset` as an
    address and sends a message to nobody."""
    from brain.install import BY_NAME

    declared = BY_NAME[ALERT_EMAIL_SETTING]
    assert declared.default == "unset" and not declared.required

    asked: list[str] = []

    def reading(name: str) -> str:
        asked.append(name)
        return answer[0]

    answer = ["unset"]
    monkeypatch.setattr(told_module, "value_of", reading)
    assert alert_email() is None
    answer[0] = "  ops@example.test "
    assert alert_email() == "ops@example.test"
    answer[0] = ""
    assert alert_email() is None
    assert set(asked) == {ALERT_EMAIL_SETTING}


# ------------------------------------------------------------------- the sending half
@dataclass
class Sessions:
    async def __aenter__(self) -> Sessions:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def __call__(self) -> Sessions:
        return self


@dataclass
class Sent:
    outcome: DeliveryOutcome
    issued: bool


@dataclass
class Teller:
    """`brain.tell_later.tell` in memory, with the operation ledger's rule: a key already sent is
    handed back its first record and issues nothing. Keeps the kind it was called with."""

    told: list[tuple[str, str, str]] = field(default_factory=list)
    kinds: list[Any] = field(default_factory=list)
    keys: set[tuple[str, str]] = field(default_factory=set)
    unaddressed: set[str] = field(default_factory=set)
    refused: set[str] = field(default_factory=set)

    async def __call__(
        self,
        request: Any,
        person: str,
        said: str,
        *,
        intent_ref: str,
        now: datetime,
        kind: Any = None,
    ) -> Sent | None:
        self.kinds.append(kind)
        if person in self.unaddressed:
            return None
        first = (person, intent_ref) not in self.keys
        self.keys.add((person, intent_ref))
        if first:
            self.told.append((person, said, intent_ref))
        outcome = DeliveryOutcome.REFUSED if person in self.refused else DeliveryOutcome.SENT
        return Sent(outcome, issued=first)


@dataclass
class Book:
    used: dict[str, datetime]

    async def addressed(self, channel: Any) -> tuple[tuple[str, str], ...]:
        return tuple((person, f"addr_{person}") for person in sorted(self.used))

    async def last_used_at(self, people: Any) -> dict[str, datetime]:
        return {one: self.used[one] for one in people if one in self.used}


@dataclass
class Reaches:
    held: dict[str, EntitlementSet]
    loaded: list[str] = field(default_factory=list)

    async def load(self, person: str, now: datetime) -> EntitlementSet:
        self.loaded.append(person)
        return self.held[person]


class Relay:
    def __init__(self, *, answer: CallOutcome = CallOutcome.OK) -> None:
        self.sent: list[Message] = []
        self.answer = answer
        self.on = True

    def __call__(self) -> Any:
        return self if self.on else None

    def send(self, message: Message) -> MailAnswer:
        self.sent.append(message)
        return MailAnswer(self.answer)


@dataclass
class World:
    teller: Teller
    book: Book
    reaches: Reaches
    relay: Relay
    ledger: MemoryLedger


def world(
    monkeypatch: pytest.MonkeyPatch,
    *,
    held: dict[str, EntitlementSet],
    used: dict[str, datetime],
    feature: bool = True,
    notice_on: bool = True,
) -> World:
    teller, relay, ledger = Teller(), Relay(), MemoryLedger()
    book, reaches = Book(used), Reaches(held)

    async def switched(_: Any) -> bool:
        return feature

    async def notice_switched(session: Any, kind: NoticeKind) -> bool:
        assert kind is NoticeKind.CONTROL_NOT_RUN
        return notice_on

    from brain import channel_routes

    monkeypatch.setattr(told_module, "control_alerts_are_on", switched)
    monkeypatch.setattr(told_module, "notice_is_on", notice_switched)
    monkeypatch.setattr(told_module, "tell", teller)
    monkeypatch.setattr(channel_routes, "addresses_of", lambda request: book)
    monkeypatch.setattr(channel_routes, "reach_of", lambda request: reaches)
    monkeypatch.setattr(channel_routes, "relay_of", lambda request: relay)
    monkeypatch.setattr(channel_routes, "ledger_of", lambda request: lambda work: work(ledger))
    return World(teller, book, reaches, relay, ledger)


def run_pass(
    *,
    email: str | None = "ops@example.test",
    last: dict[str, datetime] | None = None,
    controls: tuple[Control, ...] = (QUIET,),
) -> Told:
    return asyncio.run(
        tell_overdue_controls(
            None,  # type: ignore[arg-type]
            Sessions(),  # type: ignore[arg-type]
            now=NOW,
            since=LONG_AGO,
            last_success={QUIET.name: NOW - timedelta(days=2)} if last is None else last,
            people=None,
            email=email,
            controls=controls,
        )
    )


def test_a_holder_who_wrote_yesterday_is_told_once_in_chat_and_no_email_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The positive case, and once.** The holder is handed the sentence under the episode's own
    key, a second pass over the same silence tells nobody and counts nothing, and with a holder who
    used chat lately the install's address is not written to. Delete this and the loop tells
    nobody while it reads on, tells a person every quarter of an hour, or emails as well."""
    w = world(
        monkeypatch,
        held={"u_ops": holder("u_ops")},
        used={"u_ops": NOW - timedelta(days=1)},
    )

    first = run_pass()
    second = run_pass()

    assert (first.chat, first.email, second.chat, second.email) == (1, 0, 0, 0)
    [(person, said, key)] = w.teller.told
    assert person == "u_ops" and QUIET.name in said and key.startswith(f"{INTENT_PREFIX}.")
    assert w.relay.sent == []


def test_the_message_is_never_held_by_quiet_hours_or_a_channel_preference() -> None:
    """It names no `NotificationKind`, so `tell_later.held_by` has nothing to hold it by. Delete
    this and a safety mechanism that has stopped waits for a person's evening off to end."""
    tree = ast.parse((SRC / "control_not_run_told.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tell"
    ]
    assert len(calls) == 1
    assert "kind" not in {keyword.arg for keyword in calls[0].keywords}


def test_a_person_who_cannot_open_incidents_is_not_told_whatever_they_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The holders are filtered by their own reach before anything is sent. Delete this and the
    alert is pushed to somebody it would send to a screen that answers them as absent."""
    w = world(
        monkeypatch,
        held={"u_ops": holder("u_ops"), "u_blind": reach("u_blind", OPERATIONS_ALERT)},
        used={"u_ops": NOW - timedelta(days=1), "u_blind": NOW - timedelta(days=1)},
    )

    told = run_pass()

    assert told.chat == 1
    assert [person for person, _, _ in w.teller.told] == ["u_ops"]


def test_the_incident_holder_is_told_for_a_mechanism_that_wakes_somebody_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both severities in one world, with each person's own reach. Delete this and the incident
    capability reaches nobody, or reaches everybody for everything."""
    w = world(
        monkeypatch,
        held={"u_alert": holder("u_alert"), "u_inc": holder("u_inc", alert=False, incident=True)},
        used={"u_alert": NOW - timedelta(days=1), "u_inc": NOW - timedelta(days=1)},
    )
    last = {QUIET.name: LONG_AGO, LOUD.name: LONG_AGO}

    run_pass(last=last, controls=(QUIET, LOUD))

    told = {(person, key.split(".")[1]) for person, _, key in w.teller.told}
    assert told == {
        ("u_alert", QUIET.name),
        ("u_alert", LOUD.name),
        ("u_inc", LOUD.name),
    }


def test_when_no_holder_wrote_in_a_week_the_address_is_sent_the_same_sentence_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback, and its once. The holder is still told in chat, because their address costs
    nothing; the install's address is sent the same words through the relay, and a second pass
    sends no second message. Delete this and the fallback never leaves, leaves every pass, or says
    something other than what the chat says."""
    w = world(
        monkeypatch,
        held={"u_ops": holder("u_ops")},
        used={"u_ops": NOW - timedelta(days=8)},
    )

    first = run_pass()
    second = run_pass()

    assert (first.chat, first.email, second.chat, second.email) == (1, 1, 0, 0)
    [mail] = w.relay.sent
    assert mail.to == "ops@example.test"
    assert mail.body == w.teller.told[0][1]
    assert QUIET.name not in mail.subject


def test_with_no_address_set_and_nobody_in_chat_the_episode_is_counted_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case where nobody can be told is counted rather than silent, as an episode and never as a
    person. Delete this and a mechanism nobody can be told of looks exactly like one that was."""
    w = world(monkeypatch, held={}, used={})

    told = run_pass(email=None)

    assert (told.chat, told.email, told.unreachable, told.late) == (0, 0, 1, 1)
    assert w.relay.sent == [] and w.teller.told == []


def test_a_holder_with_no_chat_address_does_not_count_as_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tell` answers None for somebody with no address, and that is not a delivery. Delete this and
    an episode told to nobody is not counted as unreachable."""
    w = world(monkeypatch, held={"u_ops": holder("u_ops")}, used={"u_ops": NOW - timedelta(days=1)})
    w.teller.unaddressed.add("u_ops")

    told = run_pass(email=None)

    assert (told.chat, told.unreachable) == (0, 1)


def test_a_holder_whose_message_was_refused_does_not_count_as_having_used_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Used chat yesterday, and the channel refused: the email goes. Delete this and a channel an
    administrator switched off leaves the alert reaching nobody while the recency says somebody
    was told."""
    w = world(monkeypatch, held={"u_ops": holder("u_ops")}, used={"u_ops": NOW - timedelta(days=1)})
    w.teller.refused.add("u_ops")

    told = run_pass()

    assert (told.chat, told.email) == (0, 1)


def test_a_relay_that_is_not_set_up_claims_nothing_so_the_next_pass_can_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No relay is not a message sent, so the key stays free. Delete this and a relay set up an
    hour later never carries the alert for the silence that began before it."""
    w = world(monkeypatch, held={}, used={})
    w.relay.on = False

    first = run_pass()
    assert (first.email, first.unreachable, w.ledger.records) == (0, 1, {})

    w.relay.on = True
    second = run_pass()
    assert second.email == 1 and len(w.relay.sent) == 1


def test_a_relay_that_refused_leaves_the_episode_sent_and_is_not_counted_as_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal is recorded under the key and not retried every pass, and is not counted as an
    email sent. Delete this and a refused message is counted delivered, or hammers a relay."""
    w = world(monkeypatch, held={}, used={})
    w.relay.answer = CallOutcome.REJECTED

    first, second = run_pass(), run_pass()

    assert (first.email, second.email) == (0, 0)
    assert len(w.relay.sent) == 1


def test_a_second_silence_of_the_same_control_is_a_second_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control ran at a later instant and went quiet again. Delete this and the first
    episode's key is reused for ever and the second is never told."""
    w = world(monkeypatch, held={"u_ops": holder("u_ops")}, used={"u_ops": NOW - timedelta(days=1)})

    run_pass(last={QUIET.name: NOW - timedelta(days=5)})
    run_pass(last={QUIET.name: NOW - timedelta(days=2)})

    assert len(w.teller.told) == 2


def test_a_switched_off_feature_or_notice_sends_nothing_and_loads_nobody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both switches are asked before anything is read about anybody. Delete this and a feature
    that ships off sends on every install."""
    held = {"u_ops": holder("u_ops")}
    used = {"u_ops": NOW - timedelta(days=1)}

    w = world(monkeypatch, held=held, used=used, feature=False)
    assert run_pass() == Told(switched_off=True)
    assert w.teller.told == [] and w.reaches.loaded == []

    w = world(monkeypatch, held=held, used=used, notice_on=False)
    assert run_pass() == Told(switched_off=True)
    assert w.teller.told == [] and w.reaches.loaded == []


def test_with_nothing_late_nobody_is_loaded_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary pass costs one read and loads no reach. Delete this and every pass on a healthy
    install loads every addressed person's reach for nothing."""
    w = world(monkeypatch, held={"u_ops": holder("u_ops")}, used={"u_ops": NOW})

    told = run_pass(last={QUIET.name: NOW - timedelta(minutes=10)})

    assert told == Told()
    assert w.reaches.loaded == [] and w.teller.told == [] and w.relay.sent == []


def test_the_notice_row_names_this_sender_and_keeps_no_switch_of_its_own() -> None:
    """The notices page says it is sent, by this function, and still has no switch. Delete this
    and the page keeps saying no channel sends it, or the notice gains the switch the misuse rule
    says it must not have."""
    row = notice(NoticeKind.CONTROL_NOT_RUN.value)

    assert row.sent_by == "brain.control_not_run_told:tell_overdue_controls"
    assert not row.switchable
    assert "no channel" not in row.how.lower()


def test_the_feature_ships_off_and_names_the_function_that_asks() -> None:
    """The feature is declared with its reader and no default. Delete this and the loop is gated by
    a switch the Features screen does not list."""
    from brain.ops.features import FEATURES
    from brain.ops.features_declared.control_not_run_alerts import CONTROL_NOT_RUN_ALERTS

    assert CONTROL_NOT_RUN_ALERTS in FEATURES
    assert CONTROL_NOT_RUN_ALERTS.read_by == ("brain.control_not_run_told:control_alerts_are_on",)


def test_the_sender_is_the_one_later_sender_and_the_worker_sends_nothing() -> None:
    """The web process tells and the worker marks: this module sends through
    `brain.tell_later.tell` and the mail door alone, and the worker's modules import neither it nor
    them. Delete this and a second path to a chat appears beside the one that re-checks reach, or
    the worker starts needing the channels' tokens and the relay's password."""
    told = ast.parse((SRC / "control_not_run_told.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(told)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("brain.tell_later", "tell") in imported
    assert ("brain.ops.mail", "send_alert") in imported
    assert not any(module == "brain.channels.outbound" for module, _ in imported)
    for worker in ("ops/worker.py", "ops/schedule_runner.py", "ops/schedule_store.py"):
        text = (SRC / worker).read_text(encoding="utf-8")
        assert "control_not_run_told" not in text and "tell_later" not in text, worker


# ---------------------------------------------------------- the mail door, used for an alert
def test_an_alert_to_an_address_is_sent_once_per_occasion_and_again_for_another() -> None:
    """`send_alert` through the ledger, with the positive sibling. Delete this and the same silence
    is emailed every pass, or a later silence is taken for the first."""
    from brain.ops.mail import alert_operation, send_alert

    ledger, relay = MemoryLedger(), Relay()

    def run(work: Callable[[Any], Any]) -> Any:
        return work(ledger)

    def send(occasion: str, to: str = "ops@example.test") -> Any:
        return send_alert(
            run,
            alert_operation(actor="control-alerter", intent_ref=occasion, to=to),
            relay,
            Message(to=to, subject="s", body="b"),
        )

    first, again, other, elsewhere = (
        send("occasion.one"),
        send("occasion.one"),
        send("occasion.two"),
        send("occasion.one", "other@example.test"),
    )

    assert (first.accepted, again.issued, other.accepted, elsewhere.accepted) == (
        True,
        False,
        True,
        True,
    )
    assert len(relay.sent) == 3


def test_a_holder_told_in_chat_but_not_lately_leaves_no_episode_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Told in chat eight days after they last wrote, with no address to fall back on: the message
    reached somebody, so the episode is not counted as one nobody could be told of. Delete this and
    the loop warns every pass about a silence that was told."""
    world(monkeypatch, held={"u_ops": holder("u_ops")}, used={"u_ops": NOW - timedelta(days=8)})

    told = run_pass(email=None)

    assert (told.chat, told.email, told.unreachable) == (1, 0, 0)


def test_one_pass_loads_the_reach_of_no_more_people_than_its_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an install with an enormous roster loads every reach on every pass."""
    held = {f"u_{n:02d}": holder(f"u_{n:02d}") for n in range(5)}
    w = world(monkeypatch, held=held, used=dict.fromkeys(held, NOW))
    monkeypatch.setattr(told_module, "MOST_PEOPLE_PER_PASS", 3)

    run_pass()

    assert w.reaches.loaded == ["u_00", "u_01", "u_02"]
