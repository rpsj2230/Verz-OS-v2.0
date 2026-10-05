"""Free text is scrubbed of personal data before it reaches a third-party model, and put back after.

Until this module the scrubber in `brain.ops.pii` was written, tested, measured on the install's
own processor and called from nowhere on the way out: every question, every passage retrieved for
it and every record read live went to the provider exactly as it was. This is the one place that
changes that, and it is called from the one function that posts to a model provider
(`brain.models.wire.http_transport`) and from the other transport the adapter can build
(`brain.models.adapter.litellm_transport`). `tests/unit/test_egress.py` reads the source and fails
if a third way out appears.

**What leaves is numbered placeholders, and what comes back is put back for the reader.** Each
value found is replaced by its kind and a number, `[sg_nric_1]`, the same value by the same token
everywhere in the request, so the model can still say that two passages are about one person. The
answer is read for those tokens and each is replaced by the value it stood for. The reader is the
person whose question this is, and every value came from text already disclosed to them, so
putting it back tells them nothing they were not shown. Rejected: `pii.scrub`'s bare `[sg_nric]`,
which cannot be put back when there are two, and an answer full of `[email]` is an answer nobody
can act on. See `THE_ANSWER_IS_PUT_BACK_FOR_THE_READER`.

**The rules always run, and the analyser only ever adds.** The deterministic recognisers in
`brain.ops.pii` are the floor and are computed first and unconditionally. The install's analyser
(Presidio, where the profile deploys it, at `pii.analyzer_address`) is asked for the names and
numbers no pattern can describe, and its spans are folded in by `pii.merge_detections`, which
cannot lose a character the rules found. An analyser that is down, slow past
`ANALYSER_BUDGET_SECONDS`, or answers something that cannot be read leaves the rules' scrub, and
the call goes ahead with that. **Nothing is ever sent unscrubbed because the analyser is down.**
See `THE_ANALYSER_ONLY_EVER_ADDS`.

**A scrub that cannot be done stops the call.** If the scrub itself raises, the request is not
sent and the transport raises `EgressScrubFailedError`, a bare member of the transport error
family, so `adapter.failure_from` gives it no trigger and the chain stops. Rejected: sending the
original on a scrub failure, which turns a bug in this module into the leak it exists to prevent.

**What was found is telemetry and never a decision.** One log line per call names the provider,
which detector ran, and how many of each kind were found, and never a value. Nothing here returns
a verdict, refuses a call for what was found, or reads a detection as a reason not to answer: the
module is not an authorisation boundary, for `pii.NEVER_AN_AUTHORISATION_BOUNDARY`'s reason. See
`DETECTIONS_ARE_COUNTED_AND_NEVER_OBEYED`.

**Only a third party is scrubbed for.** The install's own inference server (`wire.LOCAL_PROVIDER`)
sits inside the client's network and is handed text precisely so it can help scrub it; a request
to it leaves the building no more than a database query does, and scrubbing it would degrade every
answer an install that chose a local model gets.

Task ids: M32.2.2.1, M32.2.2.3
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol

import structlog

from brain.models.adapter import Completion, TransportError
from brain.ops.pii import (
    PRESIDIO_BUILT_INS,
    PRESIDIO_KINDS,
    PRESIDIO_LANGUAGE,
    Detection,
    PiiError,
    detect,
    merge_detections,
)

if TYPE_CHECKING:
    import httpx

    from brain.models.driver import DriverRequest

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why the answer is read for placeholders and each is given its value back.
THE_ANSWER_IS_PUT_BACK_FOR_THE_READER: Final = (
    "The model is sent placeholders in place of personal data and answers in them. The person "
    "reading the answer is the one whose question it is, and every value was in text already "
    "disclosed to them, so each placeholder is given its value back before they see it. Only the "
    "third party never held the value."
)

#: Why the analyser can add to a scrub and can never take from it or stop it.
THE_ANALYSER_ONLY_EVER_ADDS: Final = (
    "The rules run first on every call and their spans are kept whole. The analyser's spans are "
    "added where the rules found nothing. An analyser that is down, slow or unreadable leaves the "
    "rules' scrub and the call goes ahead with it, so text is never sent unscrubbed because the "
    "analyser could not be asked."
)

#: Why what was found is logged and nothing else is done with it.
DETECTIONS_ARE_COUNTED_AND_NEVER_OBEYED: Final = (
    "A detection is a signal used to scrub text on its way out. It is counted by kind in the log "
    "line every call writes, and it never refuses a call, never withholds an answer and never "
    "names a value. A scrubber that blocked would be an authorisation boundary decided by "
    "a pattern."
)

# ------------------------------------------------------------------------ the figures
#: How long the analyser may take over all of one request's messages, together. Past it the rest
#: of the request is scrubbed by the rules alone. Two seconds: the analyser is a container on the
#: install's own network, it answers a question's worth of text in tens of milliseconds when it is
#: up, and a person waiting on an answer should not wait longer than this for a leg that only adds.
ANALYSER_BUDGET_SECONDS: Final = 2.0

#: The analyser's path, as the deployed service serves it.
ANALYSE_PATH: Final = "/analyze"

#: The one status that is an analysis.
ANALYSED: Final = 200

#: A placeholder as this module writes it: a kind and a number in square brackets.
PLACEHOLDER_RE: Final = re.compile(r"\[([a-z_]+)_(\d+)\]")


# ------------------------------------------------------------------------ the detector
class Detector(Protocol):
    """What finds spans beyond the rules: the analyser, or a test's stand-in."""

    def __call__(self, text: str, *, timeout_seconds: float) -> Sequence[Detection]: ...


