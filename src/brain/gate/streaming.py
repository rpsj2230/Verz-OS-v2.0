"""How an answer reaches a person while it is still being made, and what must not go with it.

Everything else in `brain.gate` decides what an answer may contain. This decides what the
person watching it arrive is told in the meantime, which is a permission surface of its own
and a quieter one: a progress step is not the answer, so nobody reviews it, and it is emitted
before any redaction has happened because the whole point of it is to arrive early.

**A progress step is the one thing in this system that describes work rather than results.**
"Searching Freshdesk for tickets on project 4471" is a useful label and it discloses, to
somebody who may not reach Freshdesk at all, that this installation runs Freshdesk, that
projects are numbered, and that theirs was one of eleven the search covered. None of that is
in the answer. All of it is in the label, and the label is on screen for the second and a
half that the answer takes. `brain.api_routes` refuses to let an installation's shape be
enumerated one entity name at a time; a step label built from a tool input hands the same map
over while the caller waits.

So the labels are a closed vocabulary of six sentences and nothing here can build a seventh.
`step_label` takes a `Progress` member and no tool, no entity, no filter and no count, which
is the enforcement: a function with nowhere to put the tool input cannot leak it. The
vocabulary itself is checked for any digit, because every number that could appear in a
progress label is a count of something the reader was not shown, and for the name of any
source, which the caller supplies: nothing in `brain.gate` may import `brain.connectors`, so
this module cannot know what the sources are, and a module that cannot know them cannot name
one. `tests/unit/test_streaming.py` reads the package and passes the names in, so the check
fails on the commit that adds a connector whose name somebody put in a label.

**Reasoning is never streamed, and the vocabulary is where that is enforced** (M6.3.5). A
model's intermediate reasoning is the one text in this system that has been through no
redaction at all: it quotes what was fetched before the field policy ran, names the tools it
considered, and reasons out loud about what it could not see, which is the "DENIED and ABSENT
are indistinguishable" rule broken in the most direct way available. `Event` has five members
and a sixth for reasoning is the thing this module exists to prevent; `encode` accepts an
`Event` rather than a string, so there is no way to emit an event name that is not one of the
five, and no member to add one under without a test failing.

**Citations arrive before the prose they support** (M6.3.4). A reader reads prose as it
lands and has decided whether to believe it by the time the last token arrives; citations
appended afterwards are read by nobody. The order is not a convention here, it is a state
machine: `AnswerStream` refuses a citation once any prose has gone out, and refuses everything
once the stream is closed. The rejected alternative was sorting a buffered list at the end,
which produces the right order and defeats the purpose, because the point of streaming is that
the reader sees the first thing before the last thing exists.

**A cache hit is one step and then the answer** (M6.3.6). Replaying the working steps for an
answer that was already computed is a progress bar for work that is not happening, and it
trains a reader to read the steps as decoration. `cache_hit` emits a single step saying the
answer is instant and why, then the text, then done, and it takes a `ServedAnswer` rather than
a string so it cannot be called with an answer that has not had its age put into it by
`brain.gate.answer_cache.serve_cached`.

**A data value containing a blank line ends the event.** This is the bug the encoder exists
to prevent and it is not hypothetical here: `answer_cache.AGE_SEPARATOR` is exactly two
newlines, so every cached answer in this system carries a blank line between the answer and
the sentence saying how old it is. `data: {text}` written the obvious way delivers the answer
and silently drops the age, which is precisely the omission `AgeNotSurfacedError` exists to
make impossible, arriving through the transport instead. `encode` splits on every line
terminator the specification recognises, carriage return included, because this repository
writes CRLF by accident often enough to have a note about it in `CLAUDE.md`.

**No event carries an id, and that is a decision rather than an omission.** An SSE id is a
resumption token: a client reconnecting with `Last-Event-ID` asks the server to replay from
there, and a server that obliges has made knowing a string sufficient to be served somebody
else's answer. It is the argument `brain.gate.compose.ComposedAnswer` makes about `trace_ref`,
one layer down, and the answer is the same one: `encode` has no parameter for an id and
`stream_gaps` fails if one appears.

Scope: domain logic. Nothing here opens a connection, reads a clock or calls a model. The
frames are strings; who writes them to a socket is somebody else's problem, for the reason
`brain.ops.limits` gives about policy that owns a client being untestable at its boundary.

**Not yet wired to a route.** There is no answer-lane endpoint in `brain.api_routes` to stream
from, because `brain.gate.fast_lane.respond` and `brain.gate.compose.compose` are both
reachable from no route today. `tests/unit/test_streaming.py` asserts that gap rather than
leaving it to a docstring, so the day somebody builds the endpoint the test tells them this
half is already here.

Task ids: M6.3.1, M6.3.2, M6.3.3, M6.3.4, M6.3.5, M6.3.6
"""

