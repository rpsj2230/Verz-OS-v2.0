"""A thread is one person's across every app, and it is re-read at the reach they hold now.

The discriminating fixture is a thread whose messages arrived on two surfaces, read from a
third. A listing that grouped by channel lists it twice or not at all, and a continuation that
replayed what was stored shows an answer to somebody who has since lost the grant behind it.
Every refusal below has a sibling proving the same thread still reads when nothing has changed,
because a thread function that returned nothing would pass every refusal on its own.

Real `EntitlementSet`s, real `ChannelCapabilities` with real `Classification`s, and the stored
reference shape read through `refs_from_json` rather than built as `RecordRef`s where the claim
is about what a stored row turns into.

Task ids: M40.2.1.5
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.channels.adapter import ChannelCapabilities
from brain.chat.threads import (
    Thread,
    ThreadError,
    ThreadMessage,
    as_turns,
    continuation_context,
    refs_as_json,
    refs_from_json,
    shown_on,
)
from brain.chat.turns import RecordRef, TurnKind
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.member_activity import (
    MEMBER_SURFACE,
    PERSONAL_CALLS,
    ContinuedThread,
    MemberError,
    RecentThread,
    continue_thread,
    member_gaps,
    recent_threads,
)
from brain.tables.chat import MessageRole

#: Pinned far from any wall clock, because nothing here is about the present.
NOW = datetime(2031, 4, 7, 9, 0, tzinfo=UTC)

ME = "u_weiling"
READ_CLIENT = Capability(value="read:client.name")
READ_SALARY = Capability(value="read:employee.salary")

#: Three surfaces with three ceilings. The console carries the most and WhatsApp the least,
#: which is the ordering the replay rule is about.
CONSOLE = ChannelCapabilities(channel=Channel.CONSOLE, max_classification=Classification.RESTRICTED)
LARK = ChannelCapabilities(channel=Channel.LARK, max_classification=Classification.CONFIDENTIAL)
#: Every one of the three can draw a label, so the ceiling is the only thing separating them
#: and the label rule has a test of its own below.
WHATSAPP = ChannelCapabilities(channel=Channel.WHATSAPP, max_classification=Classification.INTERNAL)
SURFACES = {one.channel: one for one in (CONSOLE, LARK, WHATSAPP)}


def reach(
    *capabilities: Capability, principal_id: str = ME, not_after: datetime | None = None
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities),
        not_after=not_after,
    )


def asked(text: str, channel: Channel, at: datetime) -> ThreadMessage:
    return ThreadMessage(role=MessageRole.USER, at=at, channel=channel, body=text)


def answered(text: str, channel: Channel, at: datetime, raw_refs: object) -> ThreadMessage:
    """An answer whose references arrive as the stored jsonb would, through the reader."""
    return ThreadMessage(
        role=MessageRole.ASSISTANT,
        at=at,
        channel=channel,
        body=text,
        refs=refs_from_json(raw_refs),
    )


CLIENT_REF = {"entity": "client", "record_id": "c_1", "required": READ_CLIENT.value}


def started_on_lark(
    *, thread_id: str = "th_1", owner_id: str = ME, at: datetime = NOW, retired: bool = False
) -> Thread:
    """A question and its answer on Lark, and a follow-up question on WhatsApp."""
    return Thread(
        thread_id=thread_id,
        owner_id=owner_id,
        title="who is the client on the harbour job",
        messages=(
            asked("who is the client on the harbour job", Channel.LARK, at - timedelta(hours=3)),
            answered(
                "The client is recorded.", Channel.LARK, at - timedelta(hours=3), [CLIENT_REF]
            ),
            asked("and their contact", Channel.WHATSAPP, at - timedelta(hours=1)),
        ),
        retired=retired,
    )


def continued(
    threads: list[Thread],
    thread_id: str,
    reader: EntitlementSet,
    *,
    principal_id: str | None = None,
    audience_is_one_person: bool = True,
) -> ContinuedThread | None:
    """`continue_thread` on the console, for the reader's own principal unless told otherwise."""
    return continue_thread(
        threads,
        thread_id,
        principal_id=reader.principal_id if principal_id is None else principal_id,
        reader=reader,
        reading=CONSOLE,
        surfaces=SURFACES,
        audience_is_one_person=audience_is_one_person,
        now=NOW,
    )


