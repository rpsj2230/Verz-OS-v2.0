"""Marking an answer helpful or unhelpful from the chat it was read in (M16.6.4, the channel half).

Driven through `POST /api/v1/channels/lark/events` on the real application with the fixtures
`tests/unit/test_chat_answer.py` builds: a Lark in memory, a bound person, the real answer lane.
The mark store is `StoredMarks` with its write replaced by one that keeps what it was handed and
answers as the ledger would, so what is asserted is what the route asks the console's own store.

Task ids: M16.6.4
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from brain.channels.correction import CORRECTION_ACKNOWLEDGEMENT
from brain.channels.marks import (
    A_CHAT_MARK_IS_A_WORD_AND_A_REFERENCE_AND_NOTHING_ELSE,
    EVERY_MARK_IS_ACKNOWLEDGED_ALIKE,
    MARK_ACKNOWLEDGEMENT,
    MarkLineError,
    MarkRequest,
    mark_line,
    read_mark,
)
from brain.ops.learning_signal_store import StoredMarks
from tests.unit.test_chat_answer import (
    DM,
    GROUP,
    OPEN_IDS,
    WIDE,
    World,
    dm,
    in_group,
    post,
    rooms,
)
from tests.unit.test_chat_answer import client as client  # the fixture, by its name
from tests.unit.test_chat_answer import world as world  # the fixture, by its name

#: Where the reference sits in the line an answer ends with.
_OFFERED = re.compile(r"Reply helpful (\S+) or unhelpful \1 to mark this answer\.$")


class Kept(StoredMarks):
    """`StoredMarks` whose write keeps what it was handed and counts only the traces it gave."""

    def __init__(self) -> None:
        self.given: dict[str, str] = {}
        self.asked: list[tuple[str, str, bool]] = []

    async def mark(self, *, principal_id: str, trace_id: str, helpful: bool, now: datetime) -> bool:
        self.asked.append((principal_id, trace_id, helpful))
        return self.given.get(trace_id) == principal_id


@pytest.fixture
def marks(client: TestClient) -> Kept:
    kept = Kept()
    client.app.state.answer_marks = kept  # type: ignore[attr-defined]
    return kept


def offered(text: str) -> str:
    """The reference an answer's last line offers for marking."""
    found = _OFFERED.search(text.splitlines()[-1])
    assert found is not None, text
    return found.group(1)


# ------------------------------------------------------------------------------ the line


def test_a_mark_is_a_word_and_a_reference_after_any_mention_and_nothing_else() -> None:
    """**The reader's positive and negative halves.** The two words with a reference, in any case
    and after a surface's mention, are marks; a reason on the same line, another word, a missing
    reference and a second line's mark are not.

    Delete this and a reply with a reason after the word is read as a mark with its reason thrown
    away, or a plain question starting "helpful" stops being answered."""
    assert read_mark("helpful t-abc.1") == MarkRequest(trace_id="t-abc.1", helpful=True)
    assert read_mark("@_user_1 Unhelpful t-abc") == MarkRequest(trace_id="t-abc", helpful=False)
    assert read_mark("<at>Brain</at> UNHELPFUL t-abc\n") == MarkRequest("t-abc", False)
    for not_a_mark in (
        "unhelpful t-abc because the figure is wrong",
        "wrong t-abc",
        "helpful",
        "what was helpful t-abc",
        "\n\nhello\nhelpful t-abc",
        "helpful t/abc",
    ):
        assert read_mark(not_a_mark) is None, not_a_mark
    assert "is not a mark" in A_CHAT_MARK_IS_A_WORD_AND_A_REFERENCE_AND_NOTHING_ELSE


def test_the_offered_line_names_its_reference_and_refuses_anything_that_is_not_one() -> None:
    """The line an answer ends with is read back by `read_mark` as both marks on its own
    reference, and a reference outside the console route's alphabet is refused when offered.

    Delete this and an answer can offer a line its own reader does not take."""
    line = mark_line("trace-1")
    assert offered(line) == "trace-1"
    assert read_mark(f"helpful {offered(line)}") == MarkRequest("trace-1", True)
    with pytest.raises(MarkLineError):
        mark_line("not a trace")
    assert MARK_ACKNOWLEDGEMENT == CORRECTION_ACKNOWLEDGEMENT


# ------------------------------------------------------------------------- on the route


