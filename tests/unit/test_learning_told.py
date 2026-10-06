"""Each person is told their own week of learning once, at their own reach, with its undo.

The pure half holds the week and its key, which learnings a person's week holds, the message's
words, and `brain.learning_told.send_learning_digests` with its load, its switch and its sender
replaced. The server half reads the learnings back from PostgreSQL through the loader the sender
uses.

Dates are in 2999 and 2019, far from any plausible wall clock, for CLAUDE.md's reason about a
fixture that is a clock.

Task ids: M16.5.1
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI

from brain import learning_told
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.escalation_told import INTENT_PREFIX as EXPIRED_PREFIX
from brain.learning_told import (
    A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW,
    A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING,
    CHANGE_WORDS,
    INTENT_PREFIX,
    MOST_LEARNINGS_PER_PASS,
    ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY,
    OPENING,
    SEND_EVERY,
    SIGNAL_WORDS,
    THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS,
    THE_UNDO_IS_THE_PERSONS_OWN_FORGET_ON_A_PAGE_EVERY_RECIPIENT_OPENS,
    THE_WEB_PROCESS_SENDS_IT_BECAUSE_THE_MAIL_RELAY_IS_THE_APPLICATIONS,
    UNDO_PAGE,
    UNDO_PAGE_UNLINKED,
    UNDOING,
    CoveredWeek,
    Loaded,
    Told,
    covered_week,
    digest_text,
    intent_ref_for,
    learning_pass,
    learnings_since,
    own_digest,
    send_learning_digests,
    undo_page,
    worth_sending,
)
from brain.memory.correction import Correction
from brain.memory.digest import DIGEST_PERIOD, DIGEST_TIERS, Learning, WeeklyDigest
from brain.memory.formation import Formation, MemoryKind
from brain.memory.signals import Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change, blast_radius, propose
from brain.ops.notices import NoticeKind
from brain.tables.channel import DeliveryOutcome

ROOT = Path(__file__).resolve().parents[2]

#: A Wednesday, so the week covered is the one before the week it falls in.
NOW = datetime(2999, 6, 5, 9, 0, tzinfo=UTC)
WEEK = covered_week(NOW, UTC)

CLIENT_NAME = Capability(value="read:client.name")
CLIENT_SALARY = Capability(value="read:client.salary")
PAGE = "https://brain.example.invalid/me/undo/"


def reader(principal_id: str = "u_me", *, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(Grant(capability=CLIENT_NAME, scope=Scope.department("web")),),
        not_after=not_after,
    )


def learning(
    memory_id: str,
    *,
    principal: str = "u_me",
    at: datetime | None = None,
    capability: Capability = CLIENT_NAME,
    replaced_id: str | None = None,
    change: Change = Change.PREFERENCE,
    evidence: frozenset[Signal] = frozenset({Signal.REASKED}),
) -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(change, subject=f"memory:{memory_id}"),
        formation=Formation(
            principal_id=principal,
            capabilities=(capability,),
            scope=Scope.department("web"),
            ent_hash="e" * 32,
            formed_at=WEEK.covers_from + timedelta(days=2) if at is None else at,
            kind=MemoryKind.PERSISTENT,
        ),
        evidence=evidence,
        replaced_id=replaced_id,
    )


def ids(digest: WeeklyDigest) -> list[str]:
    return [one.memory_id for one in digest.entries]


# ------------------------------------------------------------------------ the week
def test_a_run_anywhere_in_a_week_covers_the_monday_to_sunday_before_it() -> None:
    """**The positive case of the key.** A Wednesday covers the Monday to Sunday before its own
    week, keyed by that ISO week, and every instant of the same week covers the same one. Delete
    this and two runs in one week can cover two windows under two keys, so a person is told
    twice."""
    assert WEEK.covers_from == datetime(2999, 5, 27, tzinfo=UTC)
    assert WEEK.covers_to == datetime(2999, 6, 3, tzinfo=UTC)
    assert WEEK.key == "2999-W22"
    monday = datetime(2999, 6, 3, tzinfo=UTC)
    for at in (monday, monday + timedelta(days=6, hours=23, minutes=59), NOW):
        assert covered_week(at, UTC) == WEEK
    assert covered_week(monday - timedelta(microseconds=1), UTC) != WEEK


def test_consecutive_weeks_meet_with_no_overlap_and_no_gap() -> None:
    """See `ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY`. Delete this and two weeks can share
    days, so one learning arrives twice with two undo links, or a day can fall between them."""
    assert "neither overlap nor leave a gap" in ONE_WEEK_IS_ONE_MESSAGE_AND_THE_WEEK_IS_THE_KEY
    following = covered_week(NOW + timedelta(days=7), UTC)
    assert following.covers_from == WEEK.covers_to
    assert following.key != WEEK.key
    assert intent_ref_for(following) != intent_ref_for(WEEK)
    assert intent_ref_for(WEEK) == f"{INTENT_PREFIX}.{WEEK.key}"


def test_a_week_holding_a_change_of_clocks_is_bounded_by_local_midnights() -> None:
    """In London the clocks go forward on Sunday 31 March 2999, so the week ends at midnight
    British Summer Time, an hour before midnight UTC. Delete this and the boundary can be computed
    as seven days of hours, so a learning formed in the last hour of a Sunday falls in the wrong
    week."""
    london = ZoneInfo("Europe/London")
    week = covered_week(datetime(2999, 4, 3, 12, tzinfo=UTC), london)
    assert week.covers_from == datetime(2999, 3, 25, 0, tzinfo=UTC)
    assert week.covers_to == datetime(2999, 3, 31, 23, tzinfo=UTC)
    assert week.covers_to - week.covers_from == timedelta(days=7) - timedelta(hours=1)


def test_a_week_that_ends_before_it_starts_or_has_no_key_is_refused() -> None:
    """A week with no key sends every person's message under one key, and an inverted one covers
    nothing. Delete this and either can be built and keyed."""
    with pytest.raises(ValueError, match="ends before it starts"):
        CoveredWeek(covers_from=WEEK.covers_to, covers_to=WEEK.covers_from, key="k")
    with pytest.raises(ValueError, match="no key"):
        CoveredWeek(covers_from=WEEK.covers_from, covers_to=WEEK.covers_to, key=" ")
    assert CoveredWeek(covers_from=WEEK.covers_from, covers_to=WEEK.covers_to, key="k").key == "k"


def test_the_key_is_not_one_another_later_message_uses() -> None:
    """The operation ledger keys a send by person and intent, so a prefix shared with the expired
    question's message would let one stand for the other. Delete this and a rename can make them
    collide."""
    assert {INTENT_PREFIX, EXPIRED_PREFIX} == {"learning_digest", "escalation_expired"}


# ------------------------------------------------------------------------ whose week
def test_a_persons_week_holds_their_own_learnings_inside_the_week() -> None:
    """**The positive case.** A learning formed from the reader's own conversation, in the week,
    that they may recall, is in their week, newest first. Delete this and a week that holds nothing
    passes every refusal below."""
    older = learning("m_older", at=WEEK.covers_from + timedelta(days=1))
    newer = learning("m_newer", at=WEEK.covers_to)
    found = own_digest(reader=reader(), learnings=[older, newer], marked=(), week=WEEK, now=NOW)
    assert ids(found) == ["m_newer", "m_older"]
    assert (found.covers_from, found.covers_to) == (WEEK.covers_from, WEEK.covers_to)


def test_somebody_elses_learning_is_never_in_a_persons_week_even_when_they_may_recall_it() -> None:
    """See `A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW`. A colleague's learning formed
    in a place the reader reaches would pass recall; ownership is what keeps it out. Delete this and
    a person is told what the system learnt from somebody else."""
    assert "in nobody else's week" in A_WEEK_IS_THE_PERSONS_OWN_AND_AT_THE_REACH_THEY_HOLD_NOW
    theirs = learning("m_theirs", principal="u_colleague")
    mine = learning("m_mine")
    found = own_digest(reader=reader(), learnings=[theirs, mine], marked=(), week=WEEK, now=NOW)
    assert ids(found) == ["m_mine"]


def test_a_learning_the_person_may_no_longer_recall_is_not_named() -> None:
    """A learning formed under a capability the reader does not hold now is left out by recall.
    Delete this and a person who lost a grant is told about what it reached."""
    hidden = learning("m_hidden", capability=CLIENT_SALARY)
    found = own_digest(
        reader=reader(), learnings=[hidden, learning("m_kept")], marked=(), week=WEEK, now=NOW
    )
    assert ids(found) == ["m_kept"]


def test_a_learning_already_undone_or_replaced_is_not_offered_again() -> None:
    """Its undo would do nothing, and a row with a button that does nothing reads as broken. Delete
    this and an undone learning comes back in the next week's message."""
    found = own_digest(
        reader=reader(),
        learnings=[learning("m_undone"), learning("m_kept")],
        marked=frozenset({"m_undone"}),
        week=WEEK,
        now=NOW,
    )
    assert ids(found) == ["m_kept"]


