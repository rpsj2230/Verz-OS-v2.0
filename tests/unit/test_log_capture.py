"""The log capture keeps a warning's name, place and vocabulary, and nothing a value could be.

Every case logs through a real structlog logger with the capture installed in front of a stand-in
renderer, so what is asserted is what a call in the application would leave behind, and the
renderer's own copy proves the line it prints is the line it was given. Storms are built by
compiling a module of many log calls, one per line, so each call has a place of its own.

Task ids: M27.8.14
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import structlog

from brain.ops import log_capture
from brain.ops.log_capture import (
    INFO_SAMPLE_EVERY,
    MAX_FIELDS,
    MAX_INFO_ROWS_PER_MINUTE,
    MAX_KEY_CHARS,
    MAX_ROWS_PER_MINUTE,
    NO_LITERALS,
    SUPPRESSED_EVENT,
    VOCABULARY,
    Captured,
    Kind,
    LogCapture,
    LogLevel,
    install,
    literals_in,
)
from brain.ops.log_store import FLUSH_SECONDS, WORST_CASE_ROWS_A_DAY
from brain.ops.tracing import SAFE_VALUE_MAX_CHARS
from brain.tables.application_log import MAX_FIELDS_BYTES

#: Pinned far from any wall clock, because the minute window is what these tests are about.
START = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

#: A passphrase of short lowercase words: the one credential the grammar cannot tell from a word.
PASSPHRASE = "correct-horse-battery-staple"

log = structlog.get_logger()


@dataclass
class Clock:
    now: datetime = START

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Printed:
    """What the stand-in renderer was handed, in order."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, _logger: Any, _name: str, event_dict: MutableMapping[str, Any]) -> str:
        self.events.append(dict(event_dict))
        return ""


@contextmanager
def capturing(clock: Clock | None = None, **options: Any) -> Iterator[tuple[LogCapture, Printed]]:
    """A capture installed in front of a renderer that records what it would print."""
    printed = Printed()
    original = structlog.get_config()["processors"]
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            printed,
        ]
    )
    capture = LogCapture(clock=clock or Clock(), **options)
    uninstall = install(capture)
    try:
        yield capture, printed
    finally:
        uninstall()
        structlog.configure(processors=original)
        structlog.contextvars.clear_contextvars()


def only(rows: tuple[Captured, ...]) -> Captured:
    assert len(rows) == 1, rows
    return rows[0]


def storm(method: str, lines: int) -> None:
    """`lines` calls of `log.<method>`, each on its own line of a module with no source file."""
    source = "\n".join(f"log.{method}('storm')" for _ in range(lines))
    exec(compile(source, "<storm>", "exec"), {"__name__": "storm", "log": log})  # noqa: S102


# ------------------------------------------------------------------------ what is kept
def test_a_warning_keeps_its_literal_event_its_place_its_vocabulary_and_a_minted_reference() -> (
    None
):
    """The positive case, through the request middleware's own bindings.

    Delete this and every refusal below is satisfied by a capture that keeps nothing."""
    reference = uuid.uuid4().hex
    with capturing() as (capture, _):
        structlog.contextvars.bind_contextvars(
            trace_id=reference, path="/api/v1/clients/c_0447", trace_id_supplied=False
        )
        line = inspect.currentframe().f_lineno + 1  # type: ignore[union-attr]
        log.warning(
            "capture.positive",
            outcome="denied",
            attempts=3,
            timed_out=True,
            error="KeyError",
            tool="client.read_summary",
        )
        row = only(capture.drain())

    assert row.level is LogLevel.WARNING
    assert row.event == "capture.positive"
    assert row.origin == f"{__name__}:{line}"
    assert row.trace_id == reference
    assert row.error_type is None
    assert row.repeats == 1
    assert dict(row.fields) == {
        "attempts": "3",
        "error": "KeyError",
        "outcome": "denied",
        "timed_out": "true",
        "tool": "client.read_summary",
        "trace_id_supplied": "false",
    }


def test_the_renderer_is_handed_exactly_the_event_the_call_made() -> None:
    """The capture sits immediately before the renderer and changes nothing it is given.

    Delete this and a capture that masked in place would redact the container's standard output,
    which is the log an operator with a shell reads and the one record that existed before."""
    with capturing() as (capture, printed):
        processors = structlog.get_config()["processors"]
        log.warning("capture.untouched", detail="SNM owes 125000", reason="Tan Wei Ling")

    assert processors[-2] is capture
    assert processors[-1] is printed
    assert printed.events == [
        {
            "event": "capture.untouched",
            "level": "warning",
            "detail": "SNM owes 125000",
            "reason": "Tan Wei Ling",
        }
    ]


