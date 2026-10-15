"""What one exchange is filed as, and what a follow-up carries from the thread it continues.

`brain.tables.chat` built the storage and `brain.chat.threads` decided how a thread is read back,
and nothing wrote a message, so every question anybody asked was answered and forgotten. This
module holds the decisions a writer has to make and nothing that opens a connection: what the
stored answer says, what it drew on, which thread a chat message belongs to, and what a follow-up
is asked with. `brain.chat.store` does the writing.

**The stored answer is the text the asker was shown, and its references come from the typed
results it was composed from (M9.2.1).** The text is read out of the frames the lane wrote, which
are the only place an abstention's and a failure's words exist, so what is filed is what was on
the screen. The references are read off `ComposedAnswer.payload`, the redacted payload, and
never off anything a model wrote: a model's prose can name a record it was not shown, and a
reference taken from prose would be a reference nothing checked.

**An answer whose sources cannot be named is filed as unreadable, not as sourceless.** A cache hit
carries its text and not the payload behind it, and a record in a payload with no entity or no id
cannot be re-checked. Filed as an empty list, either would read as an answer that drew on
nothing and be shown again to its reader whatever they have lost since. Filed as unreadable, it
is withheld when shown again, and the question beside it still is. See
`AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_FILED_AS_UNREADABLE`.

**A refusal drew on nothing, and is filed so.** Every kind of nothing reaches the asker as one
sentence (`brain.gate.abstain`), so a refusal shown again tells its reader nothing they could not
have been told by any other question.

**A follow-up is asked with the person's own earlier questions, and never with an answer's
words (M9.2.3).** `brain.chat.threads.as_turns` keeps a question's words and an answer's
references only, which is `brain.chat.turns`' rule that retained context carries no reach. The
person typed every question, so carrying them discloses nothing; an answer is read again only
through the gate, at the reach held now. See `CONTEXT_IS_THE_PERSONS_OWN_QUESTIONS`.

**And only to the model step, never to the fast path.** A rule matches wording, so an earlier
question inside a follow-up could make the fast path answer the earlier question again. The
context is added only when neither the follow-up alone nor the follow-up with its context matches
any rule, which is `brain.gate.answer.no_rule_matches` asked twice, so the lane hands it to the
model and nothing else. See `CONTEXT_NEVER_REACHES_THE_FAST_PATH`.

**A chat message continues the thread its person was last in, if that was recent (M9.1.2).** The
web names a thread by its id. A chat has nowhere to put one: a direct message is one running
exchange. So a chat message continues the person's most recently active thread, whichever app it
was active in, when its last message is within `CHAT_CONTINUES_WITHIN`, and otherwise starts a new
one. See `A_CHAT_CONTINUES_THE_THREAD_THE_PERSON_WAS_LAST_IN`.

Rejected: one thread per chat. It is the channel-on-the-conversation split `brain.tables.chat`
refuses, arrived at by the back door: a question asked on the web and followed up on a phone
would be two threads, and the follow-up would have no context.

Rejected: carrying the record identifiers a thread drew on into the question. A passage search
reads words, and an identifier the reader still holds gives it nothing to search by; the
references are what `brain.chat.threads.may_show` re-checks when the thread is shown again.

Scope: domain logic. Nothing here opens a connection or reads a clock; `now` is a parameter.

Task ids: M9.1.2, M9.2.1, M9.2.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import ValidationError

from brain.chat.threads import Thread, as_turns, refs_as_json
from brain.chat.turns import CONTEXT_DEPTH, RecordRef, TurnKind
from brain.core.redaction import ENTITY_KEYS, ID_KEYS, ChannelPayload
from brain.gate.answer import Answered
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.streaming import Event
from brain.knowledge.rows import entity_capability
from brain.tables.chat import TITLE_CHARS

# ------------------------------------------------------------------ written-down reasons
#: Why a chat message continues the person's latest thread and not a thread of its own.
A_CHAT_CONTINUES_THE_THREAD_THE_PERSON_WAS_LAST_IN: Final = (
    "The web names a thread by its id and a chat has nowhere to put one. So a chat message "
    "continues the thread its person was most recently active in, on any app, when that was "
    "within the window, and starts a new one otherwise. The thread is found by its owner, so the "
    "worst a wrong guess does is carry the person's own earlier questions into their own "
    "follow-up; a thread per chat would split a question asked on the web from its follow-up on "
    "a phone, which is the split brain.tables.chat refuses."
)

#: Why a follow-up carries the person's questions and nothing an answer said.
CONTEXT_IS_THE_PERSONS_OWN_QUESTIONS: Final = (
    "A follow-up is asked with the earlier questions of its thread, which the person typed and "
    "which needed no grant to know. An answer's words are never carried: they were computed at "
    "the reach held then, and a model told them now would answer from a grant that may be gone. "
    "What an answer drew on is read again only through the gate, at the reach held now."
)

#: Why the context is added only where the model step will read it.
CONTEXT_NEVER_REACHES_THE_FAST_PATH: Final = (
    "A fast-path rule matches wording. An earlier question carried inside a follow-up can match "
    "a rule the follow-up does not, and the fast path would then answer the earlier question "
    "again under the new one. So the context is added only when neither the follow-up nor the "
    "follow-up with its context matches any rule, and the lane hands it to the model alone."
)

#: Why an answer whose sources cannot be named is filed as unreadable.
AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_FILED_AS_UNREADABLE: Final = (
    "A stored answer is shown again only when every record it drew on is still held. A cache "
    "hit carries no payload and a record with no entity or id cannot be re-checked, and filing "
    "either as an empty list would say the answer drew on nothing and show it to its reader "
    "whatever they have lost since. Filed as unreadable, the answer is withheld and the question "
    "beside it is still shown."
)

#: How long after a thread's last message a chat message still continues it.
#:
#: Half an hour. Long enough to read an answer on the web and follow it up from a phone on the
#: way to a meeting; short enough that the next morning's first question starts a thread of its
#: own rather than inheriting yesterday's questions as context.
CHAT_CONTINUES_WITHIN: Final = timedelta(minutes=30)

#: What `chat.message.refs` holds for an answer whose sources cannot be named. Read by
#: `brain.chat.threads.refs_from_json` as unreadable, because the entry is not a reference.
UNKNOWN_REFERENCES: Final[tuple[None, ...]] = (None,)

#: The words a follow-up's earlier questions are introduced with, in the asker's own voice.
EARLIER_HEADING: Final = "Earlier in this conversation I asked:"

#: What a title that had to be shortened ends with.
SHORTENED: Final = "..."


# ------------------------------------------------------------------ what was shown
def frame_events(frames: Sequence[str]) -> list[tuple[str, str]]:
    """Each frame's event name and data, by the event-stream format's own rules.

    The one reader of the lane's frames on the server: `brain.chat_answer` reads a chat reply
    through it and this module reads what to file.
    """
    found: list[tuple[str, str]] = []
    for frame in frames:
        name, data = "", []
        for line in frame.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if key == "event":
                name = value
            elif key == "data":
                data.append(value)
        if name:
            found.append((name, "\n".join(data)))
    return found


def shown_text(answered: Answered) -> str:
    """The words the asker was shown: the answer's prose, or the failure a frame carried."""
    prose: list[str] = []
    for name, data in frame_events(answered.frames):
        if name == Event.ERROR.value:
            return data
        if name == Event.TEXT.value:
            prose.append(data)
    return "".join(prose).strip()