def test_a_learning_after_the_week_waits_for_next_week_and_one_on_its_start_was_last_week() -> None:
    """The window is half open at the week's start and closed at its end, so a learning on a
    boundary is in exactly one week. Delete this and a run late in the week names this week's
    learnings early, then names them again next week."""
    edges = [
        learning("m_on_start", at=WEEK.covers_from),
        learning("m_on_end", at=WEEK.covers_to),
        learning("m_after", at=WEEK.covers_to + timedelta(hours=1)),
    ]
    found = own_digest(reader=reader(), learnings=edges, marked=(), week=WEEK, now=NOW)
    assert ids(found) == ["m_on_end"]
    following = covered_week(NOW + timedelta(days=7), UTC)
    later = own_digest(
        reader=reader(),
        learnings=edges,
        marked=(),
        week=following,
        now=NOW + timedelta(days=7),
    )
    assert ids(later) == ["m_after"]


def test_an_empty_week_is_not_worth_sending_and_a_week_with_one_learning_is() -> None:
    """See `A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING`. Delete this and an empty message goes to
    everybody every Monday."""
    assert "sent nothing at all" in A_WEEK_WITH_NOTHING_LEARNT_SENDS_NOTHING
    one = own_digest(reader=reader(), learnings=[learning("m")], marked=(), week=WEEK, now=NOW)
    assert worth_sending(one)
    assert not worth_sending(replace(one, entries=()))