def test_an_event_name_not_written_literally_in_the_source_is_not_kept() -> None:
    """A question passed as the event, and an event formatted from an argument, keep their place
    and lose their name; a literal beside them keeps its name.

    Delete this and a question typed in lower case is a searchable event name on the Logs
    screen."""
    question = "what is the contract value for snm construction"
    with capturing() as (capture, _):
        log.warning(question)
        log.warning("capture.formatted %s", "for snm construction")
        log.warning("capture.literal")
        rows = capture.drain()

    assert sorted((row.event or "") for row in rows) == ["", "", "capture.literal"]
    assert all(row.origin is not None for row in rows)
    assert "snm" not in repr(rows)
    assert literals_in("<nowhere>") == NO_LITERALS


@pytest.mark.parametrize(
    ("key", "value", "stored"),
    [
        # Words: a sentence, a number in a string, a key, a phone number, a known passphrase.
        ("reason", "not_permitted", "not_permitted"),
        ("reason", "Tan Wei Ling", "[masked:str/small]"),
        ("reason", "125000.00", "[masked:str/small]"),
        ("reason", "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e", "[masked:str/small]"),
        ("reason", "tel:91234567", "[masked:str/small]"),
        ("reason", PASSPHRASE, "[masked:str/small]"),
        ("outcome", True, "[masked:bool]"),
        # Numbers: never a string of digits, never a boolean, never a value that is not finite.
        ("attempts", 3, "3"),
        ("attempts", "3", "[masked:str/small]"),
        ("attempts", True, "[masked:bool]"),
        ("seconds", float("nan"), "[masked:float]"),
        # Flags.
        ("timed_out", False, "false"),
        ("timed_out", "yes", "[masked:str/small]"),
        # Exceptions: a class this process has, never a message and never an invented name.
        ("error", "KeyError", "KeyError"),
        ("error", "duplicate key value (email)=(someone@example.invalid)", "[masked:str/small]"),
        ("error", "NoSuchExceptionAnywhere", "[masked:str/small]"),
        # References: only the shape this system mints.
        ("trace_id", "customer-acme-invoice-7781", "[masked:str/small]"),
    ],
)
def test_a_value_under_a_vocabulary_key_is_kept_only_when_it_is_that_keys_kind(
    key: str, value: object, stored: str
) -> None:
    """One key and one value at a time, through a real call, with the passphrase configured.

    Delete this and any one of the checks behind a word, a number, a flag, an exception or a
    reference can go and the vocabulary keeps whatever a call site filed under it."""
    with capturing(known_secrets=(PASSPHRASE,)) as (capture, _):
        log.warning("capture.vocabulary", **{key: value})
        row = only(capture.drain())

    assert dict(row.fields) == {key: stored}
    assert row.trace_id is None


def test_a_passphrase_nobody_configured_is_a_word() -> None:
    """The sibling of the passphrase case: the same value is kept when it is not a known secret.

    Delete this and the known-secret check could mask every word and the case above would still
    pass."""
    with capturing() as (capture, _):
        log.warning("capture.vocabulary", reason=PASSPHRASE)
        row = only(capture.drain())

    assert dict(row.fields) == {"reason": PASSPHRASE}


def test_a_key_the_module_wrote_literally_keeps_its_shape_and_any_other_key_is_dropped() -> None:
    """`detail` is a literal keyword in this file and outside the vocabulary; a key spread from a
    mapping is neither.

    Delete this and a key built from a client's name reaches the screen, because a value mask
    covers the value and not the key."""
    spread = {"snm_construction": "overdue"}
    with capturing() as (capture, _):
        log.warning("capture.keys", detail="SNM owes 125000", **spread)
        row = only(capture.drain())

    assert dict(row.fields) == {"detail": "[masked:str/small]"}


def test_an_exception_is_kept_as_its_type_and_never_its_message() -> None:
    """Inside a handler, as an instance and as the tuple `sys.exc_info` returns.

    Delete this and a traceback or a message quoting a password can be kept beside the row."""
    secret = "hunter2-for-S1234567D"
    with capturing() as (capture, _):
        try:
            raise ValueError(secret)
        except ValueError as exc:
            log.exception("capture.raised")
            log.error("capture.instance", exc_info=exc)
            log.error("capture.tuple", exc_info=(type(exc), exc, exc.__traceback__))
        rows = capture.drain()

    assert sorted((row.event, row.error_type) for row in rows) == [
        ("capture.instance", "ValueError"),
        ("capture.raised", "ValueError"),
        ("capture.tuple", "ValueError"),
    ]
    assert {row.level for row in rows} == {LogLevel.ERROR}
    assert "hunter2" not in repr(rows)