from __future__ import annotations

import enum
import inspect
import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

from brain.gate.answer_cache import ServedAnswer
from brain.gate.compose import Citation

#: Why there is no reasoning event and no room to add one.
REASONING_IS_NOT_A_CHANNEL_EVENT: Final = (
    "A model's intermediate reasoning is the one text in this system that has been through "
    "no redaction. It quotes what was fetched before the field policy ran, names the tools "
    "it considered, and reasons out loud about what it could not find, which tells a reader "
    "exactly which things exist that they may not see. Event has five members and a sixth "
    "for reasoning is what this vocabulary exists to refuse; encode takes an Event rather "
    "than a string so no name outside the five can be put on the wire."
)

#: Why a step label is never built from the thing the step is about.
A_LABEL_BUILT_FROM_A_TOOL_INPUT_DESCRIBES_THE_CALLERS_SCOPE: Final = (
    "A progress step is the one thing here that describes work rather than results, so it "
    "is written before any redaction has run and read by somebody who is waiting. A label "
    "naming the source discloses which connectors this installation runs; a label carrying "
    "a figure discloses a count of things the reader was not shown; a label naming the "
    "entity discloses that the entity exists. step_label takes a Progress member and has "
    "nowhere to put a tool, an entity, a filter or a count, which is the enforcement."
)

#: Why the order of the two is not a matter of taste.
A_CITATION_AFTER_THE_PROSE_IS_A_CITATION_NOBODY_READ: Final = (
    "A reader reads prose as it lands and has decided whether to believe it before the last "
    "token arrives. Citations appended afterwards are read by nobody, which leaves an "
    "answer that looks sourced and is taken on trust. Buffering and sorting at the end "
    "produces the right order and defeats the point of streaming, so the order is a state "
    "machine: once any prose has gone out, a citation is refused rather than reordered."
)

#: Why the encoder splits a data value rather than interpolating it.
A_BLANK_LINE_IN_A_DATA_VALUE_ENDS_THE_EVENT: Final = (
    "A blank line terminates an event, so an f-string of the form 'data: {text}' delivers "
    "everything up to the first blank line and drops the rest without erroring. In this "
    "system that is not a corner case: answer_cache.AGE_SEPARATOR is two newlines, so every "
    "cached answer has a blank line between the answer and the sentence saying how old it "
    "is, and the obvious encoder drops exactly the sentence AgeNotSurfacedError exists to "
    "guarantee. Carriage returns are line terminators too, and this repository writes CRLF "
    "by accident often enough to have a note about it in CLAUDE.md."
)

#: Why no frame carries an id.
AN_EVENT_ID_IS_A_REQUEST_TO_REPLAY: Final = (
    "A client reconnecting with Last-Event-ID asks the server to replay from that point, so "
    "a server that honours ids has made knowing a string sufficient to be served somebody "
    "else's answer. It is the argument ComposedAnswer makes about trace_ref one layer down: "
    "the reference says which, and entitlement says who. encode has no parameter for an id."
)

#: Why a cache hit does not replay the working steps.
A_CACHE_HIT_IS_ONE_STEP_AND_THEN_THE_ANSWER: Final = (
    "Replaying 'looking it up' for an answer that was computed a quarter of an hour ago is "
    "a progress bar for work that is not happening, and a reader who notices stops reading "
    "the steps at all. One step, saying the answer is instant and why, is the honest render "
    "and it is also the useful one: the reason is what tells somebody whether to ask again."
)


class Event(enum.StrEnum):
    """Every event name that may go on the wire. Five members, and the sixth is the point.

    There is no member for reasoning, no member for a tool call's arguments and no member for
    a plan. `encode` takes this type rather than a string, so the vocabulary is the whole of
    what can be emitted, and widening it is an edit somebody has to make deliberately in front
    of a test that names what the widening would cost.
    """

    #: A named progress step, in user language, from the closed label vocabulary.
    STEP = "step"
    #: One record and field standing behind a claim. Always before any prose.
    CITATION = "citation"
    #: A chunk of the answer itself.
    TEXT = "text"
    #: The answer is complete. Nothing follows.
    DONE = "done"
    #: The answer failed. Carries the sentence a person is shown, never a diagnostic.
    ERROR = "error"