# ------------------------------------------------------------------------ the words
def test_every_change_a_week_can_carry_and_every_signal_has_words() -> None:
    """Derived from the tiers rather than restated, so a change moved into the digest without words
    fails here. Delete this and a person reads `fast_path_rule` in a chat."""
    carried = {
        change
        for change in Change
        if change not in CHANGES_WHAT_ANYBODY_MAY_SEE and blast_radius(change) in DIGEST_TIERS
    }
    assert set(CHANGE_WORDS) == carried
    assert set(SIGNAL_WORDS) == set(Signal)
    assert set(UNDOING) == set(Correction)


def test_the_message_names_each_learning_its_reason_and_where_to_undo_it() -> None:
    """**The positive case of the words.** The week's first and last day, then each learning's kind,
    day, reason, what undoing it does, and the address of its own undo. Delete this and a message
    can lose the undo while every other test passes."""
    replaced = learning("m_new", replaced_id="m_old", at=WEEK.covers_from + timedelta(days=3))
    alone = learning(
        "m_alone",
        change=Change.RETRIEVAL_DEMOTION,
        evidence=frozenset(),
        at=WEEK.covers_from + timedelta(days=1),
    )
    found = own_digest(reader=reader(), learnings=[replaced, alone], marked=(), week=WEEK, now=NOW)
    text = digest_text(found, page=PAGE, zone=UTC)
    first, *lines = text.split("\n")

    assert "from 27 May to 2 June" in first
    assert lines == [
        "- How you like answers shaped, learnt on 30 May, because you asked again in other words. "
        f"Undoing it puts back what it replaced. Undo it at {PAGE}m_new.",
        "- A source to rank lower for you, learnt on 28 May. Undoing it stops it being used. "
        f"Undo it at {PAGE}m_alone.",
    ]


