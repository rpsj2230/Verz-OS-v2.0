"""Copying the application's warnings somewhere the console can read them, and nothing a log line
could have carried with them.

The application logs through structlog to standard output and nothing configured it, so the
Errors screen could only say that the log was on the container. A copy the console can read needs
two things standard output never did. **It needs a redactor on its way in**, because a log call is
written by whoever was debugging that afternoon: several call sites log `str(exc)`, which quotes
whatever the exception quoted, one logs a request's `detail`, and the request middleware binds the
path, which can name a record. And **it needs bounds**, because a log that is a table is a log a
storm can fill, and a database that fills stops answering every question, not only the log's.

This module is the policy half: a structlog processor, the redaction it applies and the bounds. It
holds no connection, which is the split `brain.ops.limits` and `brain.ops.limit_store` make, for
their reason: the interesting cases are a storm and a value that must not survive, and neither can
be tested through a module that opens a socket. `brain.ops.log_store` writes what
`LogCapture.drain` hands it.

**What is kept is decided by the shape of the call and never by what a value looks like.** Four
rules, and each closes a door the others leave open.

*The event name is kept only when it is a string literal passed to a log call in the module that
emitted it*, read out of that module's source and cached. A name built by interpolation, formatted
from positional arguments or passed through a variable is not one, and the row keeps its place in
the source and says its name was not kept. That is the rule that makes a question's text impossible
as an event: nothing a person typed is a literal in the source. See
`AN_EVENT_NAME_IS_KEPT_ONLY_WHEN_IT_IS_WRITTEN_IN_THE_SOURCE`.

*A field is kept in the clear only when its key is in `VOCABULARY` and its value is the kind that
key declares.* A word is `brain.ops.tracing.VALUE_TOKEN_RE` with a letter in it and no segment
shaped like a token; a number is a number and never a string of digits; an exception is the name of
an exception class this process has loaded; a reference is the shape this system mints a trace id
in. Any other field under a key the emitting module wrote literally is kept as its shape,
`brain.ops.tracing.mask_value`, and a key nobody wrote literally is dropped, because a key built by
interpolation is the half of a field a value mask does not cover. This is the trace ledger's
allowlist applied to a second stream, and `brain.ops.tracing` argues why an allowlist and not a
detector.

*A word that survives is still run through `brain.ops.pii.detect` and past every secret this
process was configured with*, through `brain.browsing.credentials.scrub_outbound`, and masked if
either finds anything. The grammar already refuses an address, an NRIC and a sentence; the detector
is for a phone number with a word in front of it, and the known secrets are for a passphrase of
short lowercase words, which is the one credential the grammar cannot tell from vocabulary.
`brain.core.redaction` is not called and does not apply: it redacts typed results against a field
policy, and a log event is not a typed result and names no entity.

*An exception is kept as its type and never its message or its traceback*, which is
`brain.jobs_routes.AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE` for the second place an
exception's text would otherwise reach a screen.

**What survives all four, stated rather than hidden.** A single lowercase word under a vocabulary
key is indistinguishable from vocabulary, so a record's field value that happens to be one, filed by
a call site under `reason`, would be kept. No call site in the source does that today, and the key
list is short precisely so that adding one is a reviewed line.

**Standard output is untouched.** The processor sits immediately before the renderer, copies what
it keeps and returns the event unchanged, so `docker logs` reads what it read before, tracebacks
included. See `STANDARD_OUTPUT_IS_UNCHANGED`.

**The bounds are per process and written as figures.** Warnings and above are kept; info is
sampled, one call in `INFO_SAMPLE_EVERY` and at most `MAX_INFO_ROWS_PER_MINUTE` rows; debug never. A
call identical in level, event and place to a row already waiting is a repeat on that row, so a
storm of one warning is one row and a count. At most `MAX_ROWS_PER_MINUTE` new rows a minute and
`MAX_BUFFERED` waiting, and everything past either is counted and written as one row saying how many
were not kept. A row carries at most `MAX_FIELDS` fields of at most
`brain.ops.tracing.SAFE_VALUE_MAX_CHARS` characters. See `A_STORM_IS_ONE_ROW_AND_A_COUNT`.

What is not kept, said rather than implied: debug; most info; the worker's own output, which it
prints rather than logs; and anything said before the application's lifespan installed this. A
repeat keeps the first occurrence's fields and trace reference.

Rejected: a detector over the rendered line, keeping what does not look sensitive. It fails in the
direction that is permanent: a detector that misses one value has written it to a table an
administrator reads for a month. Rejected too: a stdlib `logging` handler, because nothing here
logs through stdlib logging, and routing structlog through it would change what standard output
prints.

Task ids: M27.8.14
"""