class AnalyserUnavailableError(Exception):
    """The analyser answered with something other than an analysis, or did not answer."""


class EgressScrubFailedError(TransportError):
    """The scrub itself failed, so nothing was sent. See the module docstring."""


def decode_analysis(text: str, payload: object) -> tuple[Detection, ...]:
    """The analyser's answer as detections, or a refusal naming what could not be read.

    Every span must name an entity this install enabled (`pii.PRESIDIO_BUILT_INS`) and has a kind
    for (`pii.PRESIDIO_KINDS`), lie inside the text that was sent, and carry a score. A span under
    its built-in's threshold is dropped, which is what the threshold is for. Anything else is
    refused with `PiiError`, and the caller keeps the rules' scrub: an answer that cannot be read
    is not an answer that found nothing.
    """
    if not isinstance(payload, list):
        msg = "the analyser's answer is not a list of spans"
        raise PiiError(msg)
    thresholds = {one.presidio_name: one.score_threshold for one in PRESIDIO_BUILT_INS}
    found: list[Detection] = []
    for entry in payload:
        if not isinstance(entry, Mapping):
            msg = "the analyser's answer holds something other than a span"
            raise PiiError(msg)
        entity, start, end, score = (entry.get(k) for k in ("entity_type", "start", "end", "score"))
        if not isinstance(entity, str) or entity not in thresholds or entity not in PRESIDIO_KINDS:
            msg = f"the analyser answered with {entity!r}, which this install did not ask for"
            raise PiiError(msg)
        if not (isinstance(start, int) and isinstance(end, int)) or isinstance(start, bool):
            msg = f"a {entity} span does not say where it is"
            raise PiiError(msg)
        if not 0 <= start < end <= len(text):
            msg = f"a {entity} span lies outside the text that was sent"
            raise PiiError(msg)
        if isinstance(score, bool) or not isinstance(score, int | float) or not 0 < score <= 1:
            msg = f"a {entity} span carries no score"
            raise PiiError(msg)
        if score < thresholds[entity]:
            continue
        found.append(
            Detection(kind=PRESIDIO_KINDS[entity], start=start, end=end, confidence=float(score))
        )
    return tuple(sorted(found, key=lambda one: one.start))