def test_the_message_carries_no_subject_reference_and_no_count() -> None:
    """See `THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS`. The proposal's subject is a
    reference the product understands and no person should read, and a count beside a filtered list
    is a subtraction. Delete this and either can be added to the line."""
    assert "the words are read on the person's own page" in (
        THE_MESSAGE_NAMES_A_LEARNING_AND_NEVER_WHAT_IT_SAYS
    )
    found = own_digest(
        reader=reader(),
        learnings=[learning("m_one"), learning("m_two")],
        marked=(),
        week=WEEK,
        now=NOW,
    )
    text = digest_text(found, page=PAGE, zone=UTC)
    assert "memory:m_one" not in text and "memory:m_two" not in text
    opening, *lines = text.split("\n")
    assert opening == OPENING.format(first="27 May", last="2 June")
    assert len(lines) == 2 and all(one.startswith("- ") for one in lines)


def test_the_digests_link_is_a_console_page_posting_the_grant_free_undo_route() -> None:
    """See `THE_UNDO_IS_THE_PERSONS_OWN_FORGET_ON_A_PAGE_EVERY_RECIPIENT_OPENS`. Held against the
    console's route file and the path its page posts, which must be the mounted route that asks for
    no grant (`tests/unit/test_mine_routes.py` holds that a person with none undoes there), rather
    than against itself. Delete this and the digest can link a page that is not there, or one
    posting Forget on My workspace, which a recipient without the member grant is refused."""
    from brain.api import API_PREFIX
    from brain.mine_routes import LEARNING_UNDO_PATH, router

    assert "gated on authorship and on no grant" in (
        THE_UNDO_IS_THE_PERSONS_OWN_FORGET_ON_A_PAGE_EVERY_RECIPIENT_OPENS
    )
    pages = ROOT / "console" / "src" / "pages"
    route = (pages / "LearningUndo.route.tsx").read_text("utf-8")
    query = (pages / "learningUndoQuery.ts").read_text("utf-8")
    [path] = re.findall(r'\{ path: "([^"]+)", element: <LearningUndo />', route)
    [prefix] = re.findall(r'export const UNDO_PAGE_PREFIX = "([^"]+)"', query)
    [posted] = re.findall(r'export const LEARNING_UNDO_API_PATH = "([^"]+)"', query)
    assert f"/{path}" == f"{UNDO_PAGE}:memoryId" and prefix == UNDO_PAGE
    assert posted == LEARNING_UNDO_PATH
    assert f"{API_PREFIX}{posted}" in {getattr(one, "path", "") for one in router.routes}


def test_the_undo_is_linked_at_the_installs_own_address_or_named_when_there_is_none() -> None:
    """Delete this and an install with no public address sends a bare path no chat can open."""
    assert undo_page("https://brain.example.invalid/auth/callback") == PAGE
    assert undo_page("") == UNDO_PAGE_UNLINKED
    assert UNDO_PAGE_UNLINKED.endswith(UNDO_PAGE) and not UNDO_PAGE_UNLINKED.startswith("/")


# ------------------------------------------------------------------------ the figures
def test_a_process_asks_often_enough_to_send_on_the_first_day_of_the_week() -> None:
    """Delete this and a cadence edit can leave a week's message arriving on the Thursday, or the
    loop spinning."""
    assert timedelta(0) < SEND_EVERY <= timedelta(days=1)
    assert SEND_EVERY < DIGEST_PERIOD
    assert MOST_LEARNINGS_PER_PASS > 0


def test_only_the_application_may_read_the_mail_relay_so_the_web_process_sends_the_digest() -> None:
    """See `THE_WEB_PROCESS_SENDS_IT_BECAUSE_THE_MAIL_RELAY_IS_THE_APPLICATIONS`, held against the
    vault's own policies: the application's is the one that reads the relay's slot, by name or by a
    wildcard. Delete this and the day a policy grants the worker the relay, the reason this is not a
    worker control has stopped being true with nothing saying so."""
    assert "the mail relay's password" in (
        THE_WEB_PROCESS_SENDS_IT_BECAUSE_THE_MAIL_RELAY_IS_THE_APPLICATIONS
    )
    root = ROOT / "ops" / "openbao" / "policies"
    readers = [
        one.name
        for one in sorted(root.glob("*.hcl"))
        if re.search(r'path "providers/data/(mail_relay|\+)"', one.read_text("utf-8"))
    ]
    assert readers == ["application.hcl"]