def test_a_direct_answer_ends_with_the_line_and_a_mark_on_it_is_written_and_acknowledged(
    client: TestClient,
    world: World,
    marks: Kept,
) -> None:
    """**The leaf's channel half, end to end.** A person's direct answer ends with the line
    naming the request it ran under; replying with one word and that reference hands the console's
    own store the person, the trace and the verdict, and they are told the one sentence. The mark
    computes no answer.

    Delete this and a chat answer can be marked by nobody, which is most answers."""
    post(client, dm(WIDE, "what is the price of WEB-1001", "om_dm_m1"))
    ((_, _, answer),) = world.lark.messages()
    trace = offered(answer)
    marks.given[trace] = "u_wide"

    post(client, dm(WIDE, f"unhelpful {trace}", "om_dm_m2"))

    assert marks.asked == [("u_wide", trace, False)]
    assert [(kind, where, text) for kind, where, text in world.lark.messages()[1:]] == [
        ("chat_id", DM, MARK_ACKNOWLEDGEMENT)
    ]


def test_a_mark_on_an_answer_that_was_not_the_senders_is_told_exactly_what_a_counted_one_is(
    client: TestClient,
    world: World,
    marks: Kept,
) -> None:
    """**DENIED and ABSENT on a mark.** A reference that was somebody else's answer and one that
    names nothing are refused by the store, and the sender is told the same sentence a counted mark
    is told.

    Delete this and typing references one at a time tells anybody which exist."""
    marks.given["t-real"] = "u_narrow"

    post(client, dm(WIDE, "helpful t-real", "om_dm_m3"))
    post(client, dm(WIDE, "helpful t-nothing", "om_dm_m4"))

    assert marks.asked == [("u_wide", "t-real", True), ("u_wide", "t-nothing", True)]
    told = [text for _, _, text in world.lark.messages()]
    assert told == [MARK_ACKNOWLEDGEMENT, MARK_ACKNOWLEDGEMENT]
    assert "one sentence" in EVERY_MARK_IS_ACKNOWLEDGED_ALIKE


def test_a_mark_with_a_reason_after_it_is_answered_as_an_ordinary_message(
    client: TestClient,
    world: World,
    marks: Kept,
) -> None:
    """A reply carrying a reason after the reference is not a mark: nothing is written, and it is
    answered as any other message is.

    Delete this and a person's reason is silently dropped while they are told it was received."""
    post(client, dm(WIDE, "unhelpful t-abc the price is wrong", "om_dm_m5"))

    assert marks.asked == []
    ((_, _, text),) = world.lark.messages()
    assert text != MARK_ACKNOWLEDGEMENT


def test_in_a_group_the_asker_s_aside_offers_the_line_and_the_room_s_posting_does_not(
    client: TestClient,
    world: World,
    marks: Kept,
) -> None:
    """The asker's own answer in a group, sent where only they see it, ends with the line; the
    room's posting, computed for the room, never does, including when it is the asker's answer
    because everybody holds the same.

    Delete this and a room is invited to mark an answer the ledger says was not theirs."""
    rooms(world, [WIDE, OPEN_IDS["u_prefix"]])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_m1"))
    room, aside = (text for _, _, text in world.lark.messages())
    assert offered(aside)
    assert "to mark this answer" not in room

    world.lark.sent.clear()
    rooms(world, [WIDE])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_m2"))
    ((kind, where, alone),) = world.lark.messages()
    assert (kind, where) == ("chat_id", GROUP)
    assert "to mark this answer" not in alone


def test_a_mark_typed_in_a_group_is_acknowledged_to_the_sender_alone(
    client: TestClient,
    world: World,
    marks: Kept,
) -> None:
    """A mark addressed to the bot in a group is written in the sender's name and acknowledged in
    their own conversation, never in the room.

    Delete this and a room learns who marked which answer."""
    rooms(world, [WIDE, OPEN_IDS["u_prefix"]])
    post(client, in_group(WIDE, "helpful t-abc", "om_g_m3"))

    assert marks.asked == [("u_wide", "t-abc", True)]
    ((_, where, text),) = world.lark.messages()
    assert where != GROUP and text == MARK_ACKNOWLEDGEMENT


def test_a_process_with_no_mark_store_still_acknowledges_alike_and_writes_nothing(
    client: TestClient,
    world: World,
) -> None:
    """With no database there is nowhere to write a mark, and the sender is told the one sentence
    rather than having the line answered as a question.

    Delete this and a process without a database answers "helpful t-abc" with a model call."""
    post(client, dm(WIDE, "helpful t-abc", "om_dm_m6"))
    ((_, _, text),) = world.lark.messages()
    assert text == MARK_ACKNOWLEDGEMENT