class Progress(enum.StrEnum):
    """The points in a request at which a person is told something is happening.

    Coarse on purpose. A finer vocabulary would have to distinguish steps by what they were
    doing, and what they were doing is the caller's scope: two tool calls that differ only in
    which connector they reached would produce two different labels, and the difference is the
    disclosure.
    """

    #: The question has been received and is being read.
    UNDERSTANDING = "understanding"
    #: Reach is being resolved and narrowed.
    CHECKING = "checking"
    #: A tool input has started. One member for every tool, deliberately.
    LOOKING_UP = "looking_up"
    #: What came back is being read.
    READING = "reading"
    #: The answer is being assembled from what survived.
    COMPOSING = "composing"
    #: The answer was already computed. Emitted alone, never after the others.
    CACHED = "cached"


#: What a person reads for each step. Six sentences, no numbers, no source names, no entities.
STEP_LABELS: Final[Mapping[Progress, str]] = MappingProxyType(
    {
        Progress.UNDERSTANDING: "Reading your question",
        Progress.CHECKING: "Checking what you are able to see",
        Progress.LOOKING_UP: "Looking it up",
        Progress.READING: "Reading what came back",
        Progress.COMPOSING: "Putting the answer together",
        Progress.CACHED: "Answered instantly, because this was asked a moment ago",
    }
)

#: How often a comment frame goes out on an otherwise idle stream.
#:
#: A stream that sends nothing looks to every proxy in the path like a connection nobody is
#: using, and the answer lane's slowest step is a model call with nothing to report while it
#: runs. The figure is not the interesting part; the relationship below is.
HEARTBEAT_SECONDS: Final = 10

#: The most aggressive idle timeout assumed to be in the path.
#:
#: Unmeasured against the deployed proxy, and said so rather than presented as a finding: the
#: streaming lane has no route yet, so there is nothing deployed to measure it against. What
#: is enforced is that two heartbeats fit inside it, so one dropped frame does not close a
#: live stream, and that relationship is what `stream_gaps` checks.
SHORTEST_IDLE_TIMEOUT_SECONDS: Final = 30

#: Field separator within a frame, and the blank line that ends one.
FIELD_END: Final = "\n"
FRAME_END: Final = "\n\n"

#: Every line terminator the event-stream format recognises, longest first so CRLF is one
#: break rather than two.
_TERMINATORS: Final = ("\r\n", "\r", "\n")

_WORD = re.compile(r"[a-z0-9_]+")


class StreamOrderError(Exception):
    """Raised when a frame is emitted at a point in the stream where it means something else.

    A programming error, and deliberately not a `BrainError`: the taxonomy in
    `brain.core.errors` describes outcomes a person is shown, and a citation emitted after
    the prose is a bug in the caller rather than something to render.
    """


def forbidden_words(sources: Iterable[str]) -> frozenset[str]:
    """Source names as the words a label must not contain, including their parts.

    The parts count separately because a person writing a label writes "Google Drive" and the
    name it came from is `google_drive`, so matching the name alone catches the label nobody
    would write and misses the one somebody would. That over-includes, in the direction that
    costs nothing: the vocabulary is six fixed sentences and none of them wants to say "drive".

    A function taking the names rather than a constant holding them, because of what this
    module may not know. See `scope_revealing`.
    """
    names = [one.casefold() for one in sources]
    return frozenset(names) | {part for one in names for part in one.split("_")}


def scope_revealing(label: str, sources: Iterable[str] = ()) -> tuple[str, ...]:
    """Everything in a label that describes the caller's scope rather than the work.

    Two checks, and they are supplied differently on purpose.

    A digit is checked here unconditionally, because every number that could appear in a
    progress label is a count of something: records found, sources searched, documents read,
    each a fact about what exists that the reader has not been shown.

    **A source's name is checked against a list the caller supplies, because this module may
    not know what the sources are.** `tests/unit/test_repo_shape.py` enforces that nothing in
    `brain.gate` imports `brain.connectors`, and the argument is the architecture: the gate
    decides what a caller may see and a connector fetches it, so a gate that imported one
    would be deciding and fetching, and the seam where every permission decision happens would
    stop being a seam. Reading the package to build a deny list is that import wearing a hat.

    What the rule leaves is a better statement than the one it took away. A label here cannot
    name a source because this module does not know any source names, which holds for sources
    added after this file was written and for sources nobody has thought of. The list is
    passed in by `tests/unit/test_streaming.py`, which may read the package, and it fails on
    the commit that adds a connector whose name somebody put in a label.

    Returns findings rather than raising, so `stream_gaps` can report the whole vocabulary at
    once and a reviewer sees every offending label instead of the first.
    """
    findings: list[str] = []

    if any(character.isdigit() for character in label):
        findings.append(
            f"the label {label!r} carries a figure, and every number that fits in a progress "
            "label is a count of something the reader was not shown"
        )

    words = set(_WORD.findall(label.casefold()))
    for source in sorted(words & forbidden_words(sources)):
        findings.append(
            f"the label {label!r} names {source}, which tells a reader who may not reach it "
            "that this installation runs it"
        )

    return tuple(findings)