def test_a_summary_names_no_person_and_no_number() -> None:
    """A run's line is read by whoever reads the logs. Delete this and it can say who learnt what,
    or how many people did."""
    told = Told(sent=3, already=2, undelivered=1, full=True)
    said = told.summary()
    assert not re.search(r"\d", said)
    assert "sent" in said and "already sent" in said and "not be delivered" in said
    assert Told().summary() == "the learning digest: nothing new sent"
    assert "switched off" in Told(switched_off=True).summary()


# ------------------------------------------------------------------------ the sender
@dataclass
class Session:
    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@dataclass
class Sent:
    outcome: DeliveryOutcome
    issued: bool = True


@dataclass
class Teller:
    """`brain.tell_later.tell` in memory: every message it was asked to send, and its answers."""

    told: list[tuple[str, str, str]] = field(default_factory=list)
    answers: dict[str, Sent | None] = field(default_factory=dict)

    async def __call__(
        self, request: Any, person: str, said: str, *, intent_ref: str, now: datetime
    ) -> Sent | None:
        self.told.append((person, said, intent_ref))
        return self.answers.get(person, Sent(DeliveryOutcome.SENT))


@dataclass
class Readers:
    """`brain.gate.resolve.EntitlementStore` over a dictionary, every reach in `web`."""

    expired: frozenset[str] = frozenset()
    asked: list[tuple[str, datetime]] = field(default_factory=list)

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        self.asked.append((principal_id, now))
        ends = now - timedelta(seconds=1) if principal_id in self.expired else None
        return reader(principal_id, not_after=ends)


def sending(
    monkeypatch: pytest.MonkeyPatch,
    learnings: tuple[Learning, ...],
    *,
    on: bool = True,
    marked: frozenset[str] = frozenset(),
) -> Teller:
    teller = Teller()

    async def switched(session: Any, kind: NoticeKind) -> bool:
        assert kind is NoticeKind.LEARNING_DIGEST
        return on

    async def loaded(sessions: Any, since: datetime, **kwargs: Any) -> Loaded:
        assert since == WEEK.covers_from
        return Loaded(learnings=learnings, marked=marked)

    monkeypatch.setattr(learning_told, "notice_is_on", switched)
    monkeypatch.setattr(learning_told, "learnings_since", loaded)
    monkeypatch.setattr(learning_told, "tell", teller)
    return teller


def send(readers: Readers | None = None, **kwargs: Any) -> Told:
    return asyncio.run(
        send_learning_digests(
            None,  # type: ignore[arg-type]
            Session,  # type: ignore[arg-type]
            now=NOW,
            zone=UTC,
            page=PAGE,
            readers=Readers() if readers is None else readers,
            **kwargs,
        )
    )


LEARNT = (
    learning("m_mine"),
    learning("m_also_mine", at=WEEK.covers_from + timedelta(days=4)),
    learning("m_theirs", principal="u_colleague"),
)


def test_each_person_with_a_learning_is_told_their_own_week_once_under_its_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The positive case.** One message per person a learning was formed from, naming their own
    learnings and nobody else's, under the week's key, at their reach loaded now. Delete this and
    the loop can tell nobody while its switch reads on."""
    teller = sending(monkeypatch, LEARNT)
    readers = Readers()
    told = send(readers)

    assert told == Told(sent=2)
    assert [(person, ref) for person, _, ref in teller.told] == [
        ("u_colleague", intent_ref_for(WEEK)),
        ("u_me", intent_ref_for(WEEK)),
    ]
    mine = teller.told[1][1]
    assert "m_mine" in mine and "m_also_mine" in mine and "m_theirs" not in mine
    assert readers.asked == [("u_colleague", NOW), ("u_me", NOW)]


def test_switched_off_nothing_is_read_or_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The administrator's switch, asked before the load. Delete this and switching the notice off
    on the Notifications screen stops nothing."""
    teller = sending(monkeypatch, LEARNT, on=False)
    readers = Readers()
    assert send(readers) == Told(switched_off=True)
    assert teller.told == [] and readers.asked == []