# ------------------------------------------------------------------ one history, any app
def test_a_thread_started_on_lark_is_listed_and_continued_from_the_console() -> None:
    """**The leaf, end to end.** Two surfaces wrote the thread and a third reads it: the listing
    names it once, says where it was left off, and the continuation shows the question, the
    answer and the follow-up, with the answer's reference carried into the next question.

    This is also the positive sibling of every refusal in the file.

    Delete this and a listing keyed by channel, which shows the console nothing, passes every
    other test here."""
    reader = reach(READ_CLIENT)
    thread = started_on_lark()

    listed = recent_threads(
        [thread], principal_id=ME, reader=reader, audience_is_one_person=True, now=NOW
    )
    assert [(one.thread_id, one.last_channel) for one in listed] == [("th_1", Channel.WHATSAPP)]
    assert listed[0].last_at == NOW - timedelta(hours=1)

    reopened = continued([thread], "th_1", reader)
    assert reopened is not None
    assert reopened.channel is Channel.CONSOLE
    assert reopened.shown == thread.messages
    assert reopened.context == (RecordRef(entity="client", record_id="c_1", required=READ_CLIENT),)


def test_threads_are_ordered_by_their_last_message_wherever_it_arrived() -> None:
    """The most recent thread is the one somebody last typed into, on any app. An older thread
    touched an hour ago on WhatsApp comes before a newer one left on the console before that.

    Delete this and the list can be ordered by when a thread started, which puts the thread
    somebody is in the middle of below everything they opened since."""
    older = started_on_lark(thread_id="th_old", at=NOW)
    newer = Thread(
        thread_id="th_new",
        owner_id=ME,
        title="a newer question",
        messages=(asked("a newer question", Channel.CONSOLE, NOW - timedelta(minutes=150)),),
    )
    reader = reach()

    both = recent_threads(
        [newer, older], principal_id=ME, reader=reader, audience_is_one_person=True, now=NOW
    )
    one = recent_threads(
        [newer, older],
        principal_id=ME,
        reader=reader,
        audience_is_one_person=True,
        now=NOW,
        limit=1,
    )

    assert [row.thread_id for row in both] == ["th_old", "th_new"]
    assert [row.thread_id for row in one] == ["th_old"]
    with pytest.raises(ValueError, match="at least one"):
        recent_threads(
            [older], principal_id=ME, reader=reader, audience_is_one_person=True, now=NOW, limit=0
        )


# ------------------------------------------------------------------ whose it is
def test_somebody_elses_thread_is_neither_listed_nor_continued_and_reads_as_an_invented_one() -> (
    None
):
    """A thread is the person's, and asking for another person's by id must give exactly the
    answer an id nobody created gives. The sibling is the owner reading the same thread.

    Delete this and a continuation keyed by id alone hands anybody who guesses an id another
    person's questions and answers."""
    theirs = started_on_lark(thread_id="th_theirs", owner_id="u_sam")
    reader = reach(READ_CLIENT)

    assert (
        recent_threads(
            [theirs], principal_id=ME, reader=reader, audience_is_one_person=True, now=NOW
        )
        == ()
    )
    assert continued([theirs], "th_theirs", reader) is None
    assert continued([theirs], "th_invented", reader) is None
    assert continued([theirs], "th_theirs", reach(READ_CLIENT, principal_id="u_sam")) is not None
    assert continued([theirs], "th_invented", reach(READ_CLIENT, principal_id="u_sam")) is None


def test_a_retired_thread_is_neither_listed_nor_continued() -> None:
    """Row-level security hides a retired conversation from the application role, and a loader
    that went round the policy still must not offer one. Sibling: the same thread live.

    Delete this and a conversation the person retired comes back on their landing page."""
    reader = reach(READ_CLIENT)
    gone = started_on_lark(retired=True)

    assert (
        recent_threads([gone], principal_id=ME, reader=reader, audience_is_one_person=True, now=NOW)
        == ()
    )
    assert continued([gone], "th_1", reader) is None
    assert continued([started_on_lark()], "th_1", reader) is not None