def test_a_row_keeps_at_most_max_fields_and_each_fits_the_tables_bound() -> None:
    """Every vocabulary key at once, and the figures that make a kept row fit the column's check.

    Delete this and a wide call writes a row the database refuses, which drops the whole batch
    it was in, or the figures drift apart with each side's own test green."""
    wide = {
        key: {
            Kind.WORD: "word",
            Kind.NUMBER: 1,
            Kind.FLAG: True,
            Kind.EXCEPTION: "KeyError",
            Kind.REFERENCE: "not-minted",
        }[kind]
        for key, kind in VOCABULARY.items()
    }
    with capturing() as (capture, _):
        log.warning("capture.wide", **wide)
        row = only(capture.drain())

    assert len(VOCABULARY) > MAX_FIELDS
    assert len(row.fields) == MAX_FIELDS
    # A key and a value at their widest, quoted and separated, sixteen times, inside the check.
    assert MAX_FIELDS * (MAX_KEY_CHARS + SAFE_VALUE_MAX_CHARS + 8) <= MAX_FIELDS_BYTES


# ------------------------------------------------------------------------ the bounds
def test_a_storm_of_one_warning_is_one_row_and_a_count() -> None:
    """Five thousand identical calls across forty seconds.

    Delete this and a warning inside a loop is five thousand rows."""
    clock = Clock()
    with capturing(clock) as (capture, _):
        for _ in range(5000):
            log.warning("capture.repeated", attempts=1)
            clock.now += timedelta(milliseconds=8)
        row = only(capture.drain())

    assert row.repeats == 5000
    assert row.at == START
    assert row.last_at == START + timedelta(milliseconds=8 * 4999)


def test_warnings_past_the_minutes_bound_are_one_counted_row_until_the_next_minute() -> None:
    """A thousand warnings from a thousand places in one minute, then one more a minute later.

    Delete this and a storm of distinct warnings fills the table at the rate the loop runs."""
    clock = Clock()
    with capturing(clock) as (capture, _):
        storm("warning", 1000)
        first = capture.drain()
        clock.now += timedelta(minutes=1)
        storm("warning", 1)
        second = capture.drain()

    kept = [row for row in first if row.event != SUPPRESSED_EVENT]
    counted = [row for row in first if row.event == SUPPRESSED_EVENT]
    assert len(kept) == MAX_ROWS_PER_MINUTE
    assert [dict(row.fields) for row in counted] == [
        {"not_kept": str(1000 - MAX_ROWS_PER_MINUTE), "unreadable": "0"}
    ]
    assert len(second) == 1


def test_rows_waiting_past_the_buffer_are_counted_rather_than_held() -> None:
    """The buffer binds before the minute does when the writer is behind.

    Delete this and a writer that cannot reach the database lets the waiting rows grow without
    bound."""
    with capturing(max_buffered=5, rows_per_minute=1000) as (capture, _):
        storm("error", 50)
        rows = capture.drain()

    assert len([row for row in rows if row.event != SUPPRESSED_EVENT]) == 5
    assert dict(rows[-1].fields) == {"not_kept": "45", "unreadable": "0"}


def test_info_is_a_bounded_sample_and_debug_is_never_kept() -> None:
    """A thousand info calls and a thousand debug calls from distinct places in one minute.

    Delete this and info, which is most of what the application says, is kept at the warning
    rate, or debug is kept at all."""
    with capturing() as (capture, _):
        storm("info", 1000)
        storm("debug", 1000)
        rows = capture.drain()

    assert len(rows) == MAX_INFO_ROWS_PER_MINUTE
    assert {row.level for row in rows} == {LogLevel.INFO}
    # The first kept call is the sampling interval's own, so one call in that many is considered.
    assert min(int(str(row.origin).rsplit(":", 1)[1]) for row in rows) == INFO_SAMPLE_EVERY


def test_the_worst_case_a_day_is_the_minutes_bound_and_a_row_a_flush() -> None:
    """The figure the store's ceiling is argued from, against the two it is made of.

    Delete this and the worst case quoted beside the ceiling can drift from the bound it
    describes."""
    assert WORST_CASE_ROWS_A_DAY == (MAX_ROWS_PER_MINUTE + 60 / FLUSH_SECONDS) * 24 * 60


def test_a_failure_inside_the_capture_never_breaks_the_call_and_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a defect in redaction turns every warning in the application into a
    failed request, and the line never reaches standard output."""

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("redaction broke")

    monkeypatch.setattr(log_capture, "redact", broken)
    with capturing() as (capture, printed):
        log.warning("capture.broken")
        rows = capture.drain()

    assert [one["event"] for one in printed.events] == ["capture.broken"]
    assert [(row.event, dict(row.fields)) for row in rows] == [
        (SUPPRESSED_EVENT, {"not_kept": "0", "unreadable": "1"})
    ]


def test_a_second_capture_is_refused_and_uninstalling_takes_the_first_out() -> None:
    """Delete this and two captures in one process write every row twice."""
    with capturing() as (capture, _), pytest.raises(RuntimeError):
        install(LogCapture())
    assert all(not isinstance(one, LogCapture) for one in structlog.get_config()["processors"])
    assert capture.drain() == ()