def test_a_person_with_nothing_learnt_or_whose_reach_has_ended_is_sent_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Someone named in `only` with no learning of their own, and someone whose reach has ended, are
    told nothing, and the person beside them still is: recall admits nothing to an ended reach, so
    its week is empty. Delete this and an empty week is sent, or a leaver is written to."""
    teller = sending(monkeypatch, LEARNT)
    told = send(
        Readers(expired=frozenset({"u_colleague"})), only={"u_me", "u_quiet", "u_colleague"}
    )
    assert told == Told(sent=1)
    assert [person for person, _, _ in teller.told] == ["u_me"]


def test_only_narrows_the_people_and_never_widens_a_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An install check names its own people and nobody else is written to; naming somebody does not
    put anybody else's learning in their week. Delete this and the check writes to the install's
    real people."""
    teller = sending(monkeypatch, LEARNT)
    assert send(only={"u_colleague"}) == Told(sent=1)
    [(person, said, _)] = teller.told
    assert person == "u_colleague" and "m_theirs" in said and "m_mine" not in said


def test_a_learning_already_undone_is_not_sent_and_a_week_left_empty_by_it_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the loader's marked set can be dropped between the load and the week."""
    teller = sending(monkeypatch, LEARNT, marked=frozenset({"m_theirs", "m_mine"}))
    assert send() == Told(sent=1)
    [(person, said, _)] = teller.told
    assert person == "u_me" and "m_also_mine" in said and "m_mine," not in said


def test_each_outcome_is_counted_as_what_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second pass is handed the first's record and counts as already sent; a refusal or nowhere
    to send counts as undelivered and never as sent. Delete this and a second pass reads as a fresh
    send, or a refused one as delivered."""
    learnt = (*LEARNT, learning("m_gone", principal="u_gone"), learning("m_far", principal="u_far"))
    teller = sending(monkeypatch, learnt)
    teller.answers = {
        "u_me": Sent(DeliveryOutcome.SENT, issued=False),
        "u_colleague": Sent(DeliveryOutcome.REFUSED),
        "u_gone": None,
        "u_far": Sent(DeliveryOutcome.SENT),
    }
    assert send() == Told(sent=1, already=1, undelivered=2)


def test_a_pass_finishes_its_week_once_and_a_switched_off_pass_finishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop's own pass: the week covered at its instant, handed to the sender, and not asked
    again by this process once finished; switched off, the week stays unfinished so switching it on
    sends it. Delete this and the loop composes every week's digests every hour, or never again
    after one pass on a switched-off notice."""
    import brain.locale

    asked: list[CoveredWeek | None] = []
    answer = Told(sent=1)

    async def sender(request: Any, sessions: Any, **kwargs: Any) -> Told:
        asked.append(kwargs["week"])
        assert kwargs["now"] == NOW and kwargs["zone"] is UTC
        return answer

    monkeypatch.setattr(learning_told, "send_learning_digests", sender)

    def passed(app: FastAPI, *, now: datetime, done: str) -> str:
        return asyncio.run(learning_pass(app, now=now, done=done))

    monkeypatch.setattr(brain.locale, "time_zone", lambda: UTC)
    app = FastAPI()
    assert passed(app, now=NOW, done="") == ""
    assert asked == []

    app.state.db_sessions = Session
    assert passed(app, now=NOW, done="") == WEEK.key
    assert passed(app, now=NOW, done=WEEK.key) == WEEK.key
    assert asked == [WEEK]

    answer = Told(switched_off=True)
    assert passed(app, now=NOW, done="earlier") == "earlier"


# ------------------------------------------------------------------------ the server half
@pytest.mark.needs_db
def test_the_loader_reads_the_weeks_learnings_and_the_memories_already_marked() -> None:
    """**Against PostgreSQL.** Two learnings recorded, one replacing a memory a supersession marked:
    both are read as the domain's learnings, the replaced memory is marked, a bound of one reads the
    newest and says the load came back full, and a week starting after them reads nothing. Delete
    this and the sender can read nothing on a real install while the stubbed tests stay green.
    **Skips without a server.**"""
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_memory_store import LONG_AGO, seed, through_0061

    with through_0061("brain_learning_told") as url:
        seed(url)

        async def walk() -> tuple[Loaded, Loaded, Loaded]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                every = await learnings_since(sessions, LONG_AGO)
                newest = await learnings_since(sessions, LONG_AGO, most=1)
                none = await learnings_since(sessions, datetime(2999, 1, 1, tzinfo=UTC))
                return every, newest, none
            finally:
                await engine.dispose()

        every, newest, none = run(walk)

    assert sorted(one.memory_id for one in every.learnings) == ["m_alone", "m_learnt"]
    learnt = next(one for one in every.learnings if one.memory_id == "m_learnt")
    assert learnt.replaced_id == "m_before" and learnt.formation.principal_id == "u_subject"
    assert every.marked == frozenset({"m_before"}) and not every.full
    assert [one.memory_id for one in newest.learnings] == ["m_alone"] and newest.full
    assert none == Loaded(learnings=(), marked=frozenset())