def test_a_reach_belonging_to_somebody_else_is_refused() -> None:
    """The name and the reach arrive as two arguments and can name two people, and both answers
    would then be internally consistent. Sibling: the matched pair, in the leaf test.

    Delete this and a handler with the wrong variable in scope lists one person's threads under
    another person's reach."""
    somebody = reach(READ_CLIENT, principal_id="u_sam")
    with pytest.raises(MemberError):
        recent_threads(
            [started_on_lark()],
            principal_id=ME,
            reader=somebody,
            audience_is_one_person=True,
            now=NOW,
        )
    with pytest.raises(MemberError):
        continued([started_on_lark()], "th_1", somebody, principal_id=ME)


def test_both_calls_are_held_to_the_personal_surface_rules() -> None:
    """`member_gaps` is the check that a personal call narrows by a keyword-only principal with
    no default and that no type handed to a member carries a hidden count. The new calls and
    types are listed in it, and this proves the listing is read rather than decorative.

    Delete this and `recent_threads` can grow a `principal_id=""` default with the suite green."""

    def defaulted(threads: object, principal_id: str = "") -> None: ...

    assert {recent_threads, continue_thread} <= set(PERSONAL_CALLS)
    assert {RecentThread, ContinuedThread, ThreadMessage} <= set(MEMBER_SURFACE)
    assert member_gaps() == ()
    assert member_gaps(personal=[defaulted]) != ()


# ------------------------------------------------------------------ what may be shown now
def test_an_answer_whose_grant_was_revoked_is_absent_and_the_question_stays() -> None:
    """The reader lost the grant the answer drew on. The answer goes, with no placeholder in its
    place, and its reference leaves the follow-up context; the person's own questions stay,
    because no grant was needed to know them.

    Asserted as the exact tuple of what remains, which is the strong form: a marker row or a
    count would change it.

    Delete this and a transcript becomes the way round a revocation, one scroll back."""
    thread = started_on_lark()
    reopened = continued([thread], "th_1", reach())

    assert reopened is not None
    assert reopened.shown == (thread.messages[0], thread.messages[2])
    assert reopened.context == ()


def test_an_expired_reader_is_shown_no_threads_at_all() -> None:
    """A titled list of questions is the one part of a thread that needs no grant, so it is the
    part that would survive a contractor's end date. Sibling: the same reader a second before.

    Delete this and an expired account keeps a list of everything it asked."""
    ended = reach(READ_CLIENT, not_after=NOW)
    before = reach(READ_CLIENT, not_after=NOW + timedelta(seconds=1))

    assert (
        recent_threads(
            [started_on_lark()], principal_id=ME, reader=ended, audience_is_one_person=True, now=NOW
        )
        == ()
    )
    assert continued([started_on_lark()], "th_1", ended) is None
    assert (
        recent_threads(
            [started_on_lark()],
            principal_id=ME,
            reader=before,
            audience_is_one_person=True,
            now=NOW,
        )
        != ()
    )
    assert continued([started_on_lark()], "th_1", before) is not None
    # The answer rule is asked at the instant it is given, not at the process clock: read
    # directly at `now`, the expired reader's answer is absent and the unexpired one's is not.
    thread = started_on_lark()
    assert thread.messages[1] not in shown_on(
        thread, ended, reading=CONSOLE, surfaces=SURFACES, now=NOW
    )
    assert thread.messages[1] in shown_on(
        thread, before, reading=CONSOLE, surfaces=SURFACES, now=NOW
    )


def test_a_thread_list_in_a_room_is_empty_and_a_continuation_absent() -> None:
    """On a surface other people read, one person's thread list is every member reading their
    questions. Empty and absent, which is what somebody with no threads sees.

    Delete this and asking the bot in a Lark group for recent threads posts a colleague's
    history into the group."""
    reader = reach(READ_CLIENT)

    assert (
        recent_threads(
            [started_on_lark()],
            principal_id=ME,
            reader=reader,
            audience_is_one_person=False,
            now=NOW,
        )
        == ()
    )
    assert continued([started_on_lark()], "th_1", reader, audience_is_one_person=False) is None