def _first(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    """The first of these keys holding a non-empty string or number, as a string."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str | int) and str(value).strip():
            return str(value)
    return ""


def payload_refs(payload: ChannelPayload) -> tuple[RecordRef, ...] | None:
    """Every record in a redacted payload as a reference, or None when one cannot be named.

    One unnamed record makes the whole list unknown rather than being skipped, for the reason
    `brain.chat.threads.refs_from_json` gives: an answer re-checked against fewer records than
    it drew on has been re-checked against a smaller question than the one it answered.
    """
    found: list[RecordRef] = []
    for record in payload.records:
        entity, record_id = _first(record, ENTITY_KEYS), _first(record, ID_KEYS)
        if not entity or not record_id:
            return None
        try:
            required = entity_capability(entity)
        except ValidationError:
            return None
        found.append(RecordRef(entity=entity, record_id=record_id, required=required))
    return tuple(found)


def refs_of(answered: Answered) -> tuple[RecordRef, ...] | None:
    """What an answer drew on, None when that cannot be said. See the module docstring."""
    if answered.composed is not None:
        return payload_refs(answered.composed.payload)
    if answered.from_cache:
        return None
    return ()


def refs_column(refs: Sequence[RecordRef] | None) -> list[object]:
    """`chat.message.refs` for these references, or the unreadable marker for None."""
    if refs is None:
        return list(UNKNOWN_REFERENCES)
    return list(refs_as_json(refs))


def title_of(question: str) -> str:
    """A conversation's title: its first question, shortened to fit when it must."""
    said = " ".join(question.split())
    if len(said) <= TITLE_CHARS:
        return said
    return said[: TITLE_CHARS - len(SHORTENED)].rstrip() + SHORTENED


# ------------------------------------------------------------------ what a follow-up carries
def continues(last_at: datetime, now: datetime) -> bool:
    """Whether a chat message at `now` continues a thread last active at `last_at`.

    No lower bound: `last_at` is the database's clock and `now` the application's, and a thread
    the database says was used a moment after `now` was used a moment ago.
    """
    return now - last_at <= CHAT_CONTINUES_WITHIN


def earlier_questions(thread: Thread | None, *, depth: int = CONTEXT_DEPTH) -> tuple[str, ...]:
    """The person's own questions among the thread's last `depth` turns, oldest first.

    Through `as_turns`, so an answer contributes its references and no words, and a system note
    contributes nothing. None and an empty thread carry nothing: the context dies with the thread.
    """
    if thread is None:
        return ()
    turns = as_turns(thread)[-depth:]
    return tuple(one.text for one in turns if one.kind is TurnKind.QUESTION and one.text.strip())


def in_context(follow_up: str, earlier: Sequence[str]) -> str:
    """The follow-up, then the earlier questions it follows, within what one question may be.

    The oldest are dropped first when they do not all fit, since the most recent question is the
    one a follow-up most likely leans on. A question repeated as the follow-up is not carried
    twice. With nothing that fits, the follow-up alone.
    """
    asked = [one for one in earlier if one.strip() and one.strip() != follow_up.strip()]
    while asked:
        lines = "\n".join(f"- {' '.join(one.split())}" for one in asked)
        framed = f"{follow_up}\n\n{EARLIER_HEADING}\n{lines}"
        if len(framed) <= MAX_QUESTION_CHARS:
            return framed
        asked = asked[1:]
    return follow_up