def step_label(step: Progress) -> str:
    """What a person reads for one step.

    **The signature is the guard.** There is no parameter for the tool, the entity, the filter
    or the count, so a label cannot be built from the thing the step is about, and the check
    in `scope_revealing` only has six fixed sentences to police rather than every string a
    caller might interpolate. See `A_LABEL_BUILT_FROM_A_TOOL_INPUT_DESCRIBES_THE_CALLERS_SCOPE`.
    """
    return STEP_LABELS[step]


def at_tool_input_start() -> Progress:
    """The step emitted when a tool input starts (M6.3.2). One member for every tool.

    A function taking nothing rather than a mapping from tool to step, because a mapping is a
    thing somebody fills in: the moment two tools have two labels, the label says which tool
    ran, and which tool ran says which source this installation has and which one the caller's
    question reached. Taking no argument makes that edit impossible rather than discouraged.
    """
    return Progress.LOOKING_UP


def _lines(value: str) -> tuple[str, ...]:
    """One data value split on every line terminator the format recognises.

    CRLF first, so a Windows-authored string is one break rather than a break and an empty
    line. See `A_BLANK_LINE_IN_A_DATA_VALUE_ENDS_THE_EVENT`.
    """
    normalised = value
    for terminator in _TERMINATORS[:-1]:
        normalised = normalised.replace(terminator, "\n")
    return tuple(normalised.split("\n"))


def encode(event: Event, data: str) -> str:
    """One frame, ready to write to a socket.

    Takes an `Event` rather than a name, so the vocabulary is the whole of what can be
    emitted. Takes no id, because an id is a resumption token and knowing a string must not be
    a way to be served somebody else's answer: see `AN_EVENT_ID_IS_A_REQUEST_TO_REPLAY`.

    Every line of the value gets its own `data:` field. A receiver joins them with a single
    newline, so a value's blank lines survive the transport, which is the whole reason this
    function exists rather than an f-string at the call site.
    """
    fields = [f"event: {event.value}"]
    fields.extend(f"data: {line}" for line in _lines(data))
    return FIELD_END.join(fields) + FRAME_END


def heartbeat(note: str = "still working") -> str:
    """A comment frame, which a receiver ignores and a proxy counts as traffic.

    The note is a fixed phrase rather than anything about the request, for the reason every
    step label is: this is a string that goes out before redaction has run.
    """
    return f": {_lines(note)[0]}" + FRAME_END


class Phase(enum.IntEnum):
    """Where a stream is. Ordered, because every transition this type allows goes forward."""

    OPENING = 0
    CITING = 1
    PROSE = 2
    CLOSED = 3