def test_an_answer_is_not_replayed_onto_a_surface_that_may_carry_less() -> None:
    """An answer rendered on the console was rendered for the console's ceiling. Read back on
    WhatsApp it is absent; read back on the console it is there. A Lark answer may be read on
    the console, because the console carries more.

    Delete this and a stored body reaches a surface `assert_can_send` would have refused, without
    ever being a payload."""
    on_console = Thread(
        thread_id="th_c",
        owner_id=ME,
        title="salary band",
        messages=(
            asked("salary band for the role", Channel.CONSOLE, NOW - timedelta(hours=2)),
            answered(
                "The band is recorded.",
                Channel.CONSOLE,
                NOW - timedelta(hours=2),
                [{"entity": "employee", "record_id": "e_1", "required": READ_SALARY.value}],
            ),
        ),
    )
    reader = reach(READ_SALARY)

    assert (
        shown_on(on_console, reader, reading=WHATSAPP, surfaces=SURFACES, now=NOW)
        == on_console.messages[:1]
    )
    assert (
        shown_on(on_console, reader, reading=CONSOLE, surfaces=SURFACES, now=NOW)
        == on_console.messages
    )
    assert shown_on(
        started_on_lark(), reach(READ_CLIENT), reading=CONSOLE, surfaces=SURFACES, now=NOW
    ) == (started_on_lark().messages)


def test_an_answer_is_not_replayed_where_its_opaque_label_could_not_be_drawn() -> None:
    """Two surfaces with one ceiling, differing only in whether a label can be shown. A body from
    the one that can is absent on the one that cannot, and present the other way round.

    Delete this and a rendered lock label arrives as raw text on a surface that declared it
    cannot carry one."""
    labelled = ChannelCapabilities(
        channel=Channel.EMAIL, max_classification=Classification.INTERNAL
    )
    plain = ChannelCapabilities(
        channel=Channel.TELEGRAM, max_classification=Classification.INTERNAL, can_carry_label=False
    )
    surfaces = {labelled.channel: labelled, plain.channel: plain}

    def one_answer(channel: Channel) -> Thread:
        return Thread(
            thread_id="th_l",
            owner_id=ME,
            title="t",
            messages=(answered("An answer.", channel, NOW, []),),
        )

    assert (
        shown_on(one_answer(Channel.EMAIL), reach(), reading=plain, surfaces=surfaces, now=NOW)
        == ()
    )
    assert (
        shown_on(
            one_answer(Channel.TELEGRAM), reach(), reading=labelled, surfaces=surfaces, now=NOW
        )
        != ()
    )
    assert (
        shown_on(one_answer(Channel.EMAIL), reach(), reading=labelled, surfaces=surfaces, now=NOW)
        != ()
    )
    assert (
        shown_on(one_answer(Channel.TELEGRAM), reach(), reading=plain, surfaces=surfaces, now=NOW)
        != ()
    )


def test_an_answer_from_a_surface_whose_ceiling_is_unknown_is_not_shown() -> None:
    """A surface missing from the declared capabilities has no ceiling anybody can compare. The
    answer is absent until its surface is declared, and present once it is.

    Delete this and a new channel's stored answers replay everywhere before anybody says what the
    channel may carry."""
    thread = started_on_lark()
    reader = reach(READ_CLIENT)
    undeclared = {CONSOLE.channel: CONSOLE}

    assert shown_on(thread, reader, reading=CONSOLE, surfaces=undeclared, now=NOW) == (
        thread.messages[0],
        thread.messages[2],
    )
    assert shown_on(thread, reader, reading=CONSOLE, surfaces=SURFACES, now=NOW) == thread.messages


def test_a_system_note_is_shown_under_the_answer_rule_and_is_nobodys_turn() -> None:
    """A system note is not the person's words, so it answers to the ceiling rule like an answer;
    and it is not an exchange, so it contributes no turn to a follow-up.

    Delete this and a note is converted into an answer turn the assistant never gave."""
    note = ThreadMessage(role=MessageRole.SYSTEM, at=NOW, channel=Channel.CONSOLE, body="exported")
    thread = Thread(thread_id="th_s", owner_id=ME, title="t", messages=(note,))

    assert shown_on(thread, reach(), reading=WHATSAPP, surfaces=SURFACES, now=NOW) == ()
    assert shown_on(thread, reach(), reading=CONSOLE, surfaces=SURFACES, now=NOW) == (note,)
    assert as_turns(thread) == ()


