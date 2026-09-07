"""The answer stream, held to what must not travel on it and what must not be lost by it.

Two kinds of test here and they fail differently. The permission ones say what may not reach
a person watching an answer arrive: no reasoning, no source name in a progress label, no
figure that is a count of something withheld, no resumption token. The transport ones say
what must not be lost on the way, and the one that matters is the blank line: this system puts
two newlines between a cached answer and the sentence saying how old it is, and a blank line
ends an event, so the obvious encoder delivers the answer and silently drops the disclosure
that `AgeNotSurfacedError` exists to guarantee.

**The decoder below is written from the event-stream specification, not from `encode`.** A
test that decoded by inverting the encoder would agree with the encoder about a shared
mistake, which is the failure `CLAUDE.md` describes as a test that builds the value the
function under test produces. What is implemented here is the specification's own algorithm:
split on any line terminator, a blank line dispatches, a leading colon is a comment, a field
is the text before the first colon with one optional space removed after it, and `data` lines
are joined with a newline.

Task ids: M6.3.1, M6.3.2, M6.3.3, M6.3.4, M6.3.5, M6.3.6
"""

from __future__ import annotations

import inspect
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

import brain.connectors
from brain.gate import streaming
from brain.gate.answer_cache import AGE_MARKER, serve_cached, serve_fresh
from brain.gate.cache_key import CachedAnswer
from brain.gate.compose import Citation
from brain.gate.streaming import (
    HEARTBEAT_SECONDS,
    SHORTEST_IDLE_TIMEOUT_SECONDS,
    STEP_LABELS,
    AnswerStream,
    Event,
    Progress,
    StreamOrderError,
    at_tool_input_start,
    cache_hit,
    encode,
    frames,
    heartbeat,
    scope_revealing,
    step_label,
    stream_gaps,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def sources() -> tuple[str, ...]:
    """Every source name this installation runs, read from the package.

    Read here rather than in `brain.gate.streaming` because nothing in the gate may import
    `brain.connectors`: the gate decides what a caller may see and a connector fetches it, and
    a gate that imported one would be deciding and fetching. `test_repo_shape` enforces that.
    A test is under no such rule, which is why the list is assembled on this side and passed
    in, and it is assembled from the package rather than written out so that a connector added
    next month is covered on the commit that adds it.
    """
    return tuple(module.name for module in pkgutil.iter_modules(brain.connectors.__path__))


@dataclass(frozen=True)
class Decoded:
    """One dispatched event, as a receiver would have it."""

    event: str
    data: str


def decode(body: str) -> tuple[Decoded, ...]:
    """An event stream, parsed by the specification's algorithm rather than by inverting `encode`.

    Deliberately written from the format's own rules so that a mistake shared with the encoder
    cannot cancel out. A blank line dispatches; a line beginning with a colon is a comment and
    is ignored; otherwise the field name is the text before the first colon, the value is what
    follows with a single leading space removed, and a line with no colon is a field with an
    empty value. `data` values accumulate, joined by a newline, and the buffer is dropped when
    an event dispatches with nothing in it.
    """
    out: list[Decoded] = []
    name = ""
    data: list[str] = []

    normalised = body.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalised.split("\n"):
        if line == "":
            if data or name:
                out.append(Decoded(event=name or "message", data="\n".join(data)))
            name, data = "", []
            continue
        if line.startswith(":"):
            continue
        field, _, raw = line.partition(":")
        value = raw[1:] if raw.startswith(" ") else raw
        if field == "event":
            name = value
        elif field == "data":
            data.append(value)

    return tuple(out)


def cached(payload: str, *, minutes: int) -> CachedAnswer:
    return CachedAnswer(
        key="k",
        payload=payload,
        stored_at=NOW - timedelta(minutes=minutes),
        source_epochs={},
    )


def citation(field: str = "hours_remaining") -> Citation:
    return Citation(
        entity="block",
        record_id="b_1",
        field=field,
        source="",
        fetched_at="",
    )


# --- what must not be lost on the way -----------------------------------------------------


def test_a_cached_answer_reaches_a_person_still_saying_how_old_it_is() -> None:
    """**The bug this encoder exists to prevent, in the exact shape it occurs here.**

    `answer_cache.AGE_SEPARATOR` is two newlines, so every cached answer in this system has a
    blank line between the answer and the sentence saying how old it is. A blank line ends an
    event, so `data: {text}` written the obvious way delivers the answer, drops the age, and
    raises nothing: the reader is told a quarter-of-an-hour-old figure as though the system
    had just looked, which is precisely what `AgeNotSurfacedError` is there to make
    impossible, arriving through the transport where that guard cannot see it.

    Asserted after decoding rather than by searching the wire bytes, because the property is
    about what the receiver ends up with.

    Delete this and the encoder can go back to one `data:` line, which passes every other test
    in this file and quietly removes the disclosure from every cached answer."""
    served = serve_cached(cached("SNM has 12 hours left on the block.", minutes=14), NOW)
    assert AGE_MARKER in served.text

    events = decode(frames(cache_hit(served)))
    text = next(one.data for one in events if one.event == Event.TEXT.value)

    assert text == served.text
    assert AGE_MARKER in text
    assert "14 minutes ago" in text


def test_a_blank_line_inside_an_answer_survives_the_transport() -> None:
    """The general form of the case above: an answer with a paragraph break is an ordinary
    answer, and a paragraph break is a blank line.

    Delete this and a multi-paragraph answer arrives truncated at its first paragraph, which
    reads as the model having stopped early rather than as a transport bug."""
    body = "First paragraph.\n\nSecond paragraph.\n\n\nThird, after two blank lines."

    events = decode(encode(Event.TEXT, body))

    assert len(events) == 1
    assert events[0].data == body


def test_a_carriage_return_does_not_split_one_answer_into_two_events() -> None:
    """`CLAUDE.md` records that Python on this machine writes CRLF without being asked, and
    the event-stream format treats a bare carriage return as a line terminator in its own
    right. An answer assembled from a file read on this machine therefore carries terminators
    the naive splitter does not know about.

    Both spellings, because CRLF handled as two breaks produces an empty data line, which
    decodes as a blank line the author never wrote.

    Delete this and an answer that passed through a Windows file arrives with a blank line
    between every sentence."""
    for body in ("Line one\r\nLine two", "Line one\rLine two"):
        events = decode(encode(Event.TEXT, body))

        assert len(events) == 1, body
        assert events[0].data == "Line one\nLine two", body


def test_a_heartbeat_is_a_comment_the_receiver_does_not_dispatch() -> None:
    """A stream that sends nothing looks to every proxy in the path like a connection nobody
    is using, and the answer lane's slowest step reports nothing while it runs. A comment is
    traffic to a proxy and nothing to a receiver.

    Delete this and the heartbeat is written as an event, which either appears in the answer
    or has to be filtered out by every client."""
    assert decode(heartbeat()) == ()
    assert heartbeat().startswith(":")


def test_two_heartbeats_fit_inside_the_timeout_the_heartbeat_exists_to_beat() -> None:
    """The relationship rather than the figure. A heartbeat that fits exactly once means a
    single dropped frame closes a live stream, and a stream closing mid-answer looks to a
    reader like the system giving up on their question.

    Anchored to the timeout constant rather than asserting the interval against itself, which
    would be green for every value the interval could hold.

    Delete this and somebody raises the interval to reduce chatter and reintroduces the
    disconnect that the heartbeat was added for."""
    assert HEARTBEAT_SECONDS * 2 <= SHORTEST_IDLE_TIMEOUT_SECONDS
    assert HEARTBEAT_SECONDS > 0


def test_several_frames_written_as_one_body_decode_to_one_event_each() -> None:
    """Frames are handed to a caller one at a time and often written in a single body, and
    what must hold is that the boundaries survive being run together: three calls in, three
    events out, in the order they were made.

    **This test was named for a claim the format does not support and has been corrected.** It
    used to say that joining the frames with a separator would open an empty event, which a
    mutation disproved: a blank line with nothing in the buffer dispatches nothing, so the
    separator is wasted bytes rather than a spurious event. `frames` says so now.

    Delete this and the assembly loses its only check that a frame boundary is a frame
    boundary, which is the thing a stray `strip()` anywhere in the chain would destroy."""
    stream = AnswerStream()
    body = frames([stream.step(Progress.UNDERSTANDING), stream.text("Yes."), stream.done()])

    events = decode(body)

    assert [one.event for one in events] == [
        Event.STEP.value,
        Event.TEXT.value,
        Event.DONE.value,
    ]


# --- what must not travel -----------------------------------------------------------------


def test_the_event_vocabulary_has_no_name_for_reasoning() -> None:
    """**M6.3.5.** A model's intermediate reasoning is the one text in this system that has
    been through no redaction: it quotes what was fetched before the field policy ran and
    reasons out loud about what it could not find, which is "DENIED and ABSENT are
    indistinguishable" broken in the most direct way available.

    Asserted on the member set rather than on behaviour, because behaviour today says nothing
    about what a member added tomorrow would carry, and it would arrive looking like a
    transparency feature.

    Delete this and a `reasoning` event is added because every other assistant streams one."""
    assert {member.value for member in Event} == {"step", "citation", "text", "done", "error"}

    names = {member.name for member in Event}
    for forbidden in ("REASONING", "THINKING", "PLAN", "TOOL_INPUT", "SCRATCHPAD"):
        assert forbidden not in names, f"Event has a {forbidden} member"


def test_an_event_name_outside_the_vocabulary_cannot_be_put_on_the_wire() -> None:
    """The structural half of the test above. A rule saying "do not emit reasoning" holds
    until somebody has a reason to; an encoder that cannot take a string has no way to.

    Delete this and `encode` grows a `str` parameter for convenience, and the vocabulary stops
    being the whole of what can be emitted."""
    annotation = inspect.signature(encode).parameters["event"].annotation

    assert annotation in (Event, "Event")


def test_a_frame_carries_no_resumption_token() -> None:
    """An event id is what a client sends back as `Last-Event-ID` to ask for a replay, so a
    server that honours ids has made knowing a string sufficient to be served somebody else's
    answer. It is the argument `ComposedAnswer` makes about `trace_ref`: the reference says
    which, entitlement says who.

    Checked on the signature and on the wire, because a parameter defaulting to `None` would
    pass a wire check on every test that did not pass one.

    Delete this and an id is added to support reconnection, which is a genuinely good feature
    and a capability handed to whoever the answer was forwarded to."""
    taken = set(inspect.signature(encode).parameters)
    for forbidden in ("event_id", "id", "last_event_id", "retry"):
        assert forbidden not in taken, f"encode takes {forbidden}"

    assert "id:" not in encode(Event.TEXT, "anything")


def test_a_step_label_cannot_be_built_from_what_the_step_is_about() -> None:
    """**M6.3.3, and the signature is the guard.**

    "Searching Freshdesk for tickets on project 4471" is the label somebody writes when the
    function has the tool input in scope. It tells a reader who may not reach Freshdesk that
    this installation runs it, that projects are numbered, and roughly where theirs sits.
    None of that is in the answer.

    `step_label` takes a `Progress` member and nothing else, and `at_tool_input_start` takes
    nothing at all, so a per-tool label is an edit somebody cannot make by accident.

    Delete this and a `tool` parameter is added to make the labels more helpful, which is
    exactly what it would do."""
    assert list(inspect.signature(step_label).parameters) == ["step"]
    assert list(inspect.signature(at_tool_input_start).parameters) == []

    for forbidden in ("tool", "entity", "filters", "count", "query", "source", "request"):
        assert forbidden not in inspect.signature(step_label).parameters


def test_every_tool_gets_the_same_step_regardless_of_which_one_started() -> None:
    """The positive sibling of the signature check: the step still exists and still says
    something. A guard tested only by what it refuses is satisfied by a function that refuses
    everything.

    Delete this and `at_tool_input_start` can return `None` and the reader watches a spinner
    with no words on it."""
    assert at_tool_input_start() is Progress.LOOKING_UP
    assert step_label(at_tool_input_start()) == "Looking it up"


def test_no_step_label_names_a_source_this_installation_runs() -> None:
    """Which connectors an installation has is as enumerable by watching progress labels as an
    entity list is by guessing names, and `brain.api_routes` goes to some trouble to refuse the
    second.

    The forbidden names are read out of the `brain.connectors` package rather than listed
    here, so a connector added next month is covered by this test on the commit that adds it,
    with nobody having to remember this file exists.

    Delete this and the labels get more informative one connector at a time."""
    for step, label in STEP_LABELS.items():
        assert scope_revealing(label, sources()) == (), f"{step.value}: {label}"


def test_a_label_naming_a_source_in_two_words_is_reported() -> None:
    """**Written because a mutation survived.** The forbidden names come from module names,
    and a module name is `google_drive` while a person writing a label writes "Google Drive".
    Matching only the module name spelling catches the label nobody would write and misses the
    one somebody would.

    The compound name is looked up in the package rather than spelled here, so the test says
    "a source whose module name has two parts" rather than becoming a test about Google.

    Delete this and the parts check goes, and the check survives on exactly the connectors
    whose names are one word."""
    compound = sorted(one for one in sources() if "_" in one)
    assert compound, "no connector module has a compound name for this test to use"

    spoken = compound[0].replace("_", " ").title()
    findings = scope_revealing(f"Searching {spoken} for what you asked about", sources())

    assert findings, spoken
    assert any("this installation runs it" in finding for finding in findings)


def test_a_label_that_names_a_connector_is_reported() -> None:
    """The detector's positive case, without which every assertion above is satisfied by a
    function returning an empty tuple.

    The connector name is taken from the package rather than written here, so this does not
    quietly become a test about the string "hubspot".

    Delete this and `scope_revealing` can return `()` unconditionally with the file green."""
    names = set(sources())
    assert "hubspot" in names, "the package no longer holds the connector this test names"

    findings = scope_revealing("Searching HubSpot for what you asked about", sources())

    assert findings, names
    assert any("this installation runs it" in finding for finding in findings)


def test_a_label_carrying_a_figure_is_reported() -> None:
    """Every number that fits in a progress label is a count of something: records found,
    sources searched, documents read. "Read 3 of 11 documents" is the "showing 3 of 47" leak
    with a progress bar around it.

    Delete this and the count check goes, and the leak arrives as a helpfulness improvement."""
    findings = scope_revealing("Reading 3 of 11 documents", sources())

    assert findings
    assert any("count of something the reader was not shown" in one for one in findings)


def test_a_label_saying_nothing_about_scope_is_not_reported() -> None:
    """The positive sibling. A detector that flagged everything would be satisfied by the
    labels being empty strings.

    Delete this and `scope_revealing` can flag unconditionally, and the next person to add a
    perfectly good label deletes the detector instead."""
    assert scope_revealing("Putting the answer together", sources()) == ()


# --- the order ----------------------------------------------------------------------------


def test_a_citation_cannot_go_out_after_the_prose_it_supports() -> None:
    """**M6.3.4.** A reader reads prose as it lands and has decided whether to believe it
    before the last token arrives. Citations appended afterwards are read by nobody, which
    leaves an answer that looks sourced and is taken on trust.

    Refused rather than reordered, because reordering means buffering to the end, and an
    answer buffered to the end is not a streamed answer.

    Delete this and the citations move to wherever the composition loop happens to produce
    them, which is after the text, because that is when the text is finished."""
    stream = AnswerStream()
    stream.text("SNM has hours left on the block.")

    with pytest.raises(StreamOrderError, match="once the prose it supports has started"):
        stream.citation(citation())


def test_citations_and_steps_go_out_before_the_prose() -> None:
    """The positive sibling, and without it every ordering assertion here is satisfied by a
    stream that refuses everything.

    Asserted on the decoded order rather than on the calls, because the property is what the
    receiver sees.

    Delete this and the state machine can refuse citations outright with the file green."""
    stream = AnswerStream()
    body = frames(
        [
            stream.step(Progress.UNDERSTANDING),
            stream.step(at_tool_input_start()),
            stream.citation(citation()),
            stream.citation(citation("block_id")),
            stream.text("SNM has hours left."),
            stream.done(),
        ]
    )

    seen = [one.event for one in decode(body)]

    assert seen == ["step", "step", "citation", "citation", "text", "done"]
    assert seen.index("citation") < seen.index("text")


def test_a_progress_step_cannot_go_out_once_the_answer_has_started() -> None:
    """A step emitted after the answer has begun describes work done to produce text the
    reader has already read. A progress bar that moves while the answer is being written is a
    progress bar the reader stops trusting.

    Delete this and an interleaved pipeline emits steps into the middle of the prose, where
    they arrive as sentences the model appears to have written."""
    stream = AnswerStream()
    stream.text("Yes.")

    with pytest.raises(StreamOrderError, match="once the answer itself has started"):
        stream.step(Progress.READING)


def test_nothing_goes_out_after_the_stream_is_closed() -> None:
    """A frame written after `done` arrives in a client that has stopped listening, so it is a
    silent loss rather than an error, and the thing lost is whatever the caller thought was
    important enough to send late.

    All four, because a state machine that closes for one kind and not the others is a state
    machine with a hole in it.

    Delete this and a late error frame vanishes, and the request looks to the reader like it
    succeeded."""
    sends: tuple[Callable[[AnswerStream], str], ...] = (
        lambda one: one.text("more"),
        lambda one: one.step(Progress.READING),
        lambda one: one.citation(citation()),
        lambda one: one.done(),
        lambda one: one.error("Something went wrong."),
    )
    for send in sends:
        stream = AnswerStream()
        stream.done()
        with pytest.raises(StreamOrderError):
            send(stream)


def test_an_answer_with_no_citations_can_still_be_streamed() -> None:
    """An abstention is text with nothing behind it, and `brain.gate.abstain` exists precisely
    so the system can say "I cannot answer that" honestly. A state machine requiring a
    citation before any prose would make the honest answer unsendable.

    Delete this and the abstention path cannot use this module, so it grows its own writer."""
    stream = AnswerStream()

    body = frames([stream.text("I cannot answer that from what I can reach."), stream.done()])

    assert [one.event for one in decode(body)] == ["text", "done"]


# --- the cache hit ------------------------------------------------------------------------


def test_a_cache_hit_is_one_step_and_then_the_answer() -> None:
    """**M6.3.6.** Replaying "looking it up" for an answer computed a quarter of an hour ago
    is a progress bar for work that is not happening, and a reader who notices stops reading
    the steps at all.

    Exactly one step, and it is the one that says why the answer was instant, which is the
    part that tells somebody whether to ask again.

    Delete this and the cached path runs the same step sequence as the fresh one, because that
    is one code path instead of two."""
    events = decode(frames(cache_hit(serve_cached(cached("Yes.", minutes=3), NOW))))

    steps = [one for one in events if one.event == Event.STEP.value]

    assert len(steps) == 1
    assert steps[0].data == step_label(Progress.CACHED)
    assert "instantly" in steps[0].data
    assert [one.event for one in events] == ["step", "text", "done"]


def test_a_freshly_computed_answer_cannot_be_rendered_as_instant() -> None:
    """Telling a reader an answer was instant when the system actually went and looked is the
    same class of lie as not telling them it was cached, pointing the other way: it invites
    them to distrust a figure that is in fact current.

    Refused on the `ServedAnswer`, which already knows which it is, rather than on a flag the
    caller passes.

    Delete this and one call site handles both cases with a boolean, which is the shape that
    gets inverted."""
    with pytest.raises(StreamOrderError, match="not a cache hit"):
        cache_hit(serve_fresh("Yes."))


def test_the_cached_step_label_says_why_and_not_how_long() -> None:
    """The step says the answer was instant and why; the age belongs in the answer text, where
    `serve_cached` already puts it and where `ServedAnswer` refuses to let it be missing. A
    duration in the step label would be a second place the age is rendered, and a second place
    is where the two disagree.

    Also the reason the label passes the no-figures check that every other label passes.

    Delete this and the label grows "answered 14 minutes ago", which is the same sentence
    twice on one screen and two sentences to keep in step."""
    assert scope_revealing(step_label(Progress.CACHED), sources()) == ()
    assert AGE_MARKER not in step_label(Progress.CACHED)


# --- the diagnostic, watched reporting something ------------------------------------------


def test_stream_gaps_is_quiet_on_the_module_as_it_stands() -> None:
    """The baseline for the two tests below, and on its own it proves nothing: an empty tuple
    is what a diagnostic returns whether its checks are there or not.

    Delete this and a real gap has no test that would notice it at all."""
    assert stream_gaps(sources()) == ()


def test_stream_gaps_reports_a_label_that_names_a_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Written because a diagnostic nobody has watched report anything is one nobody can
    rely on**, which is a lesson this repository has learned twice this week.

    The labels are patched rather than edited, so the module is left as it is and the test
    says what a broken vocabulary looks like instead of requiring one.

    Delete this and the label check inside `stream_gaps` can be removed with every other test
    in this file still green, because they all call it on a healthy module."""
    monkeypatch.setattr(
        streaming,
        "STEP_LABELS",
        {**STEP_LABELS, Progress.LOOKING_UP: "Searching Xero for 3 records"},
    )

    gaps = stream_gaps(sources())

    assert any("this installation runs it" in gap for gap in gaps), gaps
    assert any("count of something" in gap for gap in gaps), gaps


def test_stream_gaps_reports_a_heartbeat_that_one_dropped_frame_would_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second unwatched check. If somebody raised the interval to reduce chatter, or
    somebody else lowered the assumed timeout after measuring the real proxy, the two could
    cross and nothing else in this file compares them.

    Delete this and the heartbeat stops fitting inside the timeout it exists to beat, and the
    symptom is a stream that dies during long answers and works in every test."""
    monkeypatch.setattr(streaming, "HEARTBEAT_SECONDS", SHORTEST_IDLE_TIMEOUT_SECONDS)

    gaps = stream_gaps(sources())

    assert any("does not fit twice inside" in gap for gap in gaps), gaps


def test_stream_gaps_reports_a_step_with_no_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `Progress` member added without a label reaches a person as a `KeyError` at the worst
    moment, or as a raw key if somebody makes the lookup forgiving. Either way the reader is
    shown machine text in the middle of an answer.

    Delete this and adding a step is a two-file edit where one of the files is easy to
    forget."""
    monkeypatch.setattr(
        streaming,
        "STEP_LABELS",
        {step: text for step, text in STEP_LABELS.items() if step is not Progress.READING},
    )

    assert any("has no label" in gap for gap in stream_gaps(sources()))


def test_every_step_has_a_label_and_no_label_belongs_to_no_step() -> None:
    """Both directions. A step with no label fails in front of a person; a label with no step
    is dead text that a reader of this file will assume is reachable.

    Delete this and the vocabulary and the labels drift apart, which nothing else notices
    because every test uses the members it names."""
    assert set(STEP_LABELS) == set(Progress)


# --- the honest gap -----------------------------------------------------------------------


def test_this_module_is_reached_by_the_application_that_is_actually_built() -> None:
    """**This replaces the gap test that stood here, and it is the same test inverted.**

    Until the answer route existed, this file asserted that nothing streamed an answer, with a
    message naming what should replace it on the day somebody closed the gap. That day was the
    same day. The replacement is the one the message asked for: the frames a person receives
    carry their citations before the prose, asserted over a real HTTP response in
    `tests/unit/test_answer_route.py`.

    What is asserted here is only reachability, and it is asserted through the import graph
    rather than by looking for a name in `api_routes`: the route imports
    `brain.gate.answer`, which imports this module, so a check for the string "streaming" in
    `dir(api_routes)` would have gone on passing while the gap closed underneath it. That is
    exactly how a gap test rots into a test of nothing.

    Delete this and the encoder can be swapped for an f-string in the lane, and every test in
    this file goes on passing because they all call `encode` directly."""
    import sys

    from brain import api_routes

    assert api_routes is not None
    assert "brain.gate.streaming" in sys.modules

    from brain.gate import answer

    # Through the module's own namespace rather than by attribute access, because mypy
    # runs without implicit re-export here: `answer.AnswerStream` is an error even though
    # it is exactly the fact worth asserting, which is that the lane holds this module's
    # objects and not a second copy of them.
    assert answer.__dict__["AnswerStream"] is AnswerStream
    assert answer.__dict__["cache_hit"] is cache_hit