class AnswerStream:
    """The order of an answer's frames, enforced rather than documented.

    Steps and citations may go out until prose starts. Once prose starts, citations are
    refused, because a citation the reader has already scrolled past is one they did not read
    and the answer is left looking sourced. Once the stream is closed, everything is refused,
    because a frame after `done` arrives in a client that has stopped listening and is
    therefore a silent loss rather than an error.

    Not an iterator and not a generator: each method returns one frame and the caller decides
    what to do with it. A generator would own the loop, and the loop is where the model call,
    the timeout and the disconnect live, none of which belong in a module that must be
    testable without a socket.
    """

    def __init__(self) -> None:
        self.phase = Phase.OPENING

    def _refuse(self, what: str, because: str) -> None:
        msg = f"a {what} cannot go out {because} (phase {self.phase.name})"
        raise StreamOrderError(msg)

    def step(self, step: Progress) -> str:
        """A progress step. Allowed until the prose starts and not after it.

        A step emitted after the answer has begun describes work done to produce text the
        reader has already read, which in this pipeline means the caller has interleaved two
        phases that do not interleave. Refusing loudly is better than a progress bar that
        moves backwards.
        """
        if self.phase >= Phase.PROSE:
            self._refuse("step", "once the answer itself has started")
        return encode(Event.STEP, step_label(step))

    def citation(self, one: Citation) -> str:
        """One citation. Allowed before any prose and refused after it.

        Takes a `Citation` rather than a rendered string, so what goes out is the type that
        already refuses to carry a field's value.
        """
        if self.phase >= Phase.PROSE:
            self._refuse("citation", "once the prose it supports has started")
        self.phase = Phase.CITING
        return encode(Event.CITATION, one.render())

    def text(self, chunk: str) -> str:
        """A chunk of the answer. The first one closes the citation window."""
        if self.phase is Phase.CLOSED:
            self._refuse("chunk of answer", "after the stream has been closed")
        self.phase = Phase.PROSE
        return encode(Event.TEXT, chunk)

    def done(self) -> str:
        """The answer is complete. Nothing may follow."""
        if self.phase is Phase.CLOSED:
            self._refuse("completion", "twice")
        self.phase = Phase.CLOSED
        return encode(Event.DONE, "")

    def error(self, shown: str) -> str:
        """The answer failed, carrying the sentence a person is shown.

        Whatever the caller passes reaches a screen, so it is the rendered outcome from
        `brain.core.errors` and never a diagnostic. This module cannot enforce that and says
        so rather than implying a check it does not make.
        """
        if self.phase is Phase.CLOSED:
            self._refuse("failure", "after the stream has been closed")
        self.phase = Phase.CLOSED
        return encode(Event.ERROR, shown)


def cache_hit(served: ServedAnswer) -> tuple[str, ...]:
    """Every frame for an answer that was already computed (M6.3.6).

    One step saying it is instant and why, the answer, and done. No working steps, for the
    reason `A_CACHE_HIT_IS_ONE_STEP_AND_THEN_THE_ANSWER` gives.

    Takes a `ServedAnswer` rather than a string, so it cannot be called with a payload that
    has not been through `serve_cached` and therefore cannot serve a cached answer without the
    sentence saying how old it is. That sentence sits after a blank line, which is exactly
    what `encode` is careful about.
    """
    if not served.from_cache:
        msg = (
            "a freshly computed answer is not a cache hit; rendering one as instant would "
            "tell a reader the system did not look, when it did"
        )
        raise StreamOrderError(msg)

    stream = AnswerStream()
    return (
        stream.step(Progress.CACHED),
        stream.text(served.text),
        stream.done(),
    )


def frames(parts: Iterable[str]) -> str:
    """Several frames as one string, for a caller writing them in a single body.

    Concatenation rather than a join, because each frame already ends in the blank line that
    terminates it. A separator would put a second blank line at every boundary, and the
    honest note is that a conforming receiver ignores it: a blank line with nothing in the
    buffer dispatches nothing, so this is a mutation the tests do not catch and should not
    pretend to. What it costs is bytes on every frame of every answer, and a raw stream that
    nobody debugging one can read.
    """
    return "".join(parts)


def stream_gaps(sources: Iterable[str] = ()) -> tuple[str, ...]:
    """Everything about this module that would let something reach a person that should not.

    Five checks, and every one of them is a property that no other test in the file would
    notice on its own: a reasoning member added to the vocabulary, an id parameter added to
    the encoder, a label added without one, a label that describes scope, and a heartbeat that
    does not fit inside the timeout it exists to beat.
    """
    gaps: list[str] = []

    names = {member.name for member in Event}
    for forbidden in ("REASONING", "THINKING", "PLAN", "TOOL_INPUT", "SCRATCHPAD"):
        if forbidden in names:
            gaps.append(
                f"Event has a {forbidden} member, so text that has been through no "
                "redaction has a name to travel under"
            )

    taken = set(inspect.signature(encode).parameters)
    for forbidden in ("event_id", "id", "last_event_id", "retry"):
        if forbidden in taken:
            gaps.append(
                f"encode takes {forbidden}, so a frame carries a resumption token and "
                "knowing a string becomes a way to be served somebody else's answer"
            )

    for step in Progress:
        if step not in STEP_LABELS:
            gaps.append(f"{step.value} has no label, so a step reaches a person as a key")

    for label in STEP_LABELS.values():
        gaps.extend(scope_revealing(label, sources))

    if HEARTBEAT_SECONDS * 2 > SHORTEST_IDLE_TIMEOUT_SECONDS:
        gaps.append(
            f"a heartbeat every {HEARTBEAT_SECONDS}s does not fit twice inside a "
            f"{SHORTEST_IDLE_TIMEOUT_SECONDS}s idle timeout, so one dropped frame closes a "
            "live stream"
        )

    return tuple(gaps)