from __future__ import annotations

import ast
import enum
import inspect
import math
import re
import sys
import threading
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import structlog

from brain.browsing.credentials import MIN_SCRUBBABLE, scrub_outbound
from brain.ops.pii import detect
from brain.ops.tracing import ATTRIBUTE_KEY_RE, SAFE_VALUE_MAX_CHARS, VALUE_TOKEN_RE, mask_value

# ------------------------------------------------------------------ written-down reasons
#: Why an event name must be a literal in the source.
AN_EVENT_NAME_IS_KEPT_ONLY_WHEN_IT_IS_WRITTEN_IN_THE_SOURCE: Final = (
    "An event name is the one string on a log row a reader searches by and sees in the clear, so "
    "it is kept only when the module that emitted it passes it to a log call as a string literal. "
    "A name built from a value, formatted from positional arguments or passed in a variable is not "
    "kept, and the row names the place in the source instead. A grammar would not do: a question "
    "typed in lower case is a perfectly good event name by any grammar, and it is never a literal "
    "in the source."
)

#: Why the processor copies and never alters.
STANDARD_OUTPUT_IS_UNCHANGED: Final = (
    "The processor sits before the renderer, reads the event, keeps its own copy and returns the "
    "event exactly as it arrived, so the container's standard output carries the same lines, "
    "tracebacks and values included, as it did before a store existed. What is redacted is the "
    "copy the console reads, not the log an operator with a shell on the server reads."
)

#: Why a storm is bounded where it starts rather than where it lands.
A_STORM_IS_ONE_ROW_AND_A_COUNT: Final = (
    "A warning inside a loop logs as fast as the loop runs, and a table written that fast fills "
    "the database every question needs. So a call repeating a row already waiting is a count on "
    "that row, the rows a process may add in a minute and the rows it may hold are figures, and "
    "what falls past either is counted and written as one row saying how many were not kept. A "
    "storm costs the table a bounded number of rows a minute, and the reader is told it happened."
)

#: Why a failure inside the processor is swallowed.
CAPTURE_NEVER_BREAKS_THE_LINE_IT_COPIES: Final = (
    "The processor runs inside every log call in the process. An exception escaping it would "
    "turn a warning into a failed request and would stop the line reaching standard output, "
    "which is the one record an operator had before this existed. So a failure to copy is "
    "counted and reported as a row of its own, and the call it happened in goes on as before."
)

# ------------------------------------------------------------------------ the figures
#: How many new rows one process may add in a minute. Repeats of a waiting row are not new rows.
MAX_ROWS_PER_MINUTE: Final = 60

#: Of those, how many may be sampled info rows.
MAX_INFO_ROWS_PER_MINUTE: Final = 6

#: One info call in this many is considered for a row at all.
INFO_SAMPLE_EVERY: Final = 10

#: How many distinct rows may wait for the writer. A repeat of a waiting row takes no room.
MAX_BUFFERED: Final = 256

#: The fields one row may carry, after redaction.
MAX_FIELDS: Final = 16

#: The longest event name, key and place in the source a row keeps.
MAX_EVENT_CHARS: Final = 160
MAX_KEY_CHARS: Final = 64
MAX_ORIGIN_CHARS: Final = 200

#: The window the per-minute figures are counted over.
WINDOW: Final = timedelta(minutes=1)

#: The event a row saying how many calls were not kept is written under.
SUPPRESSED_EVENT: Final = "log_store.not_kept"

#: A value segment longer than this is not a word.
LONGEST_WORD_CHARS: Final = 40