@pytest.mark.needs_db
def test_two_web_workers_racing_one_week_send_each_person_one_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The ledger key, across processes, against PostgreSQL.** Two web workers, each its own
    application with its own connection to the operation ledger, run the same week at once through
    the real `tell` and `deliver`, to a Slack whose every send is slow enough that the second
    arrives while the first is still in flight. Each person is sent exactly one message, and the
    two passes between them count one send per person. Delete this and the guarantee that makes a
    loop in every forked web worker safe rests on a unit test with one process and a ledger in
    memory. **Skips without a server.**"""
    import json
    import threading
    import time as clock
    from types import SimpleNamespace

    from brain.channels.adapter import VendorAnswer
    from brain.gate.context import Channel
    from brain.mailbox_read import request_for
    from brain.ops.channel_store import channel_secret_ref
    from brain.settings import settings_from
    from tests.unit.test_acceptance import at_head
    from tests.unit.test_channel_pipeline import Deliveries, Records, Secrets, fresh_record
    from tests.unit.test_tell_later import LastUsedBook

    @dataclass
    class SlowSlack:
        """`ChannelTransport` that keeps every request, slowly, and answers as Slack accepts."""

        sent: list[Any] = field(default_factory=list)
        lock: threading.Lock = field(default_factory=threading.Lock)

        def send(self, request: Any) -> VendorAnswer:
            clock.sleep(0.3)
            with self.lock:
                self.sent.append(request)
            return VendorAnswer(status=200, body=b'{"ok": true}')

        def read(self, request: Any) -> VendorAnswer:
            return VendorAnswer(connection_failed=True)

    async def switched(session: Any, kind: NoticeKind) -> bool:
        return True

    async def loaded(sessions: Any, since: datetime, **kwargs: Any) -> Loaded:
        return Loaded(learnings=LEARNT, marked=frozenset())

    monkeypatch.setattr(learning_told, "notice_is_on", switched)
    monkeypatch.setattr(learning_told, "learnings_since", loaded)
    slack = SlowSlack()
    secret = json.dumps({"signing_secret": "s" * 32, "bot_token": "xoxb-test"})

    with at_head("brain_learning_told_race") as url:

        def worker() -> FastAPI:
            app = FastAPI()
            state = app.state
            state.settings = settings_from({"BRAIN_DATABASE_URL": url})
            state.gate = SimpleNamespace(store=Readers())
            state.channel_records = Records({Channel.SLACK: fresh_record(Channel.SLACK, tenant={})})
            state.channel_addresses = LastUsedBook(
                {"u_me": (Channel.SLACK, "UME0001"), "u_colleague": (Channel.SLACK, "UCOL0001")}
            )
            state.channel_secrets = Secrets({channel_secret_ref(Channel.SLACK).path: secret})
            state.channel_transport = slack
            state.channel_deliveries = Deliveries()
            return app

        async def race() -> list[Told]:
            passes = [
                send_learning_digests(
                    request_for(one),
                    Session,  # type: ignore[arg-type]
                    now=NOW,
                    zone=UTC,
                    page=PAGE,
                    readers=Readers(),
                    week=WEEK,
                )
                for one in (worker(), worker())
            ]
            return list(await asyncio.gather(*passes))

        told = asyncio.run(race())

    sent_to = sorted(json.loads(bytes(one.body))["channel"] for one in slack.sent)
    assert sent_to == ["UCOL0001", "UME0001"]
    assert sum(one.sent for one in told) == 2
    assert sum(one.already + one.undelivered for one in told) == 2
