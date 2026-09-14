"""What the three screens cost in series, and why collapsing them into one pass does not pay.

**The three screens are the ones this repository has, not the ones the architecture measured.**
`docs/architecture.html` says three serial screens cost roughly 700ms and asks for them to be
collapsed. That figure is the predecessor's and describes a scanner running as a service, and
nothing in this repository calls one. What a piece of untrusted text passes through here is three
functions in this process: `brain.browsing.credentials.scrub_outbound` removes a credential this
process issued, `brain.ops.pii` finds and replaces personal data, and `brain.gate.injection.assess`
scores the text for an attempt to steer whoever reads it. `THE_THREE_SCREENS` names them. None of
them refuses anything, and nothing here gives any of them a way to.

**Measured, two of the three are regular expressions, and their cost is the number of times the
text is walked.** `count_scans` counts that off the interpreter rather than off the source: it
watches every call to a compiled pattern's scanning methods while the real screens run, so a
screen that grows a pattern grows the count without anybody editing a figure. On text with nothing
in it the serial screens walk it thirty-two times: once to normalise it, twice per injection
signal because each is tried against the raw and the normalised text, and once per personal data
recogniser. The credential screen walks it with `in`, which is an operator and not a call, so it is
in the timings and not in the count. `measure_screens` times the same work with a clock the caller
passes, and `SCREENS_COST_ON_THE_BUILD_MACHINE` records what it said on the build machine: 8.47
ms per kibibyte for the serial screens over ordinary text and 7.99 over identifier-dense text, at
the ninety-fifth percentile. A 4 KiB tool result therefore costs about thirty-five milliseconds of
screening, which is real and is a twentieth of what the architecture's figure led anyone to expect.

**The single pass exists and reports exactly what the serial screens report.**
`screen_in_one_pass` puts every pattern the injection and personal data screens hold into one
alternation and asks it once. If that finds nothing, nothing in either screen matches anywhere and
the empty answer is returned without walking the text again; if it finds anything, the screens run
as they are. `A_COMBINED_PATTERN_ONLY_ANSWERS_WHETHER_NOTHING_MATCHED` is why the match itself is
never read. The alternation is built from `SIGNALS` and `RECOGNISERS` at import rather than written
out, so a signal added there is in the gate without anybody remembering to put it there.

**Where the semantics do not allow a collapse, the screens stay in series.** The injection screen
reads the text as it arrived, because both scrubs replace characters its signals match on
(`THE_INJECTION_SCREEN_READS_THE_TEXT_BEFORE_EITHER_SCRUB`). The credential screen runs first and
alone, because the personal data screen reads what it left, and because a pattern built from a
credential would outlive the call in the `re` module's cache
(`THE_CREDENTIAL_SCRUB_RUNS_FIRST_AND_ALONE`). So the one shared walk is available only when the
credential screen changed nothing, which is when the other two are reading the same string.

**And it does not pay, which is why nothing is switched to it.** `re` has no multi-pattern
automaton: an alternation is tried alternative by alternative at every position, so one combined
scan costs about what its parts cost apart (`AN_ALTERNATION_COSTS_WHAT_ITS_PARTS_COST`).
`collapse_gaps` says so on every call. Two cheaper-looking designs were measured or checked and
rejected. Gating each screen on an alternation of its own was slower on ordinary text than the
patterns it stood in front of. Prefiltering on literal words with `str.lower` or `str.casefold`
disagrees with `re.IGNORECASE`, which lets the dotless i at U+0131 match an `i` that neither
method produces, so a prefilter would skip a signal the pattern would have found; that is
detection coverage lost to save a scan, which is the trade this group of leaves exists to refuse.

Not claimed: M36.2.2.2 and M36.2.2.3. The single pass is built and the differential test holds it
to the serial screens over generated text, but these leaves are performance work sized after
measurement and the measurement says the collapse saves nothing on this engine. A closed leaf would
read as the checkpoints having been collapsed, and they have not been. `collapse_gaps` returning
empty for a run taken where the software is installed is what would close both.

Task ids: M36.2.2.1
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from types import FrameType
from typing import Any, Final

from brain.browsing.credentials import scrub_outbound
from brain.gate.injection import SIGNALS, RiskAssessment, assess

# Private, and imported rather than restated. The gate has to try the normalised text exactly as
# `assess` builds it, and a second copy of the normalisation is a second place for the two to
# disagree, which the differential test would find only for the inputs it happened to generate.
from brain.gate.injection import _normalise as normalise_for_signals
from brain.ops.pii import (
    MINIMUM_TIMED_SAMPLES,
    RECOGNISERS,
    SCRUB_PERCENTILE,
    Detection,
    detect,
    scrub,
)

#: The screens, by the name a reader can find them under, in the order the serial pass runs them.
THE_THREE_SCREENS: Final[tuple[str, ...]] = (
    "brain.browsing.credentials.scrub_outbound",
    "brain.ops.pii.scrub",
    "brain.gate.injection.assess",
)

#: Why the injection screen never reads scrubbed text.
THE_INJECTION_SCREEN_READS_THE_TEXT_BEFORE_EITHER_SCRUB: Final = (
    "Both scrubs replace characters the injection signals match on. A supplied address is the "
    "whole of the exfiltration signal, and the personal data scrub replaces it with [email], so "
    "an injection screen placed after a scrub scores a cleaner text than the one that arrived "
    "and reports an attempt as nothing. It reads the text as it arrived, in the serial order and "
    "in the single pass alike."
)

#: Why the credential screen is outside the shared walk.
THE_CREDENTIAL_SCRUB_RUNS_FIRST_AND_ALONE: Final = (
    "The personal data scrub reads what the credential scrub left, and the two do not commute: "
    "a credential holding something shaped like a phone number is found by that pattern while "
    "it is still in the text and is not there to be found once it has been replaced. So the "
    "order is part of what the screens report and neither pass may change it. Nor may the "
    "credential screen be folded into a combined pattern, because a pattern compiled from a "
    "secret is kept in the re module's cache after the call returns, and "
    "brain.browsing.credentials rests on a value existing in one call frame for one action."
)

#: Why a gate that matched hands the text back to the screens rather than reading the match.
A_COMBINED_PATTERN_ONLY_ANSWERS_WHETHER_NOTHING_MATCHED: Final = (
    "An alternation of every pattern that finds no match anywhere proves no pattern in it "
    "matches anywhere, because a search tries every alternative at every position before it "
    "gives up. The converse does not hold: the alternative that matched may have consumed the "
    "characters another alternative would have matched from, so which signals fired cannot be "
    "read off the match. A gate that finds nothing returns the empty answer; a gate that finds "
    "anything runs the screens themselves."
)

#: The measured reason the single pass is not used.
AN_ALTERNATION_COSTS_WHAT_ITS_PARTS_COST: Final = (
    "Python's re has no multi-pattern automaton. An alternation is tried alternative by "
    "alternative at every position, and a pattern that would have skipped ahead on its own "
    "leading literal loses that inside an alternation, so one combined scan costs about what its "
    "parts cost separately. Measured on the build machine the single pass reports exactly what "
    "the serial screens report and is no faster, which is recorded in "
    "SCREENS_COST_ON_THE_BUILD_MACHINE and repeated by collapse_gaps."
)


class ScreeningError(Exception):
    """A gate was asked to stand in front of patterns it cannot faithfully combine."""


@dataclass(frozen=True)
class Screened:
    """What the three screens report about one piece of text, and nothing about anything else.

    There is no field counting what was withheld, and there is nothing a field could count it
    from. The screens are handed text and the credentials this process issued, never an
    entitlement or the outcome of a read, so a record the reader was refused and a record that
    does not exist both arrive as text that does not mention it, and are the same input here.

    `credentials` is what `scrub_outbound` returns, which is the replacement marker once per
    credential found and never the value.
    """

    assessment: RiskAssessment
    text: str
    detections: tuple[Detection, ...]
    credentials: tuple[str, ...]


def screen_serially(text: str, secrets: Iterable[str] = ()) -> Screened:
    """The three screens as three separate calls, each walking its own input. The reference."""
    assessment = assess(text)
    cleaned, credentials = scrub_outbound(text, secrets)
    detections = detect(cleaned)
    return Screened(
        assessment=assessment,
        text=scrub(cleaned, detections),
        detections=detections,
        credentials=credentials,
    )


# ----------------------------------------------------------------------------- the gate
#: The pattern flags a gate can carry into an alternation, and the inline letter for each.
#: Anything else is refused rather than translated: none of the screens uses another flag, and a
#: translation nobody has tested is a gate that silently answers a different question.
_SCOPED_FLAGS: Final[tuple[tuple[int, str], ...]] = ((re.IGNORECASE, "i"), (re.DOTALL, "s"))


def _scoped(pattern: re.Pattern[str]) -> str:
    """One pattern as an alternative that keeps its own flags inside a combined pattern."""
    remaining = pattern.flags & ~re.UNICODE
    letters = ""
    for flag, letter in _SCOPED_FLAGS:
        if remaining & flag:
            letters += letter
            remaining &= ~flag
    if remaining:
        msg = (
            f"{pattern.pattern!r} carries flags {remaining} that a gate does not translate, so "
            "an alternation built from it would match something the screen itself does not"
        )
        raise ScreeningError(msg)
    return f"(?{letters}:{pattern.pattern})"


def combined(patterns: Iterable[re.Pattern[str]]) -> re.Pattern[str]:
    """Every pattern as one alternation, each keeping its own flags. See the reason constant.

    Refuses an empty set. An empty alternation matches the empty string at the start of every
    text, so a gate over nothing would send every text to the screens and be counted as a
    gate while doing nothing at all.
    """
    alternatives = [_scoped(pattern) for pattern in patterns]
    if not alternatives:
        msg = "a gate over no patterns matches every text and stands in front of nothing"
        raise ScreeningError(msg)
    return re.compile("|".join(alternatives))


SIGNAL_GATE: Final = combined(signal.pattern for signal in SIGNALS)
RECOGNISER_GATE: Final = combined(recogniser.pattern for recogniser in RECOGNISERS)
EVERY_PATTERN_GATE: Final = combined(
    [*(signal.pattern for signal in SIGNALS), *(recogniser.pattern for recogniser in RECOGNISERS)]
)

#: What `assess` returns for text no signal matches, built the way it builds it.
NOTHING_MATCHED: Final = RiskAssessment(score=0, matched=())


def _assessed(text: str) -> RiskAssessment:
    """`assess`, skipped when neither form of the text matches any signal."""
    if SIGNAL_GATE.search(text) is None and SIGNAL_GATE.search(normalise_for_signals(text)) is None:
        return NOTHING_MATCHED
    return assess(text)


def _detected(text: str) -> tuple[Detection, ...]:
    """`detect`, skipped when no recogniser matches the text."""
    if RECOGNISER_GATE.search(text) is None:
        return ()
    return detect(text)


def screen_in_one_pass(text: str, secrets: Iterable[str] = ()) -> Screened:
    """The same report as `screen_serially`, walking the text once where that is allowed.

    The shared walk is taken only when the credential screen left the text as it was, which is
    compared rather than inferred from what it found: a credential whose value is the marker
    itself is found and replaced by an identical string.
    """
    cleaned, credentials = scrub_outbound(text, secrets)
    if cleaned == text and EVERY_PATTERN_GATE.search(text) is None:
        normalised_quiet = SIGNAL_GATE.search(normalise_for_signals(text)) is None
        assessment = NOTHING_MATCHED if normalised_quiet else assess(text)
        detections: tuple[Detection, ...] = ()
    else:
        assessment = _assessed(text)
        detections = _detected(cleaned)
    return Screened(
        assessment=assessment,
        text=scrub(cleaned, detections),
        detections=detections,
        credentials=credentials,
    )


# ----------------------------------------------------------------------------- measuring
#: The methods of a compiled pattern that walk the text they are handed. `match` and
#: `fullmatch` are left out because they are anchored: the NRIC checksum calls `fullmatch` once
#: per nine-character candidate, and counting that as a walk of the screened text would make a
#: count of scans a count of identifiers.
SCANNING_METHODS: Final[frozenset[str]] = frozenset(
    {"search", "finditer", "findall", "sub", "subn", "split"}
)


def count_scans(work: Callable[[], object]) -> int:
    """How many times `work` walked a string with a compiled pattern, counted as it ran.

    Counted by the interpreter's profiling hook, which reports every call into C, rather than by
    reading the source, so the figure is what the code did and not what somebody thinks it does.
    Whatever profiler was installed before is put back afterwards, including when `work` raises.
    """
    counted = 0

    def observe(frame: FrameType, event: str, arg: Any) -> None:
        nonlocal counted
        if event != "c_call" or getattr(arg, "__name__", None) not in SCANNING_METHODS:
            return
        if isinstance(getattr(arg, "__self__", None), re.Pattern):
            counted += 1

    previous = sys.getprofile()
    sys.setprofile(observe)
    try:
        work()
    finally:
        sys.setprofile(previous)
    return counted


#: A paragraph of ordinary work with nothing in it for any screen to find, which is the case a
#: gate is for: the one where it can answer without the screens. Checked by test against the
#: screens themselves, so a signal that starts matching it fails a test rather than quietly
#: turning the recorded run into a measurement of a different case.
ORDINARY_PARAGRAPH: Final = (
    "The renewal for the hosting plan is due next month and the quote for the upgrade has not "
    "gone out yet. Could somebody check whether the invoice history agrees with the account "
    "notes, and reply on this thread once that is done so the renewal can go ahead on time. "
)


def ordinary_text(chars: int) -> str:
    """`ORDINARY_PARAGRAPH` repeated until it is at least this long, never truncated."""
    if chars < 1:
        msg = f"a measurement over {chars} characters times nothing"
        raise ValueError(msg)
    return ORDINARY_PARAGRAPH * math.ceil(chars / len(ORDINARY_PARAGRAPH))


def _percentile(samples: Sequence[float]) -> float:
    """Nearest rank at `SCRUB_PERCENTILE`, never interpolated, as `brain.ops.pii` argues."""
    ordered = sorted(samples)
    rank = max(1, math.ceil(SCRUB_PERCENTILE * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class ScreensCost:
    """One run of both passes over one text: walks counted, time taken, and what it leaves out.

    The prose fields are required for the reason `brain.ops.pii.ScrubCost` gives: a rate is a
    claim about a processor and a text, and a figure that can be constructed without saying
    where it came from will be quoted as though it came from everywhere.
    """

    taken_on: date
    hardware: str
    basis: str
    excludes: str
    chars: int
    samples: int
    serial_scans: int
    one_pass_scans: int
    serial_ms_per_kib: float
    one_pass_ms_per_kib: float
    on_the_client_cpu: bool = False

    def __post_init__(self) -> None:
        for name in ("hardware", "basis", "excludes"):
            if not str(getattr(self, name)).strip():
                msg = f"a timing run states its {name}; without it the figure cannot be checked"
                raise ValueError(msg)
        if self.chars < 1:
            msg = "a run over no characters has no rate per kibibyte in it"
            raise ValueError(msg)
        if self.samples < MINIMUM_TIMED_SAMPLES:
            msg = (
                f"{self.samples} sample(s) is below {MINIMUM_TIMED_SAMPLES}, at which the "
                f"{SCRUB_PERCENTILE} percentile at nearest rank is the maximum by another name"
            )
            raise ValueError(msg)
        if min(self.serial_scans, self.one_pass_scans) < 1:
            msg = (
                "a pass that walked the text no times was not watched rather than free; every "
                "pass here searches at least once, so a zero is the counter and not the screens"
            )
            raise ValueError(msg)
        if min(self.serial_ms_per_kib, self.one_pass_ms_per_kib) <= 0.0:
            msg = "a pass measured at no cost is a clock that did not tick; report the clock"
            raise ValueError(msg)


def measure_screens(
    text: str,
    *,
    clock: Callable[[], float],
    hardware: str,
    basis: str,
    excludes: str,
    taken_on: date,
    secrets: Iterable[str] = (),
    samples: int = MINIMUM_TIMED_SAMPLES,
    on_the_client_cpu: bool = False,
) -> ScreensCost:
    """Time both passes over this text, count their walks, and report both per kibibyte.

    The two passes alternate inside every sample rather than running as two blocks, so that a
    machine that speeds up or slows down during the run moves both figures together instead of
    flattering whichever ran second. The clock is a parameter for the reason
    `brain.ops.pii.measure_scrub` gives: arithmetic over readings can only be tested with a clock
    a test controls.
    """
    if not text:
        msg = "a measurement over no text has no rate per kibibyte in it"
        raise ValueError(msg)
    held = tuple(secrets)
    serial: list[float] = []
    one_pass: list[float] = []
    for _ in range(max(samples, 0)):
        for screen, timings in ((screen_serially, serial), (screen_in_one_pass, one_pass)):
            started = clock()
            screen(text, held)
            elapsed = (clock() - started) * 1000.0
            if elapsed < 0.0:
                msg = f"the clock went backwards by {-elapsed} ms, so nothing here was timed"
                raise ValueError(msg)
            timings.append(elapsed)
    if not serial:
        msg = "a timing run with no samples in it measured nothing"
        raise ValueError(msg)
    kib = len(text) / 1024
    return ScreensCost(
        taken_on=taken_on,
        hardware=hardware,
        basis=basis,
        excludes=excludes,
        chars=len(text),
        samples=len(serial),
        serial_scans=count_scans(lambda: screen_serially(text, held)),
        one_pass_scans=count_scans(lambda: screen_in_one_pass(text, held)),
        serial_ms_per_kib=_percentile(serial) / kib,
        one_pass_ms_per_kib=_percentile(one_pass) / kib,
        on_the_client_cpu=on_the_client_cpu,
    )


_BUILD_MACHINE: Final = (
    "AMD Ryzen 7 6800U, 8 cores and 16 threads, Windows 11, CPython 3.13.15 on a laptop running "
    "on mains power, the same machine brain.ops.pii.SCRUB_COST_ON_THE_BUILD_MACHINE was taken "
    "on. A mobile part with a wide boost range: indicative, and not a server"
)

_EXCLUDES: Final = (
    "anything outside this process. The personal data model leg and Presidio are calls to "
    "containers that do not run here, so neither is in either figure, and the predecessor's "
    "roughly 700ms described a scanner service this repository does not call. The credential "
    "screen is in the timings and not in the walk counts, because it searches with the in "
    "operator, which is not a call the counter can see"
)

#: The runs that have been taken, recorded rather than recomputed at import for the reason
#: `brain.ops.pii.SCRUB_COST_ON_THE_BUILD_MACHINE` gives. Each is the middle of three runs of two
#: hundred samples by its serial figure, and the basis gives the range of all three.
SCREENS_COST_ON_THE_BUILD_MACHINE: Final[tuple[ScreensCost, ...]] = (
    ScreensCost(
        taken_on=date(2026, 9, 15),
        hardware=_BUILD_MACHINE,
        basis=(
            "measure_screens over ordinary_text(16384), which is ORDINARY_PARAGRAPH repeated "
            "to 16569 characters that no screen finds anything in, with no credentials, timed "
            "with time.perf_counter. This is the single pass's best case, the one where the "
            "shared gate answers for both screens: three walks against thirty-two. Across the "
            "three runs the serial screens took 8.24 to 9.20 ms/KiB and the single pass 9.48 to "
            "10.88, so the pass that walks the text a tenth as often took longer in every run"
        ),
        excludes=_EXCLUDES,
        chars=16569,
        samples=200,
        serial_scans=32,
        one_pass_scans=3,
        serial_ms_per_kib=8.47,
        one_pass_ms_per_kib=10.78,
    ),
    ScreensCost(
        taken_on=date(2026, 9, 15),
        hardware=_BUILD_MACHINE,
        basis=(
            "measure_screens over brain.ops.pii.benchmark_text(16384), 16523 characters of "
            "synthetic identifiers with no injection signal in them and no credentials, timed "
            "with time.perf_counter. The shared gate finds the identifiers, so the single pass "
            "falls back to the per-screen gates and the recognisers: fourteen walks against "
            "thirty-two. Across the three runs the serial screens took 7.79 to 8.42 ms/KiB and "
            "the single pass 8.93 to 9.63"
        ),
        excludes=_EXCLUDES,
        chars=16523,
        samples=200,
        serial_scans=32,
        one_pass_scans=14,
        serial_ms_per_kib=7.99,
        one_pass_ms_per_kib=8.93,
    ),
)


def collapse_gaps(
    costs: Sequence[ScreensCost] = SCREENS_COST_ON_THE_BUILD_MACHINE,
) -> tuple[str, ...]:
    """Every reason the single pass is not yet something to switch to, in words.

    It does not return empty today and is not meant to. The argument has a default for the
    reason `brain.ops.pii.budget_gaps` gives: a check that can only be run against the constant
    beside it cannot be shown to fail, and so cannot be shown to pass either.
    """
    if not costs:
        return (
            "nothing has been timed, so whether the single pass saves anything is not known; "
            "run measure_screens and record what it says",
        )
    findings: list[str] = []
    for cost in costs:
        if not cost.on_the_client_cpu:
            findings.append(
                f"the run over {cost.chars} characters was taken on "
                f"{cost.hardware.split(',')[0]} and not where this is installed; the system is "
                "client-hosted, so no figure taken anywhere else decides it"
            )
        if cost.one_pass_ms_per_kib >= cost.serial_ms_per_kib:
            findings.append(
                f"over {cost.chars} characters the single pass cost "
                f"{cost.one_pass_ms_per_kib:.2f} ms/KiB against {cost.serial_ms_per_kib:.2f} "
                "for the serial screens, so it saves nothing there"
            )
    return tuple(findings)