#: A value segment carrying a digit and longer than this is shaped like a key, a hash or a token.
LONGEST_DIGIT_BEARING_SEGMENT: Final = 15

_SEGMENTS: Final = re.compile(r"[._:/-]")
_LETTER: Final = re.compile(r"[a-z]")
_EXCEPTION_NAME: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
_MODULE_NAME: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,150}$")

#: The trace references this system mints: `uuid4().hex`, optionally after dotted lowercase words,
#: as `brain.identity.administration_reconciliation.TRACE_PREFIX` writes them. A reference a caller
#: proposed in another shape is kept as its shape, and `trace_id_supplied` says it was proposed.
MINTED_REFERENCE: Final = re.compile(r"^(?:[a-z][a-z_]*\.)*[0-9a-f]{16,32}$")


class LogLevel(enum.StrEnum):
    """The levels a row can be kept at. Debug is not one of them."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


#: structlog's method names, as the level a row is kept at. `exception` is an error with a
#: traceback, and `warn` and `fatal` are older spellings. A method not here is not kept.
METHOD_LEVELS: Final[Mapping[str, LogLevel]] = MappingProxyType(
    {
        "info": LogLevel.INFO,
        "warning": LogLevel.WARNING,
        "warn": LogLevel.WARNING,
        "error": LogLevel.ERROR,
        "exception": LogLevel.ERROR,
        "critical": LogLevel.CRITICAL,
        "fatal": LogLevel.CRITICAL,
    }
)

#: The method names a log call is recognised by when a module's source is read.
LOG_METHODS: Final[frozenset[str]] = frozenset({"debug", "msg", *METHOD_LEVELS})


class Kind(enum.StrEnum):
    """What a field in the vocabulary may hold, and so what is kept in the clear under it."""

    #: System vocabulary: a lowercase token with a letter in it, such as an outcome or a tool.
    WORD = "word"
    #: A finite number, and never a string of digits or a boolean.
    NUMBER = "number"
    #: A boolean.
    FLAG = "flag"
    #: The name of an exception class this process has loaded.
    EXCEPTION = "exception"
    #: A trace reference in the shape this system mints one.
    REFERENCE = "reference"


#: The keys whose values are system vocabulary, each with the one kind it may hold. Closed and
#: short for `brain.ops.tracing.SAFE_ATTRIBUTES`'s reason: forgetting a key costs a less informative
#: row, and adding a wrong one is a value on a screen for a month.
VOCABULARY: Final[Mapping[str, Kind]] = MappingProxyType(
    {
        "attempts": Kind.NUMBER,
        "cache": Kind.WORD,
        "capability": Kind.WORD,
        "control": Kind.WORD,
        "dropped": Kind.NUMBER,
        "entity": Kind.WORD,
        "env": Kind.WORD,
        "error": Kind.EXCEPTION,
        "field": Kind.WORD,
        "lane": Kind.WORD,
        "op": Kind.WORD,
        "outcome": Kind.WORD,
        "reason": Kind.WORD,
        "rule": Kind.WORD,
        "rule_id": Kind.WORD,
        "seconds": Kind.NUMBER,
        "status": Kind.WORD,
        "status_code": Kind.NUMBER,
        "timed_out": Kind.FLAG,
        "tool": Kind.WORD,
        "trace_id": Kind.REFERENCE,
        "trace_id_supplied": Kind.FLAG,
    }
)

#: Keys structlog's own processors add, which are the row's columns or nothing at all.
STRUCTURAL_KEYS: Final[frozenset[str]] = frozenset(
    {"event", "level", "timestamp", "exc_info", "stack_info", "positional_args", "logger"}
)


# ------------------------------------------------------------------------ the shapes
@dataclass(frozen=True)
class Literals:
    """What one module's source passes to its log calls literally: event names and keyword names."""

    events: frozenset[str]
    keys: frozenset[str]


NO_LITERALS: Final = Literals(events=frozenset(), keys=frozenset())


