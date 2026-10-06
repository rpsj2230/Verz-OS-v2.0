"""Marking an answer helpful or unhelpful from the chat it was read in (M16.6.4, the channel half).

The console half is `POST /answer/mark` in `brain.api_routes`: one action, no words, written against
the trace the answer ran under by `brain.ops.learning_signal_store.StoredMarks`, and counted. Most
answers are read in a chat, so a mark the console alone could take is a mark from the people who use
the console. This module is the chat's half of the same action, and it adds no second store, no
second rule about who may mark and no second sentence about what a mark does.

**The answer offers the line, and the line is a word and a reference and nothing else.** A person's
own answer in a chat ends with `mark_line`, which names the two words and the request trace the
answer ran under. A reply whose first line is one of those words and a reference, after any mention
a surface puts in front, is a mark; anything more on that line is not, and is answered as an
ordinary message instead, because a mark that kept a sentence after it would be the free-text store
`brain.ops.feedback` refuses to have, reached from a chat. See
`A_CHAT_MARK_IS_A_WORD_AND_A_REFERENCE_AND_NOTHING_ELSE`.

**Who may mark is the console's rule, asked through the console's store.** `StoredMarks.mark`
writes only when the request ledger's row for the trace names the person marking and is inside
`MARKABLE_FOR`. A trace given to somebody else, one that never ran and one too old are refused there
and nowhere else.

**Every mark is acknowledged with one sentence, whatever became of it.** Counted, and refused
because the reference was not the sender's or does not exist, are told apart nowhere a person can
see: the sentence is `brain.channels.correction.CORRECTION_ACKNOWLEDGEMENT`, which is true of all of
them. A reply that differed would let anybody learn which references exist by typing them. See
`EVERY_MARK_IS_ACKNOWLEDGED_ALIKE`.

**Only the asker's own answer offers it.** The line goes on a direct reply and on the private aside
in a group, which are the answers computed at the asker's reach and written to their thread. A
room's answer is computed at the floor of everybody present and runs under a request that answered
the room, so offering a mark on it would invite marks the ledger then refuses.

Rejected: buttons on surfaces that draw cards. A press is a second inbound shape per vendor, and
admitting a press that writes anything is the owner question the coordinator is filing; the line
works on every surface, cards included, and the buttons can follow it.

Rejected: a bare "helpful" applied to the person's latest answer. Which answer that is depends on
timing the person cannot see, two answers in flight at once would take each other's marks, and
the reference costs one word.

Task ids: M16.6.4
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from brain.channels.correction import CORRECTION_ACKNOWLEDGEMENT

# ------------------------------------------------------------------ written-down reasons
#: Why a mark from a chat is two words and nothing else.
A_CHAT_MARK_IS_A_WORD_AND_A_REFERENCE_AND_NOTHING_ELSE: Final = (
    "A chat reply is free text, and a person marking an answer unhelpful will often say why on "
    "the same line. Reading the word and dropping the rest would tell them their reason was kept "
    "when it was thrown away, and keeping it would be a free-text store reached from a chat. So "
    "a first line that is more than the word and the reference is not a mark, and it is answered "
    "as the ordinary message it is."
)

#: Why a person is told the same thing whatever became of their mark.
EVERY_MARK_IS_ACKNOWLEDGED_ALIKE: Final = (
    "A mark counted, a mark on somebody else's answer and a mark on a reference that names "
    "nothing are three outcomes and one reply, because a reply that differed would let anybody "
    "learn which references exist by typing them one at a time. The outcome goes to the log by "
    "its kind and the person is sent one sentence that is true of all three."
)

#: What a person is sent after any mark. True of every outcome: it was received.
MARK_ACKNOWLEDGEMENT: Final = CORRECTION_ACKNOWLEDGEMENT

#: The words a mark is made with, and what each means.
MARK_WORDS: Final[dict[str, bool]] = {"helpful": True, "unhelpful": False}

#: A request trace as `brain.api_routes.MarkAsked` accepts one: the same alphabet and bound, so
#: a reference the chat offers is one the console's own route would take.
_TRACE: Final = r"[A-Za-z0-9._:-]{1,64}"
_TRACE_RE: Final = re.compile(_TRACE)

#: A mention a surface puts before what somebody typed, as `brain.channels.correction` reads it.
_MENTION: Final = r"(?:@\S+|<@[^>\s]+>|<at>[^<]*</at>)"
_LINE_RE: Final = re.compile(
    rf"(?:{_MENTION}\s+)*(?P<word>[A-Za-z]+)\s+(?P<trace>{_TRACE})", re.IGNORECASE
)


class MarkLineError(Exception):
    """Raised when an answer is offered for marking against something that is not a trace."""


def mark_line(trace_id: str) -> str:
    """The line a person's own chat answer ends with, so it can be marked from where it was read.

    Names the two words and the reference and nothing about the answer. The reference is the
    request's trace, which is quotable and grants nothing: `StoredMarks.mark` asks the ledger
    whether it answered the person marking.
    """
    if not _TRACE_RE.fullmatch(trace_id):
        msg = "an answer offered for marking against something that is not a trace points nowhere"
        raise MarkLineError(msg)
    return f"Reply helpful {trace_id} or unhelpful {trace_id} to mark this answer."


@dataclass(frozen=True)
class MarkRequest:
    """One person's mark on one answer, as read off their reply: a verdict and a reference."""

    trace_id: str
    helpful: bool


def read_mark(text: str) -> MarkRequest | None:
    """The mark this reply makes, or None when it is not one.

    The first non-blank line only, and that line whole. None rather than a refusal for anything
    else, because a message that is not a mark is an ordinary message and is answered as one.
    """
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    matched = _LINE_RE.fullmatch(first)
    if matched is None:
        return None
    helpful = MARK_WORDS.get(matched["word"].lower())
    if helpful is None:
        return None
    return MarkRequest(trace_id=matched["trace"], helpful=helpful)


class AnswerMarks(Protocol):
    """Where a mark is written. `brain.ops.learning_signal_store.StoredMarks`."""

    async def mark(self, *, principal_id: str, trace_id: str, helpful: bool, now: datetime) -> bool:
        """Write the mark when the answer was given to this person; False, writing nothing, else."""
        ...