# ------------------------------------------------------------------ the stored references
def test_stored_references_round_trip_and_anything_else_is_unreadable() -> None:
    """The stored shape is written by `refs_as_json` and read by `refs_from_json`, and every way
    a row can be wrong reads as unreadable rather than as a shorter list. An empty list is an
    answer that drew on nothing and is kept distinct from unreadable.

    Delete this and an entry carrying a value, or missing its capability, is read as a reference
    that needs no grant."""
    refs = (RecordRef(entity="client", record_id="c_1", required=READ_CLIENT),)
    assert refs_from_json(refs_as_json(refs)) == refs
    assert refs_from_json([]) == ()

    for broken in (
        {"entity": "client"},
        "client:c_1",
        (CLIENT_REF,),
        [CLIENT_REF, "c_2"],
        [CLIENT_REF, 7],
        [{**CLIENT_REF, "value": "Harbour Ltd"}],
        [{"entity": "client", "record_id": "c_1"}],
        [{**CLIENT_REF, "record_id": " "}],
        [{**CLIENT_REF, "record_id": 7}],
        [{**CLIENT_REF, "required": "not a capability"}],
    ):
        assert refs_from_json(broken) is None, broken


def test_an_answer_whose_references_cannot_be_read_is_withheld_and_adds_no_context() -> None:
    """An answer whose dependencies are unknown is not shown and contributes nothing to a
    follow-up, whatever the reader holds. The sibling is the same answer with readable refs.

    Delete this and an unreadable list is read as empty, which is an answer depending on nothing
    and shown to everybody."""
    unreadable = Thread(
        thread_id="th_u",
        owner_id=ME,
        title="t",
        messages=(answered("An answer.", Channel.CONSOLE, NOW, [{"entity": "client"}]),),
    )
    readable = Thread(
        thread_id="th_u",
        owner_id=ME,
        title="t",
        messages=(answered("An answer.", Channel.CONSOLE, NOW, [CLIENT_REF]),),
    )
    reader = reach(READ_CLIENT)

    assert shown_on(unreadable, reader, reading=CONSOLE, surfaces=SURFACES, now=NOW) == ()
    assert continuation_context(unreadable, reader, now=NOW) == ()
    assert shown_on(readable, reader, reading=CONSOLE, surfaces=SURFACES, now=NOW) != ()
    assert continuation_context(readable, reader, now=NOW) != ()


def test_a_follow_up_carries_an_answers_references_and_never_its_words() -> None:
    """A question keeps its words because they are the person's; an answer keeps only what it
    drew on, which is `brain.chat.turns`' rule about context.

    Delete this and an answer's text is carried into the next prompt as an established fact."""
    turns = as_turns(started_on_lark())

    assert [one.kind for one in turns] == [TurnKind.QUESTION, TurnKind.ANSWER, TurnKind.QUESTION]
    assert turns[0].text == "who is the client on the harbour job"
    assert turns[1].text == ""
    assert turns[1].refs == (RecordRef(entity="client", record_id="c_1", required=READ_CLIENT),)
    assert {one.principal_id for one in turns} == {ME}


def test_a_thread_nobody_owns_or_with_nothing_in_it_cannot_be_built() -> None:
    """An ownerless thread is matched by no ownership predicate or by every one, an empty
    thread has no instant to be recent at, and a naive instant orders wrongly against an aware
    one. The sibling is every thread built above.

    Delete this and a blank owner reaches `is_own`, which is the one place a blank is argued
    about rather than refused at the door."""
    message = asked("q", Channel.CONSOLE, NOW)
    with pytest.raises(ThreadError):
        Thread(thread_id="th", owner_id=" ", title="t", messages=(message,))
    with pytest.raises(ThreadError):
        Thread(thread_id="", owner_id=ME, title="t", messages=(message,))
    with pytest.raises(ThreadError):
        Thread(thread_id="th", owner_id=ME, title="t", messages=())
    with pytest.raises(ThreadError):
        asked("q", Channel.CONSOLE, datetime(2031, 4, 7, 9, 0))