@dataclass(frozen=True)
class Captured:
    """One row, as the writer receives it. Every string on it has been through the rules above."""

    level: LogLevel
    #: None when the event name was not a literal in the emitting module's source.
    event: str | None
    #: `module:line` of the call, or None when no frame outside the logging machinery was found.
    origin: str | None
    at: datetime
    last_at: datetime
    repeats: int
    #: The trace reference, when one was bound in the shape this system mints.
    trace_id: str | None
    #: The exception's type when the call carried one. Never its message.
    error_type: str | None
    fields: Mapping[str, str]


@dataclass
class _Waiting:
    level: LogLevel
    event: str | None
    origin: str | None
    at: datetime
    last_at: datetime
    repeats: int
    trace_id: str | None
    error_type: str | None
    fields: dict[str, str]


# ------------------------------------------------------------------------ reading the source
@lru_cache(maxsize=512)
def literals_in(filename: str) -> Literals:
    """Every event name and keyword name this file passes to a log call as a literal.

    Read once per file and cached. A file that cannot be read or parsed has none, which keeps no
    event name and no key outside the vocabulary: failing closed, for a process shipped without its
    source.
    """
    try:
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return NO_LITERALS
    events: set[str] = set()
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in LOG_METHODS or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        events.add(first.value)
        keys.update(one.arg for one in node.keywords if one.arg is not None)
    return Literals(events=frozenset(events), keys=frozenset(keys))


def _is_machinery(module: str) -> bool:
    return any(
        module == one or module.startswith(f"{one}.") for one in ("structlog", "logging", __name__)
    )


def call_site() -> tuple[str, str, int] | None:
    """The module name, file and line of the first frame outside structlog, stdlib logging and
    this module, or None when there is none."""
    frame = inspect.currentframe()
    while frame is not None:
        module = str(frame.f_globals.get("__name__", ""))
        if not _is_machinery(module):
            return module, frame.f_code.co_filename, frame.f_lineno
        frame = frame.f_back
    return None


def _exception_names() -> frozenset[str]:
    seen: set[type[BaseException]] = set()
    stack: list[type[BaseException]] = [BaseException]
    while stack:
        one = stack.pop()
        if one in seen:
            continue
        seen.add(one)
        stack.extend(one.__subclasses__())
    return frozenset(one.__name__ for one in seen)


# ------------------------------------------------------------------------ the decisions
def token_shaped(value: str) -> bool:
    """Whether a lowercase token has a segment too long to be a word, or long and carrying a digit,
    which is what a key, a hash and a session token look like once lowercased."""
    return any(
        len(segment) > LONGEST_WORD_CHARS
        or (len(segment) > LONGEST_DIGIT_BEARING_SEGMENT and any(c.isdigit() for c in segment))
        for segment in _SEGMENTS.split(value)
    )


def carries_a_secret(value: str, secrets: Sequence[str]) -> bool:
    """Whether a known secret appears in this value, by the browser's `scrub_outbound`."""
    return bool(scrub_outbound(value, secrets)[1])


def kept_word(value: object, secrets: Sequence[str]) -> str | None:
    """A value kept as a word, or None. A `StrEnum` member is a string and is kept by its value."""
    if not isinstance(value, str):
        return None
    text = str(value)
    if len(text) > SAFE_VALUE_MAX_CHARS or not VALUE_TOKEN_RE.match(text):
        return None
    if not _LETTER.search(text) or token_shaped(text):
        return None
    if detect(text) or carries_a_secret(text, secrets):
        return None
    return text