def analyser(address: str, client: httpx.Client) -> Detector:
    """The install's analyser at `address`, asked for every built-in this install enabled."""
    url = f"{address.rstrip('/')}{ANALYSE_PATH}"
    entities = [one.presidio_name for one in PRESIDIO_BUILT_INS]

    def ask(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
        import httpx

        try:
            response = client.post(
                url,
                json={"text": text, "language": PRESIDIO_LANGUAGE, "entities": entities},
                timeout=timeout_seconds,
            )
        except httpx.HTTPError:
            raise AnalyserUnavailableError from None
        if response.status_code != ANALYSED:
            raise AnalyserUnavailableError
        try:
            payload = response.json()
        except ValueError:
            raise AnalyserUnavailableError from None
        return decode_analysis(text, payload)

    return ask


# ------------------------------------------------------------------------ the scrub
@dataclass(frozen=True)
class EgressScrub:
    """What leaves, and what is needed to put the answer back. Holds values: never logged."""

    texts: tuple[str, ...]
    #: Each placeholder and the value it stands for.
    originals: Mapping[str, str]
    #: How many values of each kind were found, by the kind's label. Counts only.
    found: Mapping[str, int]
    #: "analyser" when the analyser answered for every message, "rules" otherwise.
    detector: str

    def put_back(self, answer: str) -> str:
        """The answer with each placeholder given its value back. See the module docstring."""
        return PLACEHOLDER_RE.sub(
            lambda match: self.originals.get(match.group(0), match.group(0)), answer
        )


def scrub_for_egress(
    texts: Sequence[str],
    *,
    detector: Detector | None,
    clock: Callable[[], float] = time.monotonic,
) -> EgressScrub:
    """Every text with each value the rules or the analyser found replaced by a placeholder.

    The rules' spans first and whole, the analyser's added by `pii.merge_detections` within one
    budget for the whole request. See `THE_ANALYSER_ONLY_EVER_ADDS`.
    """
    tokens: dict[tuple[str, str], str] = {}
    numbered: Counter[str] = Counter()
    found: Counter[str] = Counter()
    analysed = detector is not None
    deadline = clock() + ANALYSER_BUDGET_SECONDS
    out: list[str] = []
    for text in texts:
        spans = detect(text)
        if detector is not None and analysed:
            remaining = deadline - clock()
            try:
                if remaining <= 0:
                    raise AnalyserUnavailableError
                spans = merge_detections(spans, detector(text, timeout_seconds=remaining))
            except (AnalyserUnavailableError, PiiError):
                analysed = False
        pieces: list[str] = []
        cursor = 0
        for span in sorted(spans, key=lambda one: one.start):
            if span.start < cursor:
                continue
            value = text[span.start : span.end]
            key = (span.kind.value, value)
            if key not in tokens:
                numbered[span.kind.value] += 1
                tokens[key] = f"[{span.kind.value}_{numbered[span.kind.value]}]"
                found[span.kind.value] += 1
            pieces.extend((text[cursor : span.start], tokens[key]))
            cursor = span.end
        pieces.append(text[cursor:])
        out.append("".join(pieces))
    return EgressScrub(
        texts=tuple(out),
        originals=MappingProxyType({token: value for (_, value), token in tokens.items()}),
        found=MappingProxyType(dict(found)),
        detector="analyser" if analysed else "rules",
    )


# ------------------------------------------------------------------------ the one way out
def third_party_call(
    request: DriverRequest,
    send: Callable[[DriverRequest], Completion],
    *,
    provider: str,
    detector: Detector | None,
) -> Completion:
    """Send one request to a third-party model scrubbed, and return its answer put back.

    The one function every transport to a third party calls. See the module docstring for each
    rule: the rules always, the analyser when it answers, nothing sent when the scrub fails, the
    answer put back, and what was found logged by kind and never obeyed.
    """
    try:
        scrubbed = scrub_for_egress([one.content for one in request.messages], detector=detector)
    except Exception as exc:
        log.warning("egress.scrub_failed", provider=provider, error=type(exc).__name__)
        raise EgressScrubFailedError from None
    outbound = dataclasses.replace(
        request,
        messages=tuple(
            dataclasses.replace(one, content=text)
            for one, text in zip(request.messages, scrubbed.texts, strict=True)
        ),
    )
    log.info(
        "egress.scrubbed",
        provider=provider,
        detector=scrubbed.detector,
        found=sum(scrubbed.found.values()),
        kinds=",".join(f"{kind}={count}" for kind, count in sorted(scrubbed.found.items())),
    )
    completion = send(outbound)
    return dataclasses.replace(completion, text=scrubbed.put_back(completion.text))