def kept_number(value: object) -> str | None:
    """A finite int or float as text, or None. A boolean is not a number here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return str(value)


def kept_flag(value: object) -> str | None:
    """A boolean as text, or None."""
    if not isinstance(value, bool):
        return None
    return "true" if value else "false"


def kept_reference(value: object, secrets: Sequence[str]) -> str | None:
    """A trace reference in the shape this system mints, or None."""
    if not isinstance(value, str) or not MINTED_REFERENCE.match(value):
        return None
    if detect(value) or carries_a_secret(value, secrets):
        return None
    return value


class ExceptionNames:
    """The exception classes this process has loaded, by name, rebuilt when a name is missing.

    A value is an exception's type only if a class of that name exists here. A class can be loaded
    after the set was built, so a miss rebuilds it once before refusing; misses are bounded by the
    rows a minute may add, which is the only place this is asked.
    """

    def __init__(self) -> None:
        self._names = _exception_names()

    def holds(self, value: object) -> bool:
        if not isinstance(value, str) or not _EXCEPTION_NAME.match(value):
            return False
        if value in self._names:
            return True
        self._names = _exception_names()
        return value in self._names


def exception_type(exc_info: object) -> str | None:
    """The type of the exception a call carried, by name: `exc_info=True` inside a handler, an
    instance, or the tuple `sys.exc_info` returns. Never its message."""
    carried: object = None
    if isinstance(exc_info, BaseException):
        carried = type(exc_info)
    elif isinstance(exc_info, tuple) and exc_info:
        carried = exc_info[0]
    elif exc_info is True:
        carried = sys.exc_info()[0]
    if not (isinstance(carried, type) and issubclass(carried, BaseException)):
        return None
    return carried.__name__ if _EXCEPTION_NAME.match(carried.__name__) else None


def redact(
    event_dict: Mapping[str, Any],
    literals: Literals,
    *,
    secrets: Sequence[str],
    exceptions: ExceptionNames,
) -> tuple[dict[str, str], str | None]:
    """The fields a row keeps, and its trace reference.

    A key in the vocabulary keeps its value when the value is that key's kind, and its shape
    otherwise. A key the emitting module wrote literally, and not in the vocabulary, keeps its
    shape. Any other key is dropped. The first `MAX_FIELDS` by name are kept. A kept reference is
    lifted into its own column rather than left among the fields.
    """
    fields: dict[str, str] = {}
    reference: str | None = None
    for key in sorted(str(one) for one in event_dict):
        if key in STRUCTURAL_KEYS or len(key) > MAX_KEY_CHARS or not ATTRIBUTE_KEY_RE.match(key):
            continue
        value = event_dict[key]
        kind = VOCABULARY.get(key)
        if kind is None:
            if key in literals.keys:
                fields[key] = mask_value(value)
            continue
        kept: str | None = None
        match kind:
            case Kind.WORD:
                kept = kept_word(value, secrets)
            case Kind.NUMBER:
                kept = kept_number(value)
            case Kind.FLAG:
                kept = kept_flag(value)
            case Kind.EXCEPTION:
                kept = str(value) if exceptions.holds(value) else None
            case Kind.REFERENCE:
                reference = kept_reference(value, secrets)
                if reference is not None:
                    continue
        fields[key] = kept if kept is not None else mask_value(value)
    return dict(list(fields.items())[:MAX_FIELDS]), reference


def _wall_clock() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------ the processor
class LogCapture:
    """The structlog processor, the rows waiting for the writer, and the per-minute bounds.

    Called from any thread that logs, so every change to what is waiting is made under one lock.
    Redacting a new row runs under it too, and its cost is bounded by the rows a minute may add.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _wall_clock,
        known_secrets: Sequence[str] = (),
        rows_per_minute: int = MAX_ROWS_PER_MINUTE,
        info_rows_per_minute: int = MAX_INFO_ROWS_PER_MINUTE,
        info_every: int = INFO_SAMPLE_EVERY,
        max_buffered: int = MAX_BUFFERED,
    ) -> None:
        self._clock = clock
        self._secrets = tuple(one for one in known_secrets if len(one) >= MIN_SCRUBBABLE)
        self._rows_per_minute = rows_per_minute
        self._info_rows_per_minute = info_rows_per_minute
        self._info_every = info_every
        self._max_buffered = max_buffered
        self._exceptions = ExceptionNames()
        self._lock = threading.Lock()
        self._waiting: dict[tuple[str, str | None, str | None], _Waiting] = {}
        self._window_start: datetime | None = None
        self._rows_in_window = 0
        self._info_in_window = 0
        self._info_seen = 0
        self._not_kept = 0
        self._unreadable = 0

    def __call__(
        self, logger: object, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        """The processor. Returns the event as it arrived; see `STANDARD_OUTPUT_IS_UNCHANGED`."""
        try:
            self.observe(method_name, event_dict)
        except Exception:
            # See CAPTURE_NEVER_BREAKS_THE_LINE_IT_COPIES.
            with self._lock:
                self._unreadable += 1
        return event_dict

    def observe(self, method_name: str, event_dict: Mapping[str, Any]) -> None:
        """Keep a copy of one call, fold it into a waiting row, or count it as not kept."""
        level = METHOD_LEVELS.get(method_name)
        if level is None:
            return
        now = self._clock()
        with self._lock:
            self._roll(now)
            if level is LogLevel.INFO:
                self._info_seen += 1
                if self._info_seen % self._info_every != 0:
                    return
                if self._info_in_window >= self._info_rows_per_minute:
                    return
        site = call_site()
        literals = literals_in(site[1]) if site is not None else NO_LITERALS
        origin = (
            f"{site[0]}:{site[2]}"[:MAX_ORIGIN_CHARS]
            if site is not None and _MODULE_NAME.match(site[0])
            else None
        )
        named = event_dict.get("event")
        event = (
            named
            if isinstance(named, str) and len(named) <= MAX_EVENT_CHARS and named in literals.events
            else None
        )
        key = (level.value, event, origin)
        with self._lock:
            waiting = self._waiting.get(key)
            if waiting is not None:
                waiting.repeats += 1
                waiting.last_at = now
                return
            if (
                self._rows_in_window >= self._rows_per_minute
                or len(self._waiting) >= self._max_buffered
            ):
                self._not_kept += 1
                return
            fields, reference = redact(
                event_dict, literals, secrets=self._secrets, exceptions=self._exceptions
            )
            self._rows_in_window += 1
            if level is LogLevel.INFO:
                self._info_in_window += 1
            self._waiting[key] = _Waiting(
                level=level,
                event=event,
                origin=origin,
                at=now,
                last_at=now,
                repeats=1,
                trace_id=reference,
                error_type=exception_type(event_dict.get("exc_info")),
                fields=fields,
            )

    def _roll(self, now: datetime) -> None:
        if self._window_start is None or now - self._window_start >= WINDOW:
            self._window_start = now
            self._rows_in_window = 0
            self._info_in_window = 0

    def drain(self) -> tuple[Captured, ...]:
        """Every waiting row, and one saying how many calls were not kept when any were not."""
        now = self._clock()
        with self._lock:
            waiting = list(self._waiting.values())
            self._waiting = {}
            not_kept, unreadable = self._not_kept, self._unreadable
            self._not_kept = 0
            self._unreadable = 0
        rows = [
            Captured(
                level=one.level,
                event=one.event,
                origin=one.origin,
                at=one.at,
                last_at=one.last_at,
                repeats=one.repeats,
                trace_id=one.trace_id,
                error_type=one.error_type,
                fields=MappingProxyType(dict(one.fields)),
            )
            for one in waiting
        ]
        if not_kept or unreadable:
            rows.append(
                Captured(
                    level=LogLevel.WARNING,
                    event=SUPPRESSED_EVENT,
                    origin=__name__,
                    at=now,
                    last_at=now,
                    repeats=1,
                    trace_id=None,
                    error_type=None,
                    fields=MappingProxyType(
                        {"not_kept": str(not_kept), "unreadable": str(unreadable)}
                    ),
                )
            )
        return tuple(rows)


# ------------------------------------------------------------------------ installing it
def install(capture: LogCapture) -> Callable[[], None]:
    """Put `capture` into structlog's processors immediately before the renderer, and return what
    takes it out again.

    The renderer is the last processor and turns the event into text, so anything after it would be
    handed a string. A second capture is refused: two copies of every row is a storm the bounds
    were not written for.
    """
    processors = list(structlog.get_config()["processors"])
    if any(isinstance(one, LogCapture) for one in processors):
        msg = "a log capture is already installed in this process"
        raise RuntimeError(msg)
    processors.insert(max(len(processors) - 1, 0), capture)
    structlog.configure(processors=processors)

    def uninstall() -> None:
        current = structlog.get_config()["processors"]
        structlog.configure(processors=[one for one in current if one is not capture])

    return uninstall
